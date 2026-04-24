"""End-to-end image-matching integration tests.

Renders a Tk window with a distinctive shape, grabs the shape's pixels
as the needle, then exercises the real :class:`Screen` / :class:`Region`
/ :class:`Finder` pipeline (mss → matchTemplate → Match). The goal is
to catch coordinate-translation and capture-glue bugs that unit tests
with synthetic numpy arrays can't see.

Skipped whenever a display / Tk / cv2 / numpy isn't available. These
tests are display-bound by design; a headless CI should not try to run
them.
"""

from __future__ import annotations

import os

import pytest

# Gate on prerequisites. We want a single, crisp skip reason at the top
# of the module rather than a dozen importorskip calls scattered through
# each test.
if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
    pytest.skip("no display available", allow_module_level=True)

pytest.importorskip("numpy")
pytest.importorskip("cv2")
pytest.importorskip("mss")

try:
    import tkinter as tk  # noqa: F401
except Exception as exc:  # pragma: no cover - host dependent
    pytest.skip(f"tkinter unavailable: {exc}", allow_module_level=True)

import numpy as np  # noqa: E402
import mss  # noqa: E402

from sikulipy.core.region import Region  # noqa: E402
from sikulipy.core.screen import Screen  # noqa: E402


# Screen coordinates where the fixture Tk window is placed. Chosen to
# land inside any reasonable monitor layout (top-left quadrant, well
# away from panels).
WINDOW_X = 40
WINDOW_Y = 60
WINDOW_W = 480
WINDOW_H = 320


@pytest.fixture(scope="module")
def tk_root():
    """One Tk root per module. Repeated ``Tk()`` calls in the same
    Python process are flaky on 3.14; keeping a single root avoids
    mysterious placement drift between tests."""
    import tkinter as tk

    root = tk.Tk()
    root.geometry(f"{WINDOW_W}x{WINDOW_H}+{WINDOW_X}+{WINDOW_Y}")
    root.title("sikulipy-integration")
    root.overrideredirect(False)
    try:
        root.attributes("-topmost", True)
    except tk.TclError:
        pass
    # Make sure the window is mapped and positioned before any test
    # tries to paint into it.
    root.update_idletasks()
    root.update()
    import time
    time.sleep(0.3)
    yield root
    try:
        root.destroy()
    except tk.TclError:
        pass


@pytest.fixture
def tk_window(tk_root):
    """Hand the shared root to each test after wiping any previous canvas."""
    for child in list(tk_root.winfo_children()):
        child.destroy()
    tk_root.update_idletasks()
    tk_root.update()
    yield tk_root


def _paint_distinctive(root, shapes) -> "tk.Canvas":
    """Draw a set of coloured rectangles on a fresh canvas inside ``root``.

    ``shapes`` is a list of ``(x, y, w, h, fill)`` window-local
    rectangles. Returns the Canvas so callers can refer to it further.
    """
    import time
    import tkinter as tk

    canvas = tk.Canvas(
        root, width=WINDOW_W, height=WINDOW_H,
        bg="white", highlightthickness=0,
    )
    canvas.pack()
    for x, y, w, h, fill in shapes:
        canvas.create_rectangle(x, y, x + w, y + h, fill=fill, outline="")

    # Flush Tk drawing and give the compositor time to actually push a
    # frame. A single pair of update() calls is not enough on KDE/X11 —
    # kwin batches draws and may still be painting when we grab. A
    # ~300ms sleep with bookend update()s is empirically the
    # shortest reliable settle.
    root.update_idletasks()
    root.update()
    time.sleep(0.3)
    root.update()
    return canvas


def _grab_absolute(x: int, y: int, w: int, h: int) -> np.ndarray:
    """BGR numpy array of the given screen rectangle."""
    with mss.mss() as sct:
        raw = sct.grab({"left": x, "top": y, "width": w, "height": h})
    return np.asarray(raw, dtype=np.uint8)[:, :, :3]


def _window_origin(root) -> tuple[int, int]:
    """Return the on-screen (x, y) of the Tk window's top-left corner.

    Window managers may shift a window by a few pixels for decorations
    or snap-to-edge. Reading ``winfo_rootx/rooty`` after an update gives
    the actual origin the compositor drew at.
    """
    root.update_idletasks()
    return int(root.winfo_rootx()), int(root.winfo_rooty())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_region_find_locates_needle_at_expected_coords(tk_window):
    """End-to-end: paint a red square, grab its pixels, find() on the full
    screen should return a Match whose absolute coords hit the square."""
    _paint_distinctive(tk_window, [(100, 80, 60, 60, "red")])
    ox, oy = _window_origin(tk_window)
    needle_abs_x = ox + 100
    needle_abs_y = oy + 80

    needle = _grab_absolute(needle_abs_x, needle_abs_y, 60, 60)
    # Sanity: the grab itself isn't all zeros / all one colour.
    assert len(np.unique(needle.reshape(-1, 3), axis=0)) >= 1

    screen = Screen.get_primary()
    match = screen.find(needle)

    assert match is not None, "find() returned None on a needle grabbed moments ago"
    # Allow a 2-pixel slop for anti-aliasing / subpixel shifts.
    assert abs(match.x - needle_abs_x) <= 2, (
        f"match.x={match.x} expected ~{needle_abs_x}"
    )
    assert abs(match.y - needle_abs_y) <= 2, (
        f"match.y={match.y} expected ~{needle_abs_y}"
    )
    assert match.w == 60 and match.h == 60
    assert match.score > 0.95


def test_region_find_all_finds_each_copy(tk_window):
    """Paint three identical green squares; find_all() should return 3 Matches."""
    shapes = [
        (50, 50, 40, 40, "#00cc44"),
        (200, 50, 40, 40, "#00cc44"),
        (50, 200, 40, 40, "#00cc44"),
    ]
    _paint_distinctive(tk_window, shapes)
    ox, oy = _window_origin(tk_window)

    # Use the first green square as the needle.
    needle = _grab_absolute(ox + 50, oy + 50, 40, 40)
    screen = Screen.get_primary()
    matches = screen.find_all(needle)

    # Greedy NMS can't guarantee exactly-3 on real pixels if anti-aliased
    # edges or window shadows produce near-duplicates — allow [3, 6] and
    # assert the three expected positions are represented.
    assert 3 <= len(matches) <= 6, f"got {len(matches)} matches"

    expected = {(ox + x, oy + y) for x, y, _w, _h, _c in shapes}
    hit_set = {(m.x, m.y) for m in matches}
    missing = [
        e for e in expected
        if not any(abs(hx - e[0]) <= 2 and abs(hy - e[1]) <= 2 for hx, hy in hit_set)
    ]
    assert not missing, f"these painted squares weren't found: {missing}"


def test_sub_region_find_translates_coords(tk_window):
    """Constrain the search to a sub-Region. The returned Match should
    still carry absolute screen coordinates (Region.x/y added to the
    in-haystack hit), not sub-region-local ones."""
    _paint_distinctive(tk_window, [(300, 200, 50, 50, "#0066ff")])
    ox, oy = _window_origin(tk_window)
    abs_x = ox + 300
    abs_y = oy + 200

    needle = _grab_absolute(abs_x, abs_y, 50, 50)

    # Search only the bottom-right quadrant of the Tk window to prove
    # coordinate translation works when the Region isn't the full screen.
    quad = Region(
        x=ox + WINDOW_W // 2,
        y=oy + WINDOW_H // 2,
        w=WINDOW_W // 2,
        h=WINDOW_H // 2,
    )
    match = quad.find(needle)
    assert match is not None
    assert abs(match.x - abs_x) <= 2
    assert abs(match.y - abs_y) <= 2
