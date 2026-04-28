"""Phase 9 step 4 — capture overlay frame_provider.

The Tk overlay itself is interactive (drag a rectangle), so we don't
exercise it here. What this module pins down is the ``FrameProvider``
bridge: given a :class:`TargetSurface`, ``surface_frame_provider``
must hand the overlay a PIL image plus the matching virtual-bounds
dict so the post-overlay crop logic still works.

Skips when ``cv2`` / ``numpy`` / ``PIL`` aren't installed — those are
optional extras and the recorder still works on machines without them
as long as the user stays on the desktop surface.
"""

from __future__ import annotations

import pytest

# These extras are optional; skip cleanly so CI on slim envs stays green.
np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")
PIL_Image = pytest.importorskip("PIL.Image")

from sikulipy.ide.capture_overlay import surface_frame_provider
from sikulipy.ide.recorder import _DesktopSurface, _FakeSurface


def _bgr_test_frame(width: int, height: int) -> "np.ndarray":
    # Solid-blue BGR frame; concrete enough to verify the channel order.
    arr = np.zeros((height, width, 3), dtype=np.uint8)
    arr[:, :, 0] = 255  # B channel
    return arr


def test_surface_frame_provider_returns_pil_image_and_bounds():
    surf = _FakeSurface(name="android", _frame=_bgr_test_frame(64, 32))
    provide = surface_frame_provider(surf)
    img, mon = provide()
    assert img.size == (64, 32)
    # Android coordinates start at (0, 0) — overlay relies on that
    # offset to translate the drag rect back into device space.
    assert mon == {"left": 0, "top": 0, "width": 64, "height": 32}


def test_surface_frame_provider_converts_bgr_to_rgb():
    """The surface returns BGR; the overlay (and PIL) need RGB."""
    surf = _FakeSurface(name="android", _frame=_bgr_test_frame(2, 2))
    img, _ = surface_frame_provider(surf)()
    # BGR (255, 0, 0) → RGB (0, 0, 255). Pixel at (0,0) should be blue.
    r, g, b = img.getpixel((0, 0))[:3]
    assert (r, g, b) == (0, 0, 255)


def test_surface_frame_provider_invokes_surface_each_call():
    """Each pattern capture must grab a fresh frame — the user may
    have changed the device screen between two recorded steps."""
    surf = _FakeSurface(name="android", _frame=_bgr_test_frame(8, 8))
    provide = surface_frame_provider(surf)
    provide()
    provide()
    provide()
    assert surf.frame_calls == 3


def test_surface_frame_provider_for_desktop_uses_mss_grab(monkeypatch):
    """A desktop surface must NOT route through ``surface.frame()`` —
    we want the virtual-screen union (multi-monitor) and the existing
    mss path, not the lazy single-monitor BGR conversion."""
    sentinel_img = PIL_Image.new("RGB", (4, 4))
    sentinel_mon = {"left": -1920, "top": 0, "width": 3840, "height": 1080}

    def _fake_grab():
        return sentinel_img, sentinel_mon

    monkeypatch.setattr(
        "sikulipy.ide.capture_overlay._grab_fullscreen", _fake_grab
    )
    provide = surface_frame_provider(_DesktopSurface())
    img, mon = provide()
    assert img is sentinel_img
    assert mon is sentinel_mon
