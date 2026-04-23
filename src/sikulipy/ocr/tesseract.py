"""Tesseract backend — ports ``org.sikuli.script.TextRecognizer``.

Uses ``pytesseract.image_to_data`` to extract words with bounding boxes +
confidence. Expects a Tesseract binary on ``PATH``; override with
``TesseractBackend(cmd="/path/to/tesseract")``.

Preprocessing: by default we upscale 2x, convert to grayscale, and run
Otsu-style auto-thresholding before handing pixels to Tesseract. This
mirrors what SikuliX's TextRecognizer does and is what makes terminal
text (small, anti-aliased, often light-on-dark) recognisable at all —
without it, Tesseract returns empty strings for most real screen
captures. Pass ``preprocess=False`` to disable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sikulipy.ocr.types import Word

if TYPE_CHECKING:  # pragma: no cover
    import numpy as np


def _as_pil(image):
    """Coerce Image / ScreenImage / ndarray / path-like to a PIL.Image."""
    from PIL import Image as PILImage

    # numpy array (BGR) -> RGB PIL
    import numpy as np  # local, may fail on exotic hosts — deferred

    if isinstance(image, np.ndarray):
        arr = image
        if arr.ndim == 3 and arr.shape[2] == 3:
            arr = arr[:, :, ::-1]  # BGR -> RGB
        return PILImage.fromarray(arr)

    # ScreenImage / Image wrappers
    from sikulipy.core.image import Image, ScreenImage

    if isinstance(image, ScreenImage):
        return _as_pil(image.bitmap)
    if isinstance(image, Image):
        return _as_pil(image.load())

    return PILImage.open(str(image))


def _preprocess(pil_image, scale: float = 2.0):
    """Return a binarised, upscaled grayscale PIL image for Tesseract.

    Tesseract was trained on ~300 DPI black-on-white scans. Screen
    captures are closer to 100 DPI and often use anti-aliased light
    text on a dark background — both of which confuse the default
    page-segmentation/classifier pipeline. Upscaling + grayscale +
    Otsu threshold is the standard fix and matches SikuliX's
    TextRecognizer.applyPreprocessing.

    If the source image is predominantly dark (mean luminance < 128),
    we invert after thresholding so glyphs end up dark-on-light, which
    is what Tesseract expects.
    """
    from PIL import Image as PILImage
    from PIL import ImageOps

    # Upscale first (bicubic) — thresholding a small image wrecks detail.
    if scale != 1.0:
        new_size = (int(pil_image.width * scale), int(pil_image.height * scale))
        pil_image = pil_image.resize(new_size, PILImage.BICUBIC)

    gray = pil_image.convert("L")

    # If the image is mostly dark pixels (terminals), invert so that
    # glyphs end up dark on a light background.
    try:
        hist = gray.histogram()
        total = sum(hist) or 1
        mean = sum(i * c for i, c in enumerate(hist)) / total
        if mean < 128:
            gray = ImageOps.invert(gray)
    except Exception:
        pass  # pragma: no cover - defensive

    # Auto-contrast stretch, then a fixed threshold. PIL has no built-in
    # Otsu, but autocontrast + a midpoint split is a decent proxy and
    # doesn't require numpy/cv2 in this module.
    gray = ImageOps.autocontrast(gray, cutoff=2)
    binarised = gray.point(lambda v: 255 if v > 160 else 0, mode="L")
    return binarised


class TesseractBackend:
    def __init__(
        self,
        cmd: str | None = None,
        lang: str = "eng",
        config: str = "--psm 6",
        preprocess: bool = True,
    ) -> None:
        self.lang = lang
        self.config = config
        self.preprocess = preprocess
        if cmd is not None:
            import pytesseract

            pytesseract.pytesseract.tesseract_cmd = cmd

    # ---- Public API -------------------------------------------------
    def _prepare(self, image):
        pil = _as_pil(image)
        if self.preprocess:
            try:
                pil = _preprocess(pil)
            except Exception:  # pragma: no cover - fall back to raw pixels
                pass
        return pil

    def read(self, image) -> str:
        import pytesseract

        return pytesseract.image_to_string(self._prepare(image), lang=self.lang, config=self.config)

    def read_words(self, image) -> list[Word]:
        import pytesseract

        data = pytesseract.image_to_data(
            self._prepare(image),
            lang=self.lang,
            config=self.config,
            output_type=pytesseract.Output.DICT,
        )
        return self._parse_image_to_data(data)

    # ---- Helpers ----------------------------------------------------
    @staticmethod
    def _parse_image_to_data(data: dict) -> list[Word]:
        """Convert pytesseract's dict-of-columns into a list of ``Word``s."""
        n = len(data.get("text", []))
        words: list[Word] = []
        for i in range(n):
            text = (data["text"][i] or "").strip()
            if not text:
                continue
            try:
                conf = float(data["conf"][i])
            except (TypeError, ValueError):
                conf = -1.0
            if conf < 0:
                continue
            words.append(
                Word(
                    text=text,
                    x=int(data["left"][i]),
                    y=int(data["top"][i]),
                    w=int(data["width"][i]),
                    h=int(data["height"][i]),
                    confidence=conf / 100.0,  # normalise 0..1
                    line=int(data.get("line_num", [0])[i]) if "line_num" in data else 0,
                    block=int(data.get("block_num", [0])[i]) if "block_num" in data else 0,
                )
            )
        return words
