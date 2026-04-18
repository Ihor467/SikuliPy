"""High-level OCR facade — ports ``org.sikuli.script.OCR``.

Dispatches to the active :class:`OcrBackend`. Defaults to Tesseract.
Swap with :func:`sikulipy.ocr.set_ocr` (see tests and PaddleOCR usage).
"""

from __future__ import annotations

from sikulipy.ocr._backend import get_ocr
from sikulipy.ocr.types import Word


class OCR:
    # ---- Raw extraction ---------------------------------------------
    @classmethod
    def read(cls, image) -> str:
        return get_ocr().read(image)

    @classmethod
    def read_words(cls, image) -> list[Word]:
        return get_ocr().read_words(image)

    @classmethod
    def read_lines(cls, image) -> list[str]:
        """Group words by their ``line`` attribute (fallback to y-coordinate bands)."""
        words = get_ocr().read_words(image)
        if not words:
            return []
        if any(w.line for w in words):
            by_line: dict[tuple[int, int], list[Word]] = {}
            for w in words:
                by_line.setdefault((w.block, w.line), []).append(w)
            keys = sorted(by_line.keys())
            return [" ".join(w.text for w in by_line[k]) for k in keys]
        # Fallback: cluster by vertical bands of mean height
        words_sorted = sorted(words, key=lambda w: (w.y, w.x))
        lines: list[list[Word]] = []
        threshold = max(8, sum(w.h for w in words) // (2 * len(words)))
        for w in words_sorted:
            if lines and abs(lines[-1][-1].y - w.y) <= threshold:
                lines[-1].append(w)
            else:
                lines.append([w])
        return [" ".join(w.text for w in line) for line in lines]

    # ---- Search -----------------------------------------------------
    @classmethod
    def find_text(cls, image, needle: str) -> Word | None:
        for w in get_ocr().read_words(image):
            if needle in w.text:
                return w
        return None

    @classmethod
    def find_all_text(cls, image, needle: str) -> list[Word]:
        return [w for w in get_ocr().read_words(image) if needle in w.text]

    @classmethod
    def find_word(cls, image, needle: str, *, ignore_case: bool = False) -> Word | None:
        """Find a single word (whole-token match)."""
        target = needle.casefold() if ignore_case else needle
        for w in get_ocr().read_words(image):
            token = w.text.casefold() if ignore_case else w.text
            if token == target:
                return w
        return None
