"""Shared OCR result types.

A single ``Word`` shape lets Tesseract, PaddleOCR, and any future backend
share the same surface. ``Region.find_text`` works on these dataclasses
without caring where they came from.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Word:
    """A recognised text token with its screen-space bounding box."""

    text: str
    x: int
    y: int
    w: int
    h: int
    confidence: float = 0.0
    line: int = 0
    block: int = 0

    def offset(self, dx: int, dy: int) -> "Word":
        return Word(
            text=self.text,
            x=self.x + dx,
            y=self.y + dy,
            w=self.w,
            h=self.h,
            confidence=self.confidence,
            line=self.line,
            block=self.block,
        )
