"""Swappable OCR backend.

Same pattern as :mod:`sikulipy.core._input_backend` — a Protocol plus a
module-level singleton with a ``set_ocr()`` override hook for tests.
"""

from __future__ import annotations

from typing import Protocol

from sikulipy.ocr.types import Word


class OcrBackend(Protocol):
    def read_words(self, image) -> list[Word]: ...
    def read(self, image) -> str: ...


_ocr: OcrBackend | None = None


def get_ocr() -> OcrBackend:
    global _ocr
    if _ocr is None:
        from sikulipy.ocr.tesseract import TesseractBackend

        _ocr = TesseractBackend()
    return _ocr


def set_ocr(backend: OcrBackend | None) -> None:
    """Install a custom OCR backend. Pass ``None`` to reset to Tesseract default."""
    global _ocr
    _ocr = backend
