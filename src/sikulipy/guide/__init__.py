"""Visual guides / overlays — port of ``org.sikuli.guide``.

The Java version was a large Swing package (``SxArrow``, ``SxCallout``,
``SxSpotlight``, ...) drawing directly onto a transparent window. Our
port keeps the same composition model but splits responsibilities:

* :mod:`sikulipy.guide.shapes` — pure geometric dataclasses
  (:class:`Arrow`, :class:`Rectangle`, :class:`Callout`, :class:`Spotlight`,
  :class:`Text`) with :meth:`Shape.draw` painting onto a BGR canvas.
* :mod:`sikulipy.guide._backend` — swappable rendering backend (default
  Flet frameless window; null backend for tests).
* :class:`Guide` (this module) — fluent builder that accumulates shapes
  and dispatches :meth:`show` / :meth:`hide` through the backend.

Example::

    from sikulipy.guide import Guide

    g = Guide()
    g.arrow((100, 100), (200, 200), color="yellow")
    g.callout((220, 200), "Click here")
    g.spotlight(region)
    g.show(duration=3.0)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sikulipy.guide._backend import (
    GuideBackend,
    get_backend,
    set_backend,
)
from sikulipy.guide.shapes import (
    Arrow,
    Callout,
    ColorBGR,
    Rectangle,
    Shape,
    Spotlight,
    Text,
)

if TYPE_CHECKING:
    from sikulipy.core.region import Region


@dataclass
class Guide:
    """Composable set of shapes rendered as a single overlay."""

    shapes: list[Shape] = field(default_factory=list)

    # ---- Builders --------------------------------------------------
    def arrow(
        self,
        from_xy: tuple[int, int],
        to_xy: tuple[int, int],
        *,
        color: "str | ColorBGR" = "red",
        thickness: int = 3,
    ) -> "Guide":
        self.shapes.append(Arrow(from_xy, to_xy, color=color, thickness=thickness))
        return self

    def rectangle(
        self,
        region: "Region | tuple[int, int, int, int]",
        *,
        color: "str | ColorBGR" = "red",
        thickness: int = 3,
    ) -> "Guide":
        x, y, w, h = _region_tuple(region)
        self.shapes.append(Rectangle(x, y, w, h, color=color, thickness=thickness))
        return self

    def callout(
        self,
        anchor_xy: tuple[int, int],
        text: str,
        *,
        bg_color: "str | ColorBGR" = "yellow",
        fg_color: "str | ColorBGR" = "black",
    ) -> "Guide":
        self.shapes.append(
            Callout(anchor_xy=anchor_xy, text=text, bg_color=bg_color, fg_color=fg_color)
        )
        return self

    def spotlight(
        self,
        region: "Region | tuple[int, int, int, int]",
        *,
        dim_alpha: float = 0.6,
        border_color: "str | ColorBGR" = "red",
    ) -> "Guide":
        x, y, w, h = _region_tuple(region)
        self.shapes.append(
            Spotlight(
                x=x, y=y, w=w, h=h, dim_alpha=dim_alpha, border_color=border_color
            )
        )
        return self

    def text(
        self,
        xy: tuple[int, int],
        content: str,
        *,
        color: "str | ColorBGR" = "white",
    ) -> "Guide":
        self.shapes.append(Text(xy=xy, content=content, color=color))
        return self

    def clear(self) -> "Guide":
        self.shapes.clear()
        return self

    # ---- Rendering -------------------------------------------------
    def show(self, *, duration: float | None = None) -> None:
        get_backend().show(self.shapes, duration=duration)

    def hide(self) -> None:
        get_backend().hide()

    def is_visible(self) -> bool:
        return get_backend().is_visible()


def _region_tuple(
    region: "Region | tuple[int, int, int, int]",
) -> tuple[int, int, int, int]:
    if isinstance(region, tuple):
        if len(region) != 4:
            raise ValueError("region tuple must be (x, y, w, h)")
        return tuple(int(v) for v in region)  # type: ignore[return-value]
    return (int(region.x), int(region.y), int(region.w), int(region.h))


__all__ = [
    "Arrow",
    "Callout",
    "Guide",
    "GuideBackend",
    "Rectangle",
    "Shape",
    "Spotlight",
    "Text",
    "get_backend",
    "set_backend",
]
