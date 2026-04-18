"""OCR engines.

Public surface:

* :class:`OCR` — facade over the active backend.
* :class:`Word` — recognised token with bounding box + confidence.
* :func:`set_ocr` / :func:`get_ocr` — swap backends (tests, custom engines).
* :class:`TesseractBackend`, :class:`PaddleOCR` — concrete backends.
"""

from sikulipy.ocr._backend import OcrBackend, get_ocr, set_ocr
from sikulipy.ocr.engine import OCR
from sikulipy.ocr.paddle import PaddleOCR
from sikulipy.ocr.tesseract import TesseractBackend
from sikulipy.ocr.types import Word

__all__ = [
    "OCR",
    "OcrBackend",
    "PaddleOCR",
    "TesseractBackend",
    "Word",
    "get_ocr",
    "set_ocr",
]
