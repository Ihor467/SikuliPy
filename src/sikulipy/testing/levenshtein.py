"""Levenshtein distance + ratio for OCR-based text assertions.

Pure-Python fallback, ~30 lines. If ``rapidfuzz`` is installed we
delegate (much faster on long strings); detection is lazy and cached.
"""

from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def _rapidfuzz():
    try:
        import rapidfuzz.distance.Levenshtein as rf

        return rf
    except Exception:
        return None


def distance(a: str, b: str) -> int:
    """Return the Levenshtein distance between ``a`` and ``b``."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    rf = _rapidfuzz()
    if rf is not None:
        return int(rf.distance(a, b))
    # Two-row dynamic programming — O(len(b)) memory.
    prev = list(range(len(b) + 1))
    curr = [0] * (len(b) + 1)
    for i, ca in enumerate(a, start=1):
        curr[0] = i
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            curr[j] = min(
                prev[j] + 1,        # deletion
                curr[j - 1] + 1,    # insertion
                prev[j - 1] + cost,  # substitution
            )
        prev, curr = curr, prev
    return prev[len(b)]


def ratio(a: str, b: str) -> float:
    """Similarity ratio in ``[0.0, 1.0]``: ``1 - distance / max(len)``.

    Two empty strings return ``1.0`` (defining "no difference"). One
    empty + one non-empty returns ``0.0``.
    """
    if not a and not b:
        return 1.0
    n = max(len(a), len(b))
    if n == 0:
        return 1.0
    return 1.0 - (distance(a, b) / n)
