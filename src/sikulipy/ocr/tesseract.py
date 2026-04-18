"""Tesseract backend — ports ``org.sikuli.script.TextRecognizer``.

Uses ``pytesseract.image_to_data`` to extract words with bounding boxes +
confidence. Expects a Tesseract binary on ``PATH``; override with
``TesseractBackend(cmd="/path/to/tesseract")``.
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


class TesseractBackend:
    def __init__(self, cmd: str | None = None, lang: str = "eng", config: str = "") -> None:
        self.lang = lang
        self.config = config
        if cmd is not None:
            import pytesseract

            pytesseract.pytesseract.tesseract_cmd = cmd

    # ---- Public API -------------------------------------------------
    def read(self, image) -> str:
        import pytesseract

        return pytesseract.image_to_string(_as_pil(image), lang=self.lang, config=self.config)

    def read_words(self, image) -> list[Word]:
        import pytesseract

        data = pytesseract.image_to_data(
            _as_pil(image),
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
