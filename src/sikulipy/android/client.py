"""ADB client/device wrappers — port of ADBClient.java + ADBDevice.java + ADBRobot.java."""

from __future__ import annotations

import re
import shlex
from typing import TYPE_CHECKING

from sikulipy.android._backend import AdbDeviceBackend, get_client

if TYPE_CHECKING:
    from sikulipy.core.image import ScreenImage


_WM_SIZE_RE = re.compile(r"(?:Override|Physical)\s+size:\s*(\d+)\s*x\s*(\d+)", re.IGNORECASE)


class ADBClient:
    """Thin wrapper around the active ADB backend (pure-python-adb by default)."""

    def __init__(self, host: str = "127.0.0.1", port: int = 5037) -> None:
        self._client = get_client(host=host, port=port)

    def devices(self) -> list["ADBDevice"]:
        return [ADBDevice(backend=d) for d in self._client.devices()]

    def device(self, serial: str | None = None) -> "ADBDevice":
        return ADBDevice(backend=self._client.device(serial))

    def connect(self, address: str) -> "ADBDevice":
        """Connect over TCP (WiFi ADB) and return the resulting device."""
        self._client.connect(address)
        serial = address if ":" in address else f"{address}:5555"
        return self.device(serial)


class ADBDevice:
    """An Android device driven over ADB.

    Mirrors the subset of ADBDevice.java + ADBRobot.java that matters for
    automation: ``tap``, ``swipe``, ``input_text``, ``key_event``, ``shell``,
    ``screencap``, ``size``.
    """

    def __init__(self, backend: AdbDeviceBackend) -> None:
        self._backend = backend
        self._size: tuple[int, int] | None = None

    # ---- Introspection ---------------------------------------------
    @property
    def serial(self) -> str:
        return self._backend.serial

    def shell(self, cmd: str) -> str:
        return self._backend.shell(cmd)

    def size(self) -> tuple[int, int]:
        """Return (width, height) in pixels, cached after first query."""
        if self._size is None:
            out = self.shell("wm size")
            m = _WM_SIZE_RE.search(out or "")
            if not m:
                raise RuntimeError(f"could not parse 'wm size' output: {out!r}")
            self._size = (int(m.group(1)), int(m.group(2)))
        return self._size

    # ---- Input -----------------------------------------------------
    def tap(self, x: int, y: int) -> None:
        self.shell(f"input tap {int(x)} {int(y)}")

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        self.shell(
            f"input swipe {int(x1)} {int(y1)} {int(x2)} {int(y2)} {int(duration_ms)}"
        )

    def long_press(self, x: int, y: int, duration_ms: int = 1000) -> None:
        # Android's ``input swipe`` with same start/end acts as a long press.
        self.swipe(x, y, x, y, duration_ms=duration_ms)

    def input_text(self, text: str) -> None:
        """Type ``text`` on the device. Spaces → %s (Android convention)."""
        # ``input text`` does not accept spaces directly; replace with "%s".
        payload = text.replace(" ", "%s")
        # Special characters that break shell parsing get escaped via shlex.
        self.shell(f"input text {shlex.quote(payload)}")

    def key_event(self, key: int | str) -> None:
        self.shell(f"input keyevent {key}")

    # ---- Screenshot ------------------------------------------------
    def screencap_png(self) -> bytes:
        return self._backend.screencap_png()

    def screencap(self) -> "ScreenImage":
        """Return a :class:`ScreenImage` with a BGR numpy bitmap."""
        # Deferred imports so importing this module does not require numpy.
        import cv2
        import numpy as np

        from sikulipy.core.image import ScreenImage
        from sikulipy.core.region import Region

        png = self.screencap_png()
        arr = cv2.imdecode(np.frombuffer(png, dtype=np.uint8), cv2.IMREAD_COLOR)
        if arr is None:
            raise RuntimeError("failed to decode screencap PNG")
        h, w = arr.shape[:2]
        return ScreenImage(bitmap=arr, bounds=Region(0, 0, int(w), int(h)))
