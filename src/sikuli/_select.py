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

    The returned Region remembers the full-screen bitmap grabbed for
    the overlay, so a subsequent ``region.text()`` or ``region.find()``
    crops from it instead of asking ``mss`` for a fresh grab. On KDE/X11
    a second grab often comes back as a black rectangle when the target
    window is an accelerated one kwin has unredirected (konsole,
    alacritty, kitty, video players); see ``Region._capture_bgr``.
    """
    del prompt  # reserved; not rendered by the overlay yet

    # Users typically call ``popup("please select...")`` right before us.
    # kdialog / zenity / Tk return the instant the OK button is clicked,
    # but the compositor still needs a frame or two to unmap the dialog
    # window and repaint the desktop underneath. Without this pause the
    # popup is still on screen when we grab, and it bakes itself into
    # the overlay's background (and therefore into any subsequent
    # region.text() capture).
    import time
    time.sleep(0.25)

    bg, mon = _grab_fullscreen()
    rect = _run_overlay(bg)
    if rect is None or rect.is_empty:
        return None
    # rect is in virtual-screen coordinates; Region expects the same.
    # mon["left"] / mon["top"] are usually 0 on a single-monitor setup,
    # but on multi-monitor layouts with a non-zero virtual origin we
    # want the absolute screen coord, which is what rect already carries.
    region = Region(x=rect.x, y=rect.y, w=rect.w, h=rect.h)

    # Attach the overlay's frozen screenshot so text() / find() don't
    # re-grab. bg is a PIL RGB image; convert to BGR ndarray for parity
    # with the rest of the capture pipeline.
    try:
        import numpy as np

        arr = np.array(bg)  # HxWx3 RGB
        if arr.ndim == 3 and arr.shape[2] == 3:
            arr = arr[:, :, ::-1]  # RGB -> BGR
        region._attach_frozen_bitmap(
            arr, origin_x=int(mon["left"]), origin_y=int(mon["top"])
        )
    except Exception:
        # If numpy/PIL conversion fails for any reason, fall back to
        # live mss grabs — recognition may still succeed on non-KDE
        # hosts.
        pass

    return region


__all__ = ["selectRegion"]
