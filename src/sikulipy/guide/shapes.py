"""Guide shape models — Arrow, Rectangle, Callout, Spotlight, Text.

Each shape is a pure dataclass that:

* exposes ``bounds`` as ``(x, y, w, h)`` in screen coordinates so the
  backend knows where to size its overlay window, and
* draws itself onto a BGR :class:`numpy.ndarray` via :meth:`draw`.

Drawing uses OpenCV when available. The shape classes are safe to
import without cv2 or numpy — :meth:`draw` raises
:class:`RuntimeError` on such hosts instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:  # numpy/cv2 are optional on this host
    import numpy as np


ColorBGR = tuple[int, int, int]


_NAMED_COLORS: dict[str, ColorBGR] = {
    "red": (0, 0, 255),
    "green": (0, 255, 0),
    "blue": (255, 0, 0),
    "yellow": (0, 255, 255),
    "cyan": (255, 255, 0),
    "magenta": (255, 0, 255),
    "white": (255, 255, 255),
    "black": (0, 0, 0),
}


def _to_bgr(color: "str | ColorBGR") -> ColorBGR:
    if isinstance(color, str):
        return _NAMED_COLORS.get(color.lower(), _NAMED_COLORS["red"])
    r = tuple(int(c) for c in color)
    if len(r) != 3:
        raise ValueError(f"color must be a (B, G, R) triple, got {color!r}")
    return r  # type: ignore[return-value]


@runtime_checkable
class Shape(Protocol):
    """Common interface: every guide shape can locate and draw itself."""

    def bounds(self) -> tuple[int, int, int, int]: ...
    def draw(self, canvas: "np.ndarray") -> None: ...


# ---------------------------------------------------------------------------
# Shapes
# ---------------------------------------------------------------------------


@dataclass
class Rectangle:
    """Axis-aligned outlined rectangle."""

    x: int
    y: int
    w: int
    h: int
    color: "str | ColorBGR" = "red"
    thickness: int = 3

    def bounds(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.w, self.h)

    def draw(self, canvas: "np.ndarray") -> None:
        cv2 = _cv2()
        cv2.rectangle(
            canvas,
            (self.x, self.y),
            (self.x + self.w, self.y + self.h),
            _to_bgr(self.color),
            self.thickness,
        )


@dataclass
class Arrow:
    """Straight arrow from one point to another."""

    from_xy: tuple[int, int]
    to_xy: tuple[int, int]
    color: "str | ColorBGR" = "red"
    thickness: int = 3
    tip_length: float = 0.2

    def bounds(self) -> tuple[int, int, int, int]:
        x1, y1 = self.from_xy
        x2, y2 = self.to_xy
        x, w = (min(x1, x2), abs(x2 - x1))
        y, h = (min(y1, y2), abs(y2 - y1))
        return (x, y, w, h)

    def draw(self, canvas: "np.ndarray") -> None:
        cv2 = _cv2()
        cv2.arrowedLine(
            canvas,
            self.from_xy,
            self.to_xy,
            _to_bgr(self.color),
            self.thickness,
            tipLength=self.tip_length,
        )


@dataclass
class Callout:
    """Text balloon anchored at ``anchor_xy``."""

    anchor_xy: tuple[int, int]
    text: str
    bg_color: "str | ColorBGR" = "yellow"
    fg_color: "str | ColorBGR" = "black"
    padding: int = 8
    font_scale: float = 0.6
    thickness: int = 1

    def _measure(self) -> tuple[int, int, int]:
        """Return (text_w, text_h, baseline) — safe without cv2."""
        try:
            cv2 = _cv2()
        except RuntimeError:
            # Fallback heuristic: ~9px per character at scale=0.6.
            return (int(len(self.text) * self.font_scale * 15), int(self.font_scale * 25), 4)
        (tw, th), baseline = cv2.getTextSize(
            self.text,
            cv2.FONT_HERSHEY_SIMPLEX,
            self.font_scale,
            self.thickness,
        )
        return (tw, th, baseline)

    def bounds(self) -> tuple[int, int, int, int]:
        tw, th, baseline = self._measure()
        w = tw + 2 * self.padding
        h = th + baseline + 2 * self.padding
        return (self.anchor_xy[0], self.anchor_xy[1], w, h)

    def draw(self, canvas: "np.ndarray") -> None:
        cv2 = _cv2()
        x, y, w, h = self.bounds()
        cv2.rectangle(canvas, (x, y), (x + w, y + h), _to_bgr(self.bg_color), -1)
        cv2.rectangle(canvas, (x, y), (x + w, y + h), _to_bgr(self.fg_color), 1)
        _, th, baseline = self._measure()
        text_y = y + self.padding + th
        cv2.putText(
            canvas,
            self.text,
            (x + self.padding, text_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            self.font_scale,
            _to_bgr(self.fg_color),
            self.thickness,
            lineType=getattr(__import__("cv2"), "LINE_AA", 16),
        )


@dataclass
class Spotlight:
    """Dim the whole canvas, punch a hole revealing ``(x, y, w, h)``."""

    x: int
    y: int
    w: int
    h: int
    dim_alpha: float = 0.6
    border_color: "str | ColorBGR" = "red"
    border_thickness: int = 3

    def bounds(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.w, self.h)

    def draw(self, canvas: "np.ndarray") -> None:
        cv2 = _cv2()
        import numpy as np

        overlay = canvas.copy()
        overlay[:] = 0  # full black
        overlay[self.y : self.y + self.h, self.x : self.x + self.w] = canvas[
            self.y : self.y + self.h, self.x : self.x + self.w
        ]
        alpha = float(self.dim_alpha)
        cv2.addWeighted(overlay, alpha, canvas, 1 - alpha, 0, canvas)
        cv2.rectangle(
            canvas,
            (self.x, self.y),
            (self.x + self.w, self.y + self.h),
            _to_bgr(self.border_color),
            self.border_thickness,
        )
        _ = np  # keep the import referenced for linters


@dataclass
class Text:
    """Plain text label at a point."""

    xy: tuple[int, int]
    content: str
    color: "str | ColorBGR" = "white"
    font_scale: float = 0.6
    thickness: int = 1

    def bounds(self) -> tuple[int, int, int, int]:
        try:
            cv2 = _cv2()
            (tw, th), baseline = cv2.getTextSize(
                self.content,
                cv2.FONT_HERSHEY_SIMPLEX,
                self.font_scale,
                self.thickness,
            )
            return (self.xy[0], self.xy[1] - th, tw, th + baseline)
        except RuntimeError:
            # cv2-less fallback matches Callout._measure.
            return (
                self.xy[0],
                self.xy[1] - int(self.font_scale * 25),
                int(len(self.content) * self.font_scale * 15),
                int(self.font_scale * 30),
            )

    def draw(self, canvas: "np.ndarray") -> None:
        cv2 = _cv2()
        cv2.putText(
            canvas,
            self.content,
            self.xy,
            cv2.FONT_HERSHEY_SIMPLEX,
            self.font_scale,
            _to_bgr(self.color),
            self.thickness,
            lineType=getattr(cv2, "LINE_AA", 16),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cv2():
    try:
        import cv2  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - host without cv2
        raise RuntimeError("OpenCV (cv2) is required to draw guide shapes") from exc
    return cv2
