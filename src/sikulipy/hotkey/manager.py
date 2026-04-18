"""Global hotkey manager — ports HotkeyController.java + Keys.java.

Backed by ``pynput.keyboard.GlobalHotKeys``. Translates a SikuliPy key
(character or ``Key.*`` constant) plus a ``KeyModifier`` bitmask into
pynput's ``<ctrl>+<shift>+a`` hotkey string.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Callable


class Keys:
    """Convenience aliases used when registering hotkeys."""

    ESCAPE = "esc"
    F1 = "<f1>"
    F2 = "<f2>"
    F3 = "<f3>"
    F4 = "<f4>"
    F5 = "<f5>"
    F6 = "<f6>"
    F7 = "<f7>"
    F8 = "<f8>"
    F9 = "<f9>"
    F10 = "<f10>"
    F11 = "<f11>"
    F12 = "<f12>"


@dataclass
class HotkeyEvent:
    key: str
    modifiers: int


HotkeyCallback = Callable[[HotkeyEvent], None]


# Map SikuliPy ``Key.*`` private-use chars and literal chars to pynput tokens.
_KEY_TO_PYNPUT: dict[str, str] = {
    "\ue000": "<up>",
    "\ue001": "<right>",
    "\ue002": "<down>",
    "\ue003": "<left>",
    "\ue004": "<page_up>",
    "\ue005": "<page_down>",
    "\ue006": "<delete>",
    "\ue007": "<end>",
    "\ue008": "<home>",
    "\ue009": "<insert>",
    "\ue011": "<f1>", "\ue012": "<f2>", "\ue013": "<f3>", "\ue014": "<f4>",
    "\ue015": "<f5>", "\ue016": "<f6>", "\ue017": "<f7>", "\ue018": "<f8>",
    "\ue019": "<f9>", "\ue01A": "<f10>", "\ue01B": "<f11>", "\ue01C": "<f12>",
    "\n": "<enter>",
    "\t": "<tab>",
    "\b": "<backspace>",
    "\x1b": "<esc>",
}


def translate(key: str, modifiers: int = 0) -> str:
    """Translate a (key, modifier bitmask) pair to a pynput hotkey string."""
    from sikulipy.core.keyboard import Key, KeyModifier  # local to avoid cycle

    parts: list[str] = []
    if modifiers & KeyModifier.CTRL:
        parts.append("<ctrl>")
    if modifiers & KeyModifier.ALT:
        parts.append("<alt>")
    if modifiers & KeyModifier.SHIFT:
        parts.append("<shift>")
    if modifiers & KeyModifier.META:
        parts.append("<cmd>")

    # Allow passing a pre-formatted pynput token (e.g. "<f5>") unchanged.
    if key.startswith("<") and key.endswith(">"):
        parts.append(key)
    elif key in _KEY_TO_PYNPUT:
        parts.append(_KEY_TO_PYNPUT[key])
    elif key == Key.CTRL:
        if "<ctrl>" not in parts:
            parts.append("<ctrl>")
    elif key == Key.ALT:
        if "<alt>" not in parts:
            parts.append("<alt>")
    elif key == Key.SHIFT:
        if "<shift>" not in parts:
            parts.append("<shift>")
    elif key in (Key.META, Key.CMD, Key.WIN):
        if "<cmd>" not in parts:
            parts.append("<cmd>")
    else:
        parts.append(key.lower())
    return "+".join(parts)


class HotkeyManager:
    """Register/unregister global hotkeys. Thread-safe."""

    def __init__(self) -> None:
        self._bindings: dict[str, HotkeyCallback] = {}
        self._lock = Lock()
        self._listener = None  # pynput GlobalHotKeys

    # ---- Registration -----------------------------------------------
    def register(self, key: str, modifiers: int, cb: HotkeyCallback) -> str:
        combo = translate(key, modifiers)
        with self._lock:
            self._bindings[combo] = lambda _cb=cb, _k=key, _m=modifiers: _cb(
                HotkeyEvent(key=_k, modifiers=_m)
            )
            self._restart_listener()
        return combo

    def unregister(self, key: str, modifiers: int) -> None:
        combo = translate(key, modifiers)
        with self._lock:
            self._bindings.pop(combo, None)
            self._restart_listener()

    def clear(self) -> None:
        with self._lock:
            self._bindings.clear()
            self._stop_listener()

    def stop(self) -> None:
        self.clear()

    # ---- Backend plumbing -------------------------------------------
    def _stop_listener(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None

    def _restart_listener(self) -> None:
        self._stop_listener()
        if not self._bindings:
            return
        from pynput.keyboard import GlobalHotKeys

        self._listener = GlobalHotKeys(dict(self._bindings))
        self._listener.start()
