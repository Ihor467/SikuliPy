"""Tesseract + Levenshtein-ratio text assertion.

Pulls text via the active OCR backend (defaults to Tesseract, which
already runs the upscale/threshold preprocessing pipeline — raw screen
pixels OCR to empty strings without it), normalises it, and computes
a Levenshtein similarity ratio against the expected string. Fails if
the ratio drops below ``ratio_threshold`` (default 0.85, slack enough
to absorb typical OCR noise on antialiased UI text but tight enough
to catch a real label change).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from sikulipy.ocr import OCR
from sikulipy.testing.levenshtein import ratio as _levenshtein_ratio

if TYPE_CHECKING:  # pragma: no cover
    import numpy as np


Normalizer = Callable[[str], str]


@dataclass
class TextDiff:
    """Result of one OCR-based text comparison."""

    passed: bool
    ratio: float
    threshold: float
    expected_norm: str
    actual_norm: str
    actual_raw: str
    message: str = ""


_WS = re.compile(r"\s+")


def normalize(
    text: str,
    *,
    casefold: bool = True,
    collapse_whitespace: bool = True,
    strip_diacritics: bool = False,
) -> str:
    """Default normaliser: NFC, optional lowercase / whitespace squeeze
    / diacritic strip. Pulled out so callers can swap in their own."""
    if strip_diacritics:
        text = "".join(
            ch for ch in unicodedata.normalize("NFKD", text)
            if not unicodedata.combining(ch)
        )
    else:
        text = unicodedata.normalize("NFC", text)
    if casefold:
        text = text.casefold()
    if collapse_whitespace:
        text = _WS.sub(" ", text).strip()
    return text


def compare_text(
    actual_image: "np.ndarray",
    expected: str,
    *,
    ratio_threshold: float = 0.85,
    normalize_fn: Normalizer | None = None,
) -> TextDiff:
    """Run OCR on ``actual_image`` and compare to ``expected``.

    ``actual_image`` is anything :class:`OCR.read` accepts (numpy
    BGR ndarray, ``ScreenImage``, ``Image``, or path).
    """
    norm = normalize_fn or normalize
    raw = OCR.read(actual_image) or ""
    actual = norm(raw)
    target = norm(expected)
    score = _levenshtein_ratio(actual, target)
    passed = score >= ratio_threshold
    msg = "" if passed else (
        f"OCR ratio {score:.3f} < threshold {ratio_threshold:.3f}; "
        f"expected={target!r} actual={actual!r}"
    )
    return TextDiff(
        passed=passed,
        ratio=score,
        threshold=ratio_threshold,
        expected_norm=target,
        actual_norm=actual,
        actual_raw=raw,
        message=msg,
    )
