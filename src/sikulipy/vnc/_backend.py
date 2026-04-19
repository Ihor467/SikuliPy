"""Swappable VNC backend.

Same pattern as ``_input_backend`` / ``ocr/_backend`` / ``android/_backend``.
The default implementation wraps ``vncdotool`` (Twisted-based). Tests
substitute a fake that records pointer/keyboard events and returns canned
framebuffers.

The backend API is intentionally small so we can re-implement it with a
custom asyncio RFB client later without touching callers:

``connect(host, port, password) -> VncBackend``

``VncBackend`` exposes:
    * ``size: tuple[int, int]``              — framebuffer width/height
    * ``capture() -> np.ndarray``            — full-frame BGR bitmap
    * ``pointer(x, y, button_mask)``         — absolute pointer + button mask
    * ``key_down(xkeysym)`` / ``key_up(xkeysym)``
    * ``disconnect()``
"""

from __future__ import annotations

from typing import Protocol


class VncBackend(Protocol):
    @property
    def size(self) -> tuple[int, int]: ...
    def capture(self): ...  # -> np.ndarray (BGR)
    def pointer(self, x: int, y: int, button_mask: int) -> None: ...
    def key_down(self, xkeysym: int) -> None: ...
    def key_up(self, xkeysym: int) -> None: ...
    def disconnect(self) -> None: ...


class VncConnector(Protocol):
    def connect(
        self, host: str, port: int = 5900, password: str | None = None
    ) -> VncBackend: ...


# ---------------------------------------------------------------------------
# vncdotool implementation
# ---------------------------------------------------------------------------


class _VncDoToolBackend:
    """Adapter around a ``vncdotool`` synchronous client.

    ``vncdotool.api.connect()`` returns a ``ThreadedVNCClientProxy`` that
    dispatches calls to a background Twisted reactor. Its surface fits our
    Protocol well enough that this adapter mostly forwards.
    """

    def __init__(self, client) -> None:
        self._client = client
        self._button_mask = 0
        # vncdotool exposes .screen (PIL Image) after captureScreen().
        self._width: int | None = None
        self._height: int | None = None

    @property
    def size(self) -> tuple[int, int]:
        if self._width is None or self._height is None:
            img = self._client.captureScreen()  # PIL.Image
            self._width, self._height = img.size
        return self._width, self._height

    def capture(self):
        import numpy as np

        img = self._client.captureScreen()  # PIL.Image in RGB
        self._width, self._height = img.size
        arr = np.asarray(img)
        # PIL → RGB → BGR for OpenCV parity
        if arr.ndim == 3 and arr.shape[2] >= 3:
            arr = arr[:, :, [2, 1, 0]].copy()
        return arr

    def pointer(self, x: int, y: int, button_mask: int) -> None:
        self._client.mouseMove(int(x), int(y))
        # vncdotool has mousePress/mouseDown/mouseUp per-button; we replay the
        # delta against the previously recorded mask.
        changed = button_mask ^ self._button_mask
        for bit in range(8):
            mask_bit = 1 << bit
            if not (changed & mask_bit):
                continue
            button = bit + 1  # RFB buttons are 1-indexed
            if button_mask & mask_bit:
                self._client.mouseDown(button)
            else:
                self._client.mouseUp(button)
        self._button_mask = button_mask

    def key_down(self, xkeysym: int) -> None:
        self._client.keyDown(_xkeysym_to_vncdotool(xkeysym))

    def key_up(self, xkeysym: int) -> None:
        self._client.keyUp(_xkeysym_to_vncdotool(xkeysym))

    def disconnect(self) -> None:
        try:
            self._client.disconnect()
        except Exception:
            pass


def _xkeysym_to_vncdotool(xkeysym: int) -> str:
    """vncdotool accepts either an int keysym or a name; prefer the name."""
    from sikulipy.vnc.xkeysym import keysym_name

    name = keysym_name(xkeysym)
    return name if name is not None else chr(xkeysym) if 0x20 <= xkeysym <= 0x7E else str(xkeysym)


class _VncDoToolConnector:
    def connect(
        self, host: str, port: int = 5900, password: str | None = None
    ) -> VncBackend:
        from vncdotool import api  # type: ignore[import-not-found]

        # vncdotool takes host:display style; default port 5900 = display 0.
        display = port - 5900
        target = f"{host}::{port}" if display < 0 else f"{host}:{display}"
        client = api.connect(target, password=password)
        return _VncDoToolBackend(client)


# ---------------------------------------------------------------------------
# Singleton hook — follows the ADB / OCR pattern
# ---------------------------------------------------------------------------

_connector: VncConnector | None = None


def get_connector() -> VncConnector:
    global _connector
    if _connector is None:
        _connector = _VncDoToolConnector()
    return _connector


def set_connector(connector: VncConnector | None) -> None:
    global _connector
    _connector = connector
