"""Port of ``org.sikuli.script.Key`` + ``KeyModifier`` — keyboard input.

Special-key encoding follows SikuliX: each non-character key is a reserved
char in the U+E000.. private-use block (e.g. ``Key.ENTER = '\\n'``,
``Key.LEFT = '\\ue003'``). ``Key.type("Hello" + Key.ENTER)`` works.
"""

from __future__ import annotations

import time

from sikulipy.core._input_backend import get_keyboard


class KeyModifier:
    SHIFT = 1
    CTRL = 2
    ALT = 4
    META = 8
    CMD = 8
    WIN = 8

    @classmethod
    def decode(cls, mask: int) -> list[str]:
        """Return the SikuliPy key-strings for a modifier bitmask."""
        keys: list[str] = []
        if mask & cls.SHIFT:
            keys.append(Key.SHIFT)
        if mask & cls.CTRL:
            keys.append(Key.CTRL)
        if mask & cls.ALT:
            keys.append(Key.ALT)
        if mask & cls.META:
            keys.append(Key.META)
        return keys


class Key:
    """SikuliX-compatible key constants.

    Character literals (``ENTER='\\n'``, ``TAB='\\t'``, ``SPACE=' '``, ``BACKSPACE='\\b'``,
    ``ESC='\\x1b'``) are typed directly. Keys in the ``\\ue0XX`` block are
    mapped to pynput special keys via :meth:`_pynput_map`.
    """

    SPACE = " "
    ENTER = "\n"
    BACKSPACE = "\b"
    TAB = "\t"
    ESC = "\u001b"

    UP = "\ue000"
    RIGHT = "\ue001"
    DOWN = "\ue002"
    LEFT = "\ue003"
    PAGE_UP = "\ue004"
    PAGE_DOWN = "\ue005"
    DELETE = "\ue006"
    END = "\ue007"
    HOME = "\ue008"
    INSERT = "\ue009"

    F1 = "\ue011"
    F2 = "\ue012"
    F3 = "\ue013"
    F4 = "\ue014"
    F5 = "\ue015"
    F6 = "\ue016"
    F7 = "\ue017"
    F8 = "\ue018"
    F9 = "\ue019"
    F10 = "\ue01A"
    F11 = "\ue01B"
    F12 = "\ue01C"
    F13 = "\ue01D"
    F14 = "\ue01E"
    F15 = "\ue01F"

    SHIFT = "\ue020"
    CTRL = "\ue021"
    ALT = "\ue022"
    META = "\ue023"
    CMD = "\ue023"
    WIN = "\ue042"
    ALTGR = "\ue043"
    PRINTSCREEN = "\ue024"
    SCROLL_LOCK = "\ue025"
    PAUSE = "\ue026"
    CAPS_LOCK = "\ue027"

    NUM_LOCK = "\ue03B"
    ADD = "\ue03C"
    MINUS = "\ue03D"
    MULTIPLY = "\ue03E"
    DIVIDE = "\ue03F"
    DECIMAL = "\ue040"

    # ------------------------------------------------------------------
    _SPECIAL_NAME: dict[str, str] = {
        "\ue000": "up",
        "\ue001": "right",
        "\ue002": "down",
        "\ue003": "left",
        "\ue004": "page_up",
        "\ue005": "page_down",
        "\ue006": "delete",
        "\ue007": "end",
        "\ue008": "home",
        "\ue009": "insert",
        "\ue011": "f1", "\ue012": "f2", "\ue013": "f3", "\ue014": "f4",
        "\ue015": "f5", "\ue016": "f6", "\ue017": "f7", "\ue018": "f8",
        "\ue019": "f9", "\ue01A": "f10", "\ue01B": "f11", "\ue01C": "f12",
        "\ue01D": "f13", "\ue01E": "f14", "\ue01F": "f15",
        "\ue020": "shift", "\ue021": "ctrl", "\ue022": "alt",
        "\ue023": "cmd", "\ue042": "cmd", "\ue043": "alt_gr",
        "\ue024": "print_screen", "\ue025": "scroll_lock",
        "\ue026": "pause", "\ue027": "caps_lock",
        "\ue03B": "num_lock",
    }

    # Character literals that map to special pynput keys rather than ``type``.
    _LITERAL_SPECIAL: dict[str, str] = {
        "\n": "enter",
        "\t": "tab",
        "\b": "backspace",
        "\x1b": "esc",
    }

    @classmethod
    def is_special(cls, ch: str) -> bool:
        return ch in cls._SPECIAL_NAME or ch in cls._LITERAL_SPECIAL

    @classmethod
    def special_name(cls, ch: str) -> str | None:
        return cls._SPECIAL_NAME.get(ch) or cls._LITERAL_SPECIAL.get(ch)

    @classmethod
    def _pynput_map(cls, PynputKey) -> dict[str, object]:
        """Build a SikuliPy-string -> pynput.keyboard.Key map on demand."""
        mapping: dict[str, object] = {}
        for ch, name in {**cls._SPECIAL_NAME, **cls._LITERAL_SPECIAL}.items():
            if hasattr(PynputKey, name):
                mapping[ch] = getattr(PynputKey, name)
        return mapping

    # ------------------------------------------------------------------
    # High-level type/press/release
    # ------------------------------------------------------------------
    _type_delay: float = 0.0

    @classmethod
    def type(cls, text: str, modifiers: int = 0) -> int:
        """Type ``text`` holding ``modifiers`` (a ``KeyModifier`` bitmask).

        Special keys embedded in ``text`` (Key.ENTER, Key.LEFT, ...) are sent
        via press/release; literal characters go through the backend's
        ``type()`` which handles OS-level text entry.
        """
        backend = get_keyboard()
        held = KeyModifier.decode(modifiers)
        for mod in held:
            backend.press(mod)
        try:
            for run_text, run_is_special in cls._tokenize(text):
                if run_is_special:
                    for ch in run_text:
                        backend.press(ch)
                        backend.release(ch)
                else:
                    backend.type(run_text)
                if cls._type_delay > 0:
                    time.sleep(cls._type_delay)
        finally:
            for mod in reversed(held):
                backend.release(mod)
        return len(text)

    @classmethod
    def press(cls, key: str) -> None:
        get_keyboard().press(key)

    @classmethod
    def release(cls, key: str) -> None:
        get_keyboard().release(key)

    @classmethod
    def hotkey(cls, *keys: str) -> None:
        """Press ``keys`` in order, release in reverse — e.g. ``Key.hotkey(Key.CTRL, 's')``."""
        backend = get_keyboard()
        pressed: list[str] = []
        try:
            for k in keys:
                backend.press(k)
                pressed.append(k)
        finally:
            for k in reversed(pressed):
                backend.release(k)

    # ---- Tokeniser ---------------------------------------------------
    @classmethod
    def _tokenize(cls, text: str) -> list[tuple[str, bool]]:
        """Split text into (run, is_special) pairs so backend.type() handles plain text in bulk."""
        runs: list[tuple[str, bool]] = []
        if not text:
            return runs
        buf: list[str] = []
        buf_special = cls.is_special(text[0])
        for ch in text:
            is_sp = cls.is_special(ch)
            if is_sp != buf_special:
                runs.append(("".join(buf), buf_special))
                buf = [ch]
                buf_special = is_sp
            else:
                buf.append(ch)
        runs.append(("".join(buf), buf_special))
        return runs
