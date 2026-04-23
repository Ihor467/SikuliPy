"""Port of ``org.sikuli.script.Finder`` — OpenCV template matching.

Uses ``cv2.TM_SQDIFF_NORMED`` under the hood (minimised, perfect = 0,
worst = 1) and exposes scores to callers in the familiar
higher-is-better 0..1 orientation (``score = 1 - sqdiff``). This
sidesteps a silent ``TM_CCOEFF_NORMED`` numerical quirk: when the
needle has near-zero pixel variance (solid-colour UI elements — a
filled button, a blank icon, a colour swatch), TM_CCOEFF_NORMED's
internal divide-by-std returns 1.0 *everywhere* and the finder reports
a perfect match at (0, 0). TM_SQDIFF_NORMED has no such division and
stays well-behaved on zero-variance needles.

Single-match uses ``cv2.minMaxLoc``. Multi-match does a threshold +
greedy non-max suppression pass (faster and simpler than full NMS,
good enough for screen-automation needles which rarely overlap
heavily).
"""

from __future__ import annotations

from typing import Iterator

import cv2
import numpy as np

from sikulipy.core.match import Match


def _as_bgr(img) -> np.ndarray:
    """Coerce an Image/ndarray/path-like into a BGR uint8 numpy array."""
    if isinstance(img, np.ndarray):
        return img
    # Delayed import to dodge cycles.
    from sikulipy.core.image import Image, ScreenImage

    if isinstance(img, ScreenImage):
        return img.bitmap
    if isinstance(img, Image):
        return img.load()
    return Image(img).load()


class Finder:
    """Search for ``needle`` inside ``haystack``."""

    def __init__(self, haystack, region=None) -> None:
        self.haystack_bgr = _as_bgr(haystack)
        self.region = region
        self._offset_x = getattr(region, "x", 0) if region is not None else 0
        self._offset_y = getattr(region, "y", 0) if region is not None else 0
        self._queue: list[Match] = []

    # ---- Single match ------------------------------------------------
    def find(self, needle, similarity: float = 0.7) -> Match | None:
        needle_bgr = _as_bgr(needle)
        h, w = needle_bgr.shape[:2]
        # TM_SQDIFF_NORMED: 0 = perfect, 1 = worst. Convert the caller's
        # similarity threshold (higher-is-better, 0..1) to a max allowed
        # sqdiff and look for global minima.
        result = cv2.matchTemplate(self.haystack_bgr, needle_bgr, cv2.TM_SQDIFF_NORMED)
        min_v, _max_v, min_l, _max_l = cv2.minMaxLoc(result)
        score = 1.0 - float(min_v)
        if score < similarity:
            return None
        return Match(
            x=int(min_l[0]) + self._offset_x,
            y=int(min_l[1]) + self._offset_y,
            w=int(w),
            h=int(h),
            score=score,
        )

    # ---- Multi match -------------------------------------------------
    def find_all(self, needle, similarity: float = 0.7) -> list[Match]:
        needle_bgr = _as_bgr(needle)
        h, w = needle_bgr.shape[:2]
        result = cv2.matchTemplate(self.haystack_bgr, needle_bgr, cv2.TM_SQDIFF_NORMED)

        matches: list[Match] = []
        # Greedy NMS: repeatedly pick the global *minimum* (perfect = 0),
        # record it, then paint that window to +inf so we don't report
        # overlapping hits.
        max_sqdiff = 1.0 - similarity
        while True:
            min_v, _max_v, min_l, _max_l = cv2.minMaxLoc(result)
            if float(min_v) > max_sqdiff:
                break
            mx, my = int(min_l[0]), int(min_l[1])
            matches.append(
                Match(
                    x=mx + self._offset_x,
                    y=my + self._offset_y,
                    w=w,
                    h=h,
                    score=1.0 - float(min_v),
                    index=len(matches),
                )
            )
            x0 = max(0, mx - w // 2)
            y0 = max(0, my - h // 2)
            x1 = min(result.shape[1], mx + w // 2 + 1)
            y1 = min(result.shape[0], my + h // 2 + 1)
            result[y0:y1, x0:x1] = np.inf
        self._queue = list(matches)
        return matches

    # ---- Iterator-style API (Java parity) ----------------------------
    def hasNext(self) -> bool:  # noqa: N802 - Java parity
        return bool(self._queue)

    def next(self) -> Match | None:
        return self._queue.pop(0) if self._queue else None

    def __iter__(self) -> Iterator[Match]:
        while self._queue:
            yield self._queue.pop(0)
