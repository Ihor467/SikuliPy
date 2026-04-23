"""Mutable default values that can be overridden globally.

Callers — typically the SikuliX-compatible ``Settings`` shim at
``sikuli._settings`` — mutate these at runtime so user scripts like
``Settings.MinSimilarity = 0.9`` take effect without having to thread
the value through every ``find()`` call.

Keep this module tiny and dependency-free: anything that imports it
should not pay for numpy/cv2/pynput.
"""

from __future__ import annotations


# Default similarity used when a caller passes a plain path / Image /
# ndarray to Region.find(...) instead of a Pattern with its own
# threshold. Matches SikuliX's ``Settings.MinSimilarity`` default.
_min_similarity: float = 0.7


def get_min_similarity() -> float:
    return _min_similarity


def set_min_similarity(value: float) -> None:
    global _min_similarity
    _min_similarity = float(value)


__all__ = ["get_min_similarity", "set_min_similarity"]
