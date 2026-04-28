"""Phase 9 step 1 — TargetSurface abstraction.

The desktop / android surfaces lazy-import cv2 / mss / adb so the
import-time tests don't require any of those extras. ``frame()`` and
``bounds()`` are exercised through ``_FakeSurface``; the real surfaces
are only checked for their static metadata (name, header lines).
"""

from __future__ import annotations

from sikulipy.ide.recorder import (
    RecorderAction,
    RecorderSession,
    TargetSurface,
    _AndroidSurface,
    _DesktopSurface,
    _FakeSurface,
    default_surface,
)


# ---------------------------------------------------------------------------
# Static metadata
# ---------------------------------------------------------------------------


def test_default_surface_is_desktop():
    s = default_surface()
    assert isinstance(s, _DesktopSurface)
    assert s.name == "desktop"
    # Desktop generator emits bare verbs; no setup line needed.
    assert s.header_setup() == []
    # Star-import keeps the existing recorder UX (`click(...)` works without
    # qualifying the module).
    assert "from sikulipy import *" in s.header_imports()


def test_target_surface_protocol_recognises_desktop_and_android():
    assert isinstance(_DesktopSurface(), TargetSurface)
    # _AndroidSurface needs a device, but the runtime_checkable Protocol
    # only inspects attribute presence — wire a tiny stub.
    class _Stub:
        serial = "abc"
        def screencap(self):
            raise NotImplementedError
        def size(self):
            return (1080, 1920)
    surf = _AndroidSurface(device=_Stub())
    assert isinstance(surf, TargetSurface)


def test_android_surface_header_setup_uses_serial_when_no_address():
    class _Stub:
        serial = "ABC123"
    surf = _AndroidSurface(device=_Stub())
    setup = surf.header_setup()
    assert setup == ['screen = ADBScreen.start(serial="ABC123")']
    imports = surf.header_imports()
    assert "from sikulipy.android.screen import ADBScreen" in imports


def test_android_surface_header_setup_uses_connect_for_address():
    class _Stub:
        serial = "192.168.1.5:5555"
    surf = _AndroidSurface(device=_Stub(), address="192.168.1.5:5555")
    setup = surf.header_setup()
    assert setup == ['screen = ADBScreen.connect("192.168.1.5:5555")']


def test_android_surface_falls_back_to_bare_start_without_serial():
    class _NoSerial:
        serial = None
    surf = _AndroidSurface(device=_NoSerial())
    assert surf.header_setup() == ["screen = ADBScreen.start()"]


# ---------------------------------------------------------------------------
# _FakeSurface
# ---------------------------------------------------------------------------


def test_fake_surface_records_frame_calls():
    sentinel = object()
    surf = _FakeSurface(_frame=sentinel, _bounds_value=(0, 0, 800, 600))
    assert surf.frame() is sentinel
    assert surf.frame() is sentinel
    assert surf.frame_calls == 2
    assert surf.bounds() == (0, 0, 800, 600)


def test_fake_surface_uses_explicit_imports_and_setup():
    surf = _FakeSurface(
        imports=["from sikulipy.android.screen import ADBScreen"],
        setup=["screen = ADBScreen.start()"],
    )
    assert "ADBScreen" in surf.header_imports()[0]
    assert surf.header_setup()[0].startswith("screen = ")


# ---------------------------------------------------------------------------
# RecorderSession integration
# ---------------------------------------------------------------------------


def test_recorder_session_default_surface_is_desktop():
    sess = RecorderSession()
    assert sess.surface.name == "desktop"


def test_recorder_session_set_surface_swaps_and_drops_lines():
    fake_dst = _FakeSurface(name="android")
    sess = RecorderSession()
    sess.record_payload(RecorderAction.TYPE, "hello")
    assert len(sess.lines()) == 1

    notified: list[None] = []
    sess.on_change = lambda: notified.append(None)
    sess.set_surface(fake_dst)
    assert sess.surface is fake_dst
    assert sess.lines() == []
    # set_surface fires on_change so the UI can repaint the preview.
    assert notified


def test_recorder_session_set_surface_can_keep_lines():
    fake_dst = _FakeSurface(name="android")
    sess = RecorderSession()
    sess.record_payload(RecorderAction.TYPE, "hello")
    sess.set_surface(fake_dst, drop_lines=False)
    assert sess.surface is fake_dst
    assert len(sess.lines()) == 1


def test_recorder_session_set_surface_idempotent_when_same():
    sess = RecorderSession()
    sess.record_payload(RecorderAction.TYPE, "hi")
    same = sess.surface
    sess.set_surface(same)  # no change
    assert len(sess.lines()) == 1
