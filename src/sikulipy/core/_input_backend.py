"""Swappable input backend for Mouse/Keyboard.

Separating the backend from the public API lets tests inject a fake, and
keeps ``pynput`` (which loads platform-specific bindings at import time)
out of the import graph for code that only needs geometry primitives.
"""

from __future__ import annotations

from typing import Protocol


class MouseBackend(Protocol):
    def position(self) -> tuple[int, int]: ...
    def move(self, x: int, y: int) -> None: ...
    def press(self, button: str) -> None: ...
    def release(self, button: str) -> None: ...
    def click(self, button: str, count: int = 1) -> None: ...
    def scroll(self, dx: int, dy: int) -> None: ...


class KeyboardBackend(Protocol):
    def press(self, key: str) -> None: ...
    def release(self, key: str) -> None: ...
    def type(self, text: str) -> None: ...


class _PynputMouse:
    """Lazy pynput-backed mouse controller."""

    def __init__(self) -> None:
        from pynput.mouse import Button, Controller

        self._Button = Button
        self._ctrl = Controller()

    def _btn(self, name: str):
        return {
            "left": self._Button.left,
            "right": self._Button.right,
            "middle": self._Button.middle,
        }[name]

    def position(self) -> tuple[int, int]:
        x, y = self._ctrl.position
        return int(x), int(y)

    def move(self, x: int, y: int) -> None:
        self._ctrl.position = (int(x), int(y))

    def press(self, button: str) -> None:
        self._ctrl.press(self._btn(button))

    def release(self, button: str) -> None:
        self._ctrl.release(self._btn(button))

    def click(self, button: str, count: int = 1) -> None:
        self._ctrl.click(self._btn(button), count)

    def scroll(self, dx: int, dy: int) -> None:
        self._ctrl.scroll(int(dx), int(dy))


class _PynputKeyboard:
    def __init__(self) -> None:
        from pynput.keyboard import Controller, Key

        self._Key = Key
        self._ctrl = Controller()

    def _resolve(self, key: str):
        """Map a SikuliPy key-string to a pynput key or literal character."""
        from sikulipy.core.keyboard import Key as SKey

        mapping = SKey._pynput_map(self._Key)
        if key in mapping:
            return mapping[key]
        return key  # literal character

    def press(self, key: str) -> None:
        self._ctrl.press(self._resolve(key))

    def release(self, key: str) -> None:
        self._ctrl.release(self._resolve(key))

    def type(self, text: str) -> None:
        self._ctrl.type(text)


# -----------------------------------------------------------------------------
# Singletons with override hook for tests.
# -----------------------------------------------------------------------------

_mouse: MouseBackend | None = None
_keyboard: KeyboardBackend | None = None


def get_mouse() -> MouseBackend:
    global _mouse
    if _mouse is None:
        _mouse = _PynputMouse()
    return _mouse


def get_keyboard() -> KeyboardBackend:
    global _keyboard
    if _keyboard is None:
        _keyboard = _PynputKeyboard()
    return _keyboard


def set_mouse(backend: MouseBackend | None) -> None:
    """Install a custom mouse backend (or ``None`` to reset)."""
    global _mouse
    _mouse = backend


def set_keyboard(backend: KeyboardBackend | None) -> None:
    global _keyboard
    _keyboard = backend
