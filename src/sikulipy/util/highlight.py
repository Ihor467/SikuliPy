"""Port of ``Highlight.java`` — draw a coloured rectangle over a region.

Thin wrapper over :class:`sikulipy.guide.Guide`: one rectangle, shown
for a duration or until :meth:`close`. Supports context-manager usage::

    with Highlight(region, color="yellow", duration=0):
        do_work()
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sikulipy.guide import Guide

if TYPE_CHECKING:
    from sikulipy.core.region import Region


class Highlight:
    """Transient outlined rectangle over a :class:`Region`."""

    def __init__(
        self,
        region: "Region | tuple[int, int, int, int]",
        color: str = "red",
        duration: float = 2.0,
    ) -> None:
        self.region = region
        self.color = color
        self.duration = duration
        self._guide: Guide | None = None

    def show(self) -> "Highlight":
        guide = Guide().rectangle(self.region, color=self.color)
        # duration=0 means "indefinite" — caller must close().
        duration = self.duration if self.duration and self.duration > 0 else None
        guide.show(duration=duration)
        self._guide = guide
        return self

    def close(self) -> None:
        if self._guide is not None:
            self._guide.hide()
            self._guide = None

    def __enter__(self) -> "Highlight":
        return self.show()

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        self.close()
