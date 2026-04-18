"""PaddleOCR backend — ports PaddleOCREngine.java + PaddleOCRClient.java.

Two modes:

* **In-process** (``endpoint=None``) — uses the ``paddleocr`` Python package.
  Call ``PaddleOCR.recognize(image)`` to get a list of ``Word`` objects.
* **HTTP** (``endpoint="http://localhost:5000"``) — posts the image to
  the same REST server the Java engine talks to and parses the JSON
  response shape: ``[[ [[x1,y1],...,[x4,y4]], ("text", conf) ], ...]``.

Both modes return the same :class:`sikulipy.ocr.types.Word` list so the
rest of the code (``Region.find_text``, ``OCR.read``) is backend-agnostic.
"""

from __future__ import annotations

import base64
import json as _json
from io import BytesIO
from pathlib import Path
from typing import Any

from sikulipy.ocr.types import Word


def _image_to_png_bytes(image) -> bytes:
    """Serialise an image-like to PNG bytes suitable for HTTP upload."""
    from PIL import Image as PILImage

    import numpy as np

    buf = BytesIO()
    if isinstance(image, (str, Path)):
        with open(image, "rb") as f:
            return f.read()
    if isinstance(image, np.ndarray):
        arr = image[:, :, ::-1] if (image.ndim == 3 and image.shape[2] == 3) else image
        PILImage.fromarray(arr).save(buf, format="PNG")
        return buf.getvalue()
    from sikulipy.core.image import Image, ScreenImage

    if isinstance(image, ScreenImage):
        return _image_to_png_bytes(image.bitmap)
    if isinstance(image, Image):
        return _image_to_png_bytes(image.load())
    raise TypeError(f"Unsupported image type for PaddleOCR: {type(image)!r}")


def _bbox_from_polygon(poly: list[list[float]]) -> tuple[int, int, int, int]:
    xs = [int(p[0]) for p in poly]
    ys = [int(p[1]) for p in poly]
    x0, y0 = min(xs), min(ys)
    x1, y1 = max(xs), max(ys)
    return x0, y0, x1 - x0, y1 - y0


class PaddleOCR:
    """Unified in-process / HTTP PaddleOCR client."""

    def __init__(
        self,
        endpoint: str | None = None,
        lang: str = "en",
        *,
        use_angle_cls: bool = True,
    ) -> None:
        self.endpoint = endpoint.rstrip("/") if endpoint else None
        self.lang = lang
        self.use_angle_cls = use_angle_cls
        self._engine: Any | None = None  # lazy paddleocr.PaddleOCR instance

    # ---- OcrBackend interface --------------------------------------
    def read(self, image) -> str:
        return "\n".join(w.text for w in self.read_words(image))

    def read_words(self, image) -> list[Word]:
        raw = self._recognize_raw(image)
        return self._raw_to_words(raw)

    # ---- Low-level --------------------------------------------------
    def _recognize_raw(self, image) -> list:
        if self.endpoint is None:
            return self._recognize_inprocess(image)
        return self._recognize_http(image)

    def _recognize_inprocess(self, image) -> list:
        if self._engine is None:
            from paddleocr import PaddleOCR as _PP

            self._engine = _PP(use_angle_cls=self.use_angle_cls, lang=self.lang)
        # paddleocr accepts path strings or numpy arrays
        if isinstance(image, (str, Path)):
            result = self._engine.ocr(str(image), cls=self.use_angle_cls)
        else:
            import numpy as np

            from sikulipy.core.image import Image, ScreenImage

            if isinstance(image, ScreenImage):
                arr = image.bitmap
            elif isinstance(image, Image):
                arr = image.load()
            elif isinstance(image, np.ndarray):
                arr = image
            else:
                raise TypeError(f"Unsupported image type: {type(image)!r}")
            result = self._engine.ocr(arr, cls=self.use_angle_cls)
        return result[0] if result else []

    def _recognize_http(self, image) -> list:
        import urllib.request

        payload = _json.dumps({
            "image": base64.b64encode(_image_to_png_bytes(image)).decode("ascii"),
            "lang": self.lang,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.endpoint}/ocr",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
        data = _json.loads(body)
        # OculiX's server returns {"result": [[polygon, [text, conf]], ...]}
        return data.get("result", data if isinstance(data, list) else [])

    @staticmethod
    def _raw_to_words(raw: list) -> list[Word]:
        words: list[Word] = []
        for entry in raw or []:
            if not entry or len(entry) < 2:
                continue
            poly, text_conf = entry[0], entry[1]
            if isinstance(text_conf, (list, tuple)) and len(text_conf) >= 2:
                text, conf = str(text_conf[0]), float(text_conf[1])
            else:
                text, conf = str(text_conf), 0.0
            x, y, w, h = _bbox_from_polygon(poly)
            words.append(Word(text=text, x=x, y=y, w=w, h=h, confidence=conf))
        return words

    # ---- Parity helpers (mirror Java API) ---------------------------
    def recognize(self, image) -> str:
        """Return the raw paddle JSON string for parity with PaddleOCRClient.java."""
        return _json.dumps(self._recognize_raw(image))

    def parse_texts(self, payload: str) -> list[str]:
        return [w.text for w in self._raw_to_words(_json.loads(payload))]

    def parse_text_with_confidence(self, payload: str) -> dict[str, float]:
        return {w.text: w.confidence for w in self._raw_to_words(_json.loads(payload))}

    def find_text_coordinates(self, payload: str, needle: str) -> tuple[int, int, int, int] | None:
        for w in self._raw_to_words(_json.loads(payload)):
            if needle in w.text:
                return (w.x, w.y, w.w, w.h)
        return None
