"""Swappable ADB backend.

Same pattern as ``_input_backend`` / ``ocr/_backend``. The default
implementation wraps ``pure-python-adb``; tests substitute a fake that
records the shell commands it was asked to run.
"""

from __future__ import annotations

from typing import Protocol


class AdbDeviceBackend(Protocol):
    @property
    def serial(self) -> str: ...
    def shell(self, cmd: str) -> str: ...
    def screencap_png(self) -> bytes: ...


class AdbClientBackend(Protocol):
    def devices(self) -> list[AdbDeviceBackend]: ...
    def device(self, serial: str | None = None) -> AdbDeviceBackend: ...
    def connect(self, address: str) -> None: ...


# ---------------------------------------------------------------------------
# pure-python-adb implementation
# ---------------------------------------------------------------------------


class _PpAdbDevice:
    """Adapter around a ``ppadb.device.Device`` instance."""

    def __init__(self, dev) -> None:
        self._dev = dev

    @property
    def serial(self) -> str:
        return str(self._dev.serial)

    def shell(self, cmd: str) -> str:
        return self._dev.shell(cmd) or ""

    def screencap_png(self) -> bytes:
        return self._dev.screencap()


class _PpAdbClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 5037) -> None:
        from ppadb.client import Client

        self._client = Client(host=host, port=port)

    def devices(self) -> list[AdbDeviceBackend]:
        return [_PpAdbDevice(d) for d in self._client.devices()]

    def device(self, serial: str | None = None) -> AdbDeviceBackend:
        if serial is not None:
            dev = self._client.device(serial)
            if dev is None:
                raise RuntimeError(f"ADB device with serial {serial!r} not found")
            return _PpAdbDevice(dev)
        devs = self._client.devices()
        if not devs:
            raise RuntimeError("No ADB devices attached")
        return _PpAdbDevice(devs[0])

    def connect(self, address: str) -> None:
        # ppadb's Client exposes remote_connect(host, port)
        if ":" in address:
            host, port = address.rsplit(":", 1)
            self._client.remote_connect(host, int(port))
        else:
            self._client.remote_connect(address, 5555)


# ---------------------------------------------------------------------------
# Singleton hook
# ---------------------------------------------------------------------------

_client: AdbClientBackend | None = None


def get_client(host: str = "127.0.0.1", port: int = 5037) -> AdbClientBackend:
    global _client
    if _client is None:
        _client = _PpAdbClient(host=host, port=port)
    return _client


def set_client(client: AdbClientBackend | None) -> None:
    global _client
    _client = client
