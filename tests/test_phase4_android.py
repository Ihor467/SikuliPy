"""Phase 4 tests — ADBDevice / ADBScreen against a fake backend.

A ``FakeAdbDevice`` records every shell command it is asked to run and
returns preset replies (e.g. a canned ``wm size`` output). No real
adb-server or device is needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from sikulipy.android import ADBClient, ADBDevice, ADBScreen, set_client
from sikulipy.android._backend import AdbDeviceBackend
from sikulipy.core.location import Location
from sikulipy.core.match import Match
from sikulipy.core.region import Region


@dataclass
class FakeAdbDevice(AdbDeviceBackend):
    _serial: str = "FAKE-0001"
    size_output: str = "Physical size: 1080x2400"
    shell_calls: list[str] = field(default_factory=list)
    shell_replies: dict[str, str] = field(default_factory=dict)
    png_bytes: bytes = b""

    @property
    def serial(self) -> str:
        return self._serial

    def shell(self, cmd: str) -> str:
        self.shell_calls.append(cmd)
        if cmd == "wm size":
            return self.size_output
        return self.shell_replies.get(cmd, "")

    def screencap_png(self) -> bytes:
        return self.png_bytes


@dataclass
class FakeAdbClient:
    dev: FakeAdbDevice

    def devices(self):
        return [self.dev]

    def device(self, serial: str | None = None):
        return self.dev

    def connect(self, address: str) -> None:  # noqa: ARG002
        pass


@pytest.fixture
def fake_device():
    dev = FakeAdbDevice()
    set_client(FakeAdbClient(dev))
    yield dev
    set_client(None)


# -----------------------------------------------------------------------------
# ADBClient / ADBDevice
# -----------------------------------------------------------------------------


def test_client_lists_devices(fake_device):
    devices = ADBClient().devices()
    assert len(devices) == 1
    assert devices[0].serial == "FAKE-0001"


def test_device_size_parses_wm_size(fake_device):
    assert ADBClient().device().size() == (1080, 2400)
    # Second call is cached — no extra shell call.
    ADBClient().device().size()


def test_device_size_raises_on_bad_output(fake_device):
    fake_device.size_output = "weird garbage"
    with pytest.raises(RuntimeError):
        ADBClient().device().size()


def test_device_tap_builds_shell_command(fake_device):
    ADBClient().device().tap(123, 456)
    assert "input tap 123 456" in fake_device.shell_calls


def test_device_swipe_with_duration(fake_device):
    ADBClient().device().swipe(10, 20, 300, 400, duration_ms=250)
    assert "input swipe 10 20 300 400 250" in fake_device.shell_calls


def test_device_long_press_is_swipe_in_place(fake_device):
    ADBClient().device().long_press(50, 60, duration_ms=1500)
    assert "input swipe 50 60 50 60 1500" in fake_device.shell_calls


def test_device_input_text_replaces_spaces(fake_device):
    ADBClient().device().input_text("hello world")
    # Android's `input text` needs `%s` for spaces.
    assert any("input text" in c and "hello%sworld" in c for c in fake_device.shell_calls)


def test_device_input_text_shell_quotes_specials(fake_device):
    ADBClient().device().input_text("a$b&c")
    # shlex.quote wraps in single quotes when specials are present.
    cmd = next(c for c in fake_device.shell_calls if c.startswith("input text"))
    assert "'a$b&c'" in cmd


def test_device_key_event(fake_device):
    ADBClient().device().key_event(66)  # KEYCODE_ENTER
    assert "input keyevent 66" in fake_device.shell_calls


# -----------------------------------------------------------------------------
# ADBScreen
# -----------------------------------------------------------------------------


def test_screen_start_populates_region_from_size(fake_device):
    screen = ADBScreen.start()
    assert isinstance(screen, Region)
    assert (screen.x, screen.y, screen.w, screen.h) == (0, 0, 1080, 2400)


def test_screen_click_location_dispatches_tap(fake_device):
    screen = ADBScreen.start()
    screen.click(Location(100, 200))
    assert "input tap 100 200" in fake_device.shell_calls


def test_screen_click_none_taps_centre(fake_device):
    screen = ADBScreen.start()
    screen.click()
    # centre of 1080x2400 is (540, 1200)
    assert "input tap 540 1200" in fake_device.shell_calls


def test_screen_double_click_taps_twice(fake_device):
    ADBScreen.start().click(Location(10, 10))
    # One tap so far; now double-click another point:
    ADBScreen.start().double_click(Location(20, 20))
    taps = [c for c in fake_device.shell_calls if c.startswith("input tap 20 20")]
    assert len(taps) == 2


def test_screen_right_click_is_long_press(fake_device):
    ADBScreen.start().right_click(Location(30, 40))
    assert "input swipe 30 40 30 40 1000" in fake_device.shell_calls


def test_screen_drag_drop_dispatches_swipe(fake_device):
    ADBScreen.start().drag_drop(Location(10, 20), Location(300, 500), duration_ms=450)
    assert "input swipe 10 20 300 500 450" in fake_device.shell_calls


def test_screen_type_dispatches_input_text(fake_device):
    ADBScreen.start().type("hi there")
    assert any("hi%sthere" in c for c in fake_device.shell_calls)


def test_screen_click_pattern_finds_then_taps(fake_device, monkeypatch):
    """Pattern target: find() is consulted, target_offset applied, ADB tap executed."""
    from sikulipy.core.pattern import Pattern

    screen = ADBScreen.start()
    sentinel = Match(x=500, y=600, w=40, h=20, score=0.99)
    monkeypatch.setattr(ADBScreen, "find", lambda self, target: sentinel)

    screen.click(Pattern(image="btn.png").targetOffset(3, 4))
    # centre (520, 610) + offset (3, 4) -> (523, 614)
    assert "input tap 523 614" in fake_device.shell_calls


def test_screen_find_text_coordinates_uses_ocr(fake_device, monkeypatch):
    """ADBScreen.find_text_coordinates wraps OCR.find_text."""
    from sikulipy.ocr import Word
    import sikulipy.android.screen as screen_mod

    class _OCR:
        @staticmethod
        def find_text(image, needle):
            assert needle == "Validate"
            return Word(text="Validate", x=50, y=60, w=80, h=24, confidence=0.99)

    # Monkeypatch the OCR module attribute the method imports locally.
    import sikulipy.ocr as ocr_mod

    monkeypatch.setattr(ocr_mod, "OCR", _OCR)
    # Also bypass the screen capture path entirely.
    monkeypatch.setattr(screen_mod.ADBScreen, "_capture_bgr", lambda self: b"fake")

    coords = ADBScreen.start().find_text_coordinates("Validate")
    assert coords == (50, 60, 80, 24)
