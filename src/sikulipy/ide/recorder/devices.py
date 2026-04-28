"""Headless device-picker model for the recorder UI.

The Flet recorder bar wraps this with a Dropdown + Refresh + IP:PORT
text field. Keeping the logic here means the UI is a thin view we don't
have to drive in tests — and it lets the picker fall back gracefully
when ADB / pure-python-adb isn't installed (the desktop-only user case).

Two shapes the dialog needs:

* :class:`DeviceEntry` — a serial + label that the dropdown shows; the
  ``"desktop"`` entry stands for "stay on the desktop surface".
* :class:`DevicePicker` — owns a :class:`RecorderSession`, lists the
  attached ADB devices, and switches the session's surface in response
  to user picks. All ADB calls are wrapped so an import or connection
  error returns an empty list instead of raising.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from sikulipy.ide.recorder.session import RecorderSession
from sikulipy.ide.recorder.surface import (
    TargetSurface,
    _AndroidSurface,
    _DesktopSurface,
)


# The dropdown always shows desktop first; the value is reserved.
DESKTOP_ENTRY_KEY = "__desktop__"


@dataclass(frozen=True)
class DeviceEntry:
    """One row in the picker dropdown.

    ``key`` is the stable id the dropdown stores (serial for ADB
    devices, :data:`DESKTOP_ENTRY_KEY` for the desktop surface).
    ``label`` is what the user sees. ``serial`` is ``None`` for the
    desktop entry, otherwise the ADB device serial (``"abc123"`` for
    USB, ``"192.168.1.5:5555"`` for WiFi).
    """

    key: str
    label: str
    serial: str | None


def _desktop_entry() -> DeviceEntry:
    return DeviceEntry(key=DESKTOP_ENTRY_KEY, label="Desktop", serial=None)


# Type alias for the ADB-client factory. Tests pass a stub; the real
# UI passes ``ADBClient`` so the picker doesn't import the Android
# stack at module import time.
ClientFactory = Callable[[], object]


def _default_client_factory() -> object:
    """Return a fresh ``ADBClient``; deferred import so the recorder
    starts on machines without ``pure-python-adb`` installed."""
    from sikulipy.android import ADBClient

    return ADBClient()


@dataclass
class DevicePicker:
    """State container for the recorder's device dropdown."""

    session: RecorderSession
    client_factory: ClientFactory = _default_client_factory
    entries: list[DeviceEntry] = field(default_factory=list)
    selected_key: str = DESKTOP_ENTRY_KEY
    last_error: str | None = None

    def __post_init__(self) -> None:
        # Always start with the desktop row so the dropdown is never
        # empty even before the first refresh.
        self.entries = [_desktop_entry()]

    # ---- Refresh ---------------------------------------------------
    def refresh(self) -> list[DeviceEntry]:
        """Re-query attached ADB devices.

        Catches every exception so a missing ``pure-python-adb``,
        unreachable ADB server, or transient adb error doesn't crash
        the recorder — the dropdown just falls back to ``[Desktop]``
        and ``last_error`` carries the message for the status bar.
        """
        entries: list[DeviceEntry] = [_desktop_entry()]
        self.last_error = None
        try:
            client = self.client_factory()
            for dev in client.devices():
                serial = dev.serial
                entries.append(
                    DeviceEntry(
                        key=serial,
                        label=_format_label(serial),
                        serial=serial,
                    )
                )
        except Exception as exc:
            # Keep the desktop row; record the error so the UI can show
            # it next to the dropdown without raising.
            self.last_error = str(exc) or exc.__class__.__name__
        self.entries = entries
        # If the previously-selected device went away, fall back to
        # desktop so the session never points at a dead surface.
        if self.selected_key not in {e.key for e in entries}:
            self.select(DESKTOP_ENTRY_KEY)
        return list(entries)

    # ---- Selection -------------------------------------------------
    def select(self, key: str) -> TargetSurface:
        """Switch the recorder session to the surface for ``key``.

        ``key`` must come from one of the current :class:`DeviceEntry`
        rows. Selecting the desktop entry restores ``_DesktopSurface``;
        selecting a device entry connects ``_AndroidSurface`` to that
        serial. Lines previously recorded against a different surface
        are dropped (matches ``RecorderSession.set_surface`` default).
        """
        entry = self._find(key)
        if entry.serial is None:
            surf: TargetSurface = _DesktopSurface()
        else:
            surf = _make_android_surface(self.client_factory, entry.serial)
        self.selected_key = entry.key
        self.session.set_surface(surf)
        return surf

    def connect_address(self, address: str) -> DeviceEntry:
        """Connect ADB over TCP and select the resulting device.

        Used by the IP:PORT text field. The address can be ``host`` or
        ``host:port``; ADB defaults to ``5555`` when port is omitted.
        After a successful connect we refresh so the new device shows
        up in the dropdown, and we auto-select it.
        """
        address = address.strip()
        if not address:
            raise ValueError("connect address is empty")
        client = self.client_factory()
        device = client.connect(address)
        # Refresh first so the UI dropdown picks up the new entry, then
        # select by the real serial that the ADB server returned (which
        # may be normalized to ``host:5555``).
        self.refresh()
        serial = device.serial
        for entry in self.entries:
            if entry.serial == serial:
                self.select(entry.key)
                return entry
        # If the refresh didn't see it (race / mock client), still wire
        # the surface manually so the user isn't stuck on desktop.
        entry = DeviceEntry(key=serial, label=_format_label(serial), serial=serial)
        self.entries.append(entry)
        self.selected_key = entry.key
        self.session.set_surface(_AndroidSurface(device=device, address=address))
        return entry

    # ---- Internals -------------------------------------------------
    def _find(self, key: str) -> DeviceEntry:
        for entry in self.entries:
            if entry.key == key:
                return entry
        raise KeyError(f"unknown device entry: {key!r}")


def _make_android_surface(factory: ClientFactory, serial: str) -> TargetSurface:
    """Build an ``_AndroidSurface`` for ``serial`` via ``factory``.

    Wireless serials look like ``host:port`` — ``_AndroidSurface``'s
    ``header_setup`` uses that to pick ``ADBScreen.connect(...)`` over
    ``ADBScreen.start(serial=...)``.
    """
    client = factory()
    device = client.device(serial)
    address = serial if ":" in serial else None
    return _AndroidSurface(device=device, address=address)


def _format_label(serial: str) -> str:
    """Pretty label for the dropdown — ``serial (wireless)`` for ip:port,
    ``serial`` for everything else. Kept tiny so the UI can show the
    label inline next to a tiny status dot."""
    if ":" in serial:
        return f"{serial} (wireless)"
    return serial
