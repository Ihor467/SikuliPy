"""Phase 9 step 3 — headless device-picker model.

These tests pin down the behavior the recorder bar relies on: the
picker always exposes a Desktop row, refresh tolerates a missing or
broken ADB stack, selecting a device swaps the session's surface, and
``connect_address`` wires up wireless devices. The UI layer is a thin
view over this module.
"""

from __future__ import annotations

import pytest

from sikulipy.ide.recorder import (
    DESKTOP_ENTRY_KEY,
    DeviceEntry,
    DevicePicker,
    RecorderSession,
    _AndroidSurface,
    _DesktopSurface,
)


# ---------------------------------------------------------------------------
# Stub ADB layer
# ---------------------------------------------------------------------------


class _StubDevice:
    def __init__(self, serial: str) -> None:
        self.serial = serial

    def size(self) -> tuple[int, int]:
        return (1080, 1920)

    def screencap(self):
        raise NotImplementedError


class _StubClient:
    def __init__(self, serials: list[str]) -> None:
        self._serials = list(serials)
        self.connect_calls: list[str] = []

    def devices(self) -> list[_StubDevice]:
        return [_StubDevice(s) for s in self._serials]

    def device(self, serial: str) -> _StubDevice:
        return _StubDevice(serial)

    def connect(self, address: str) -> _StubDevice:
        self.connect_calls.append(address)
        # ADB normalizes ``host`` to ``host:5555`` on connect.
        serial = address if ":" in address else f"{address}:5555"
        if serial not in self._serials:
            self._serials.append(serial)
        return _StubDevice(serial)


def _picker(serials: list[str]) -> tuple[DevicePicker, _StubClient]:
    client = _StubClient(serials)
    sess = RecorderSession()
    picker = DevicePicker(session=sess, client_factory=lambda: client)
    return picker, client


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------


def test_picker_starts_with_desktop_only_entry():
    picker, _ = _picker([])
    assert [e.key for e in picker.entries] == [DESKTOP_ENTRY_KEY]
    assert picker.selected_key == DESKTOP_ENTRY_KEY
    assert picker.session.surface.name == "desktop"


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------


def test_refresh_lists_attached_devices():
    picker, _ = _picker(["abc123", "192.168.1.5:5555"])
    entries = picker.refresh()
    keys = [e.key for e in entries]
    assert keys == [DESKTOP_ENTRY_KEY, "abc123", "192.168.1.5:5555"]
    assert "(wireless)" in entries[2].label
    assert picker.last_error is None


def test_refresh_swallows_adb_errors_and_records_message():
    sess = RecorderSession()

    def _broken_factory() -> object:
        raise RuntimeError("adb server not running")

    picker = DevicePicker(session=sess, client_factory=_broken_factory)
    entries = picker.refresh()
    assert [e.key for e in entries] == [DESKTOP_ENTRY_KEY]
    assert "adb" in picker.last_error.lower()


def test_refresh_falls_back_to_desktop_when_selected_device_disappears():
    picker, client = _picker(["abc123"])
    picker.refresh()
    picker.select("abc123")
    assert picker.session.surface.name == "android"
    # Device unplugged.
    client._serials.clear()
    picker.refresh()
    assert picker.selected_key == DESKTOP_ENTRY_KEY
    assert picker.session.surface.name == "desktop"


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def test_select_device_swaps_session_surface_to_android():
    picker, _ = _picker(["abc123"])
    picker.refresh()
    surf = picker.select("abc123")
    assert isinstance(surf, _AndroidSurface)
    assert picker.session.surface is surf
    assert picker.selected_key == "abc123"


def test_select_desktop_restores_desktop_surface():
    picker, _ = _picker(["abc123"])
    picker.refresh()
    picker.select("abc123")
    surf = picker.select(DESKTOP_ENTRY_KEY)
    assert isinstance(surf, _DesktopSurface)
    assert picker.session.surface.name == "desktop"


def test_select_unknown_key_raises():
    picker, _ = _picker([])
    with pytest.raises(KeyError):
        picker.select("nope")


def test_select_wireless_serial_passes_address_to_android_surface():
    picker, _ = _picker(["192.168.1.5:5555"])
    picker.refresh()
    surf = picker.select("192.168.1.5:5555")
    setup = surf.header_setup()
    assert setup == ['screen = ADBScreen.connect("192.168.1.5:5555")']


# ---------------------------------------------------------------------------
# connect_address
# ---------------------------------------------------------------------------


def test_connect_address_appends_default_port_and_selects_device():
    picker, client = _picker([])
    entry = picker.connect_address("192.168.1.5")
    assert client.connect_calls == ["192.168.1.5"]
    assert entry.serial == "192.168.1.5:5555"
    assert picker.selected_key == "192.168.1.5:5555"
    assert picker.session.surface.name == "android"


def test_connect_address_with_explicit_port():
    picker, client = _picker([])
    entry = picker.connect_address("10.0.0.4:5777")
    assert entry.serial == "10.0.0.4:5777"
    assert client.connect_calls == ["10.0.0.4:5777"]


def test_connect_address_rejects_empty():
    picker, _ = _picker([])
    with pytest.raises(ValueError):
        picker.connect_address("   ")


# ---------------------------------------------------------------------------
# Entry shape
# ---------------------------------------------------------------------------


def test_device_entry_is_hashable_and_frozen():
    e = DeviceEntry(key="abc", label="abc", serial="abc")
    # Frozen dataclass — hashable, immutable.
    assert hash(e) == hash(DeviceEntry(key="abc", label="abc", serial="abc"))
    with pytest.raises(Exception):
        e.label = "nope"  # type: ignore[misc]
