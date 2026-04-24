"""End-to-end drag-and-drop integration tests.

Paint a draggable Tk rectangle, drive the real pynput-backed ``Mouse``
through ``Mouse.drag_drop`` / ``Region.drag_drop``, then assert the
window's own event handlers saw a press + motion + release and the
shape ended up where we aimed.

Skipped whenever a display / Tk / pynput isn't available. These tests
move the real pointer, so do not run them on a shared desktop while
you're trying to use it.
"""

from __future__ import annotations

import os

import pytest

if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
    pytest.skip("no display available", allow_module_level=True)

pytest.importorskip("pynput")

try:
    import tkinter as tk  # noqa: F401
except Exception as exc:  # pragma: no cover - host dependent
    pytest.skip(f"tkinter unavailable: {exc}", allow_module_level=True)

import time  # noqa: E402

from sikulipy.core.location import Location  # noqa: E402
from sikulipy.core.mouse import Mouse  # noqa: E402
from sikulipy.core.screen import Screen  # noqa: E402


WINDOW_X = 60
WINDOW_Y = 80
WINDOW_W = 520
WINDOW_H = 360

# Initial rectangle position inside the window.
RECT_X = 80
RECT_Y = 80
RECT_W = 100
RECT_H = 100


class _DraggableCanvas:
    """Tk canvas with a single draggable rectangle.

    We bind press/motion/release on the rectangle itself so we get native
    Tk events as the real OS pointer moves over it. The canvas records
    each event, which the tests then inspect.
    """

    def __init__(self, root):
        self.root = root
        self.canvas = tk.Canvas(
            root, width=WINDOW_W, height=WINDOW_H,
            bg="white", highlightthickness=0,
        )
        self.canvas.pack()
        self.rect_id = self.canvas.create_rectangle(
            RECT_X, RECT_Y, RECT_X + RECT_W, RECT_Y + RECT_H,
            fill="#e04040", outline="",
        )
        self.events: list[tuple[str, int, int]] = []
        self._drag_anchor: tuple[int, int] | None = None

        self.canvas.tag_bind(self.rect_id, "<ButtonPress-1>", self._on_press)
        self.canvas.tag_bind(self.rect_id, "<B1-Motion>", self._on_motion)
        self.canvas.tag_bind(self.rect_id, "<ButtonRelease-1>", self._on_release)

    # --- handlers -----------------------------------------------------
    def _on_press(self, ev):
        self.events.append(("press", ev.x, ev.y))
        self._drag_anchor = (ev.x, ev.y)

    def _on_motion(self, ev):
        self.events.append(("motion", ev.x, ev.y))
        if self._drag_anchor is None:
            return
        dx = ev.x - self._drag_anchor[0]
        dy = ev.y - self._drag_anchor[1]
        self.canvas.move(self.rect_id, dx, dy)
        self._drag_anchor = (ev.x, ev.y)

    def _on_release(self, ev):
        self.events.append(("release", ev.x, ev.y))
        self._drag_anchor = None

    # --- queries ------------------------------------------------------
    def rect_bbox(self) -> tuple[int, int, int, int]:
        """Current rectangle bbox in window-local coords: (x1, y1, x2, y2)."""
        x1, y1, x2, y2 = self.canvas.coords(self.rect_id)
        return int(x1), int(y1), int(x2), int(y2)

    def rect_center_abs(self) -> tuple[int, int]:
        x1, y1, x2, y2 = self.rect_bbox()
        ox, oy = _window_origin(self.root)
        return ox + (x1 + x2) // 2, oy + (y1 + y2) // 2

    def pump(self, seconds: float = 0.1) -> None:
        """Process Tk events for a while so pointer input gets delivered."""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.root.update()
            time.sleep(0.01)


def _window_origin(root) -> tuple[int, int]:
    root.update_idletasks()
    return int(root.winfo_rootx()), int(root.winfo_rooty())


@pytest.fixture(scope="module")
def tk_root():
    root = tk.Tk()
    root.geometry(f"{WINDOW_W}x{WINDOW_H}+{WINDOW_X}+{WINDOW_Y}")
    root.title("sikulipy-integration-drag")
    try:
        root.attributes("-topmost", True)
    except tk.TclError:
        pass
    root.update_idletasks()
    root.update()
    time.sleep(0.3)
    yield root
    try:
        root.destroy()
    except tk.TclError:
        pass


@pytest.fixture
def canvas(tk_root):
    for child in list(tk_root.winfo_children()):
        child.destroy()
    tk_root.update_idletasks()
    tk_root.update()
    c = _DraggableCanvas(tk_root)
    tk_root.update_idletasks()
    tk_root.update()
    time.sleep(0.2)
    yield c


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_mouse_drag_drop_moves_rectangle(canvas):
    """``Mouse.drag_drop`` (low level) should press, drag, release such
    that the Tk rectangle both fires the full event sequence and ends up
    translated by (dx, dy)."""
    ox, oy = _window_origin(canvas.root)
    start_abs = (ox + RECT_X + RECT_W // 2, oy + RECT_Y + RECT_H // 2)
    delta = (120, 80)
    end_abs = (start_abs[0] + delta[0], start_abs[1] + delta[1])

    Mouse.drag_drop(Location(*start_abs), Location(*end_abs))
    canvas.pump(0.4)  # let Tk drain the X motion events

    kinds = [e[0] for e in canvas.events]
    assert "press" in kinds, f"press not received: {canvas.events}"
    assert "motion" in kinds, f"no motion received: {canvas.events}"
    assert "release" in kinds, f"release not received: {canvas.events}"
    # press must come before release, with at least one motion between.
    press_idx = kinds.index("press")
    release_idx = len(kinds) - 1 - kinds[::-1].index("release")
    assert press_idx < release_idx
    assert any(k == "motion" for k in kinds[press_idx + 1: release_idx])

    x1, y1, x2, y2 = canvas.rect_bbox()
    # The press handler re-anchors drag to the click point, so the rect
    # follows the cursor 1:1. Allow a few pixels slop for WM quirks.
    assert abs(x1 - (RECT_X + delta[0])) <= 4, f"x1={x1}"
    assert abs(y1 - (RECT_Y + delta[1])) <= 4, f"y1={y1}"
    assert (x2 - x1, y2 - y1) == (RECT_W, RECT_H)


def test_region_drag_drop_between_locations(canvas):
    """``Region.drag_drop`` with two ``Location`` targets should drive
    the same drag as the low-level ``Mouse.drag_drop``."""
    ox, oy = _window_origin(canvas.root)
    start_abs = Location(ox + RECT_X + RECT_W // 2, oy + RECT_Y + RECT_H // 2)
    end_abs = Location(start_abs.x + 60, start_abs.y + 140)

    Screen.get_primary().drag_drop(start_abs, end_abs)
    canvas.pump(0.4)

    kinds = [e[0] for e in canvas.events]
    assert kinds.count("press") >= 1
    assert kinds.count("release") >= 1

    x1, y1, _x2, _y2 = canvas.rect_bbox()
    assert abs(x1 - (RECT_X + 60)) <= 4
    assert abs(y1 - (RECT_Y + 140)) <= 4
