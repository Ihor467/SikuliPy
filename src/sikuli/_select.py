"""``selectRegion`` — interactive region picker for user scripts.

SikuliX's ``selectRegion(prompt)`` minimises the IDE, shows a
drag-rectangle overlay over the whole desktop, and returns the chosen
area as a :class:`Region`. We already have the overlay implemented for
the IDE's Capture button (:mod:`sikulipy.ide.capture_overlay`); this
wrapper just reuses it and skips the "save a PNG" tail.
"""

from __future__ import annotations

from sikulipy.core.region import Region
from sikulipy.ide.capture_overlay import _grab_fullscreen, _run_overlay


def selectRegion(prompt: str = "Select a region") -> Region | None:  # noqa: N802 - SikuliX parity
    """Drag out a rectangle over the desktop; return a :class:`Region` or ``None``.

    ``prompt`` is accepted for SikuliX parity but currently unused by
    the overlay (the overlay only shows the frozen screenshot with a
    crosshair). Pass an informational :func:`popup` before calling
    :func:`selectRegion` if you need to brief the user.
    """
    del prompt  # reserved; not rendered by the overlay yet
    bg, mon = _grab_fullscreen()
    rect = _run_overlay(bg)
    if rect is None or rect.is_empty:
        return None
    # rect is in virtual-screen coordinates; Region expects the same.
    # mon["left"] / mon["top"] are usually 0 on a single-monitor setup,
    # but on multi-monitor layouts with a non-zero virtual origin we
    # want the absolute screen coord, which is what rect already carries.
    del mon
    return Region(x=rect.x, y=rect.y, w=rect.w, h=rect.h)


__all__ = ["selectRegion"]
