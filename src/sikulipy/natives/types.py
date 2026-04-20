"""Shared data types for the :mod:`sikulipy.natives` subsystem."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WindowInfo:
    """Immutable description of an OS window.

    ``bounds`` is ``(x, y, w, h)`` in screen coordinates.  Represented
    as a tuple rather than :class:`~sikulipy.core.region.Region` so this
    module stays free of numpy/opencv imports — ``App`` converts on
    demand.
    """

    pid: int
    title: str
    bounds: tuple[int, int, int, int]
    handle: int | None = None

    @property
    def x(self) -> int:
        return self.bounds[0]

    @property
    def y(self) -> int:
        return self.bounds[1]

    @property
    def w(self) -> int:
        return self.bounds[2]

    @property
    def h(self) -> int:
        return self.bounds[3]


class NotSupportedError(RuntimeError):
    """Raised by the null backend when the host offers no window manager."""
