"""``VNCScreen`` — a remote desktop exposed as a :class:`Region`.

Port of ``org.sikuli.vnc.VNCScreen`` + ``VNCRobot``. Capture goes through
the VNC backend's framebuffer; click/type/drag are translated into RFB
pointer and keyboard events and dispatched through the same backend.

The backend is swappable (see ``_backend.py``) so tests can plug in a
recorder without a running RFB server.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from sikulipy.core.region import Region
from sikulipy.vnc import xkeysym
from sikulipy.vnc._backend import VncBackend, get_connector

if TYPE_CHECKING:
    from sikulipy.core.location import Location


PatternLike = Any


# RFB button masks (same bits as VNCRobot.java).
VNC_BUTTON_1 = 1 << 0  # left
VNC_BUTTON_2 = 1 << 1  # middle
VNC_BUTTON_3 = 1 << 2  # right
VNC_BUTTON_4 = 1 << 3  # wheel up
VNC_BUTTON_5 = 1 << 4  # wheel down


# Map SikuliPy's ``\ue0xx`` private-use chars → X11 keysym integers.
_SPECIAL_TO_XK: dict[str, int] = {
    "\ue000": xkeysym.XK_Up,
    "\ue001": xkeysym.XK_Right,
    "\ue002": xkeysym.XK_Down,
    "\ue003": xkeysym.XK_Left,
    "\ue004": xkeysym.XK_Page_Up,
    "\ue005": xkeysym.XK_Page_Down,
    "\ue006": xkeysym.XK_Delete,
    "\ue007": xkeysym.XK_End,
    "\ue008": xkeysym.XK_Home,
    "\ue009": xkeysym.XK_Insert,
    "\ue011": xkeysym.XK_F1, "\ue012": xkeysym.XK_F2, "\ue013": xkeysym.XK_F3,
    "\ue014": xkeysym.XK_F4, "\ue015": xkeysym.XK_F5, "\ue016": xkeysym.XK_F6,
    "\ue017": xkeysym.XK_F7, "\ue018": xkeysym.XK_F8, "\ue019": xkeysym.XK_F9,
    "\ue01A": xkeysym.XK_F10, "\ue01B": xkeysym.XK_F11, "\ue01C": xkeysym.XK_F12,
    "\ue01D": xkeysym.XK_F13, "\ue01E": xkeysym.XK_F14, "\ue01F": xkeysym.XK_F15,
    "\ue020": xkeysym.XK_Shift_L, "\ue021": xkeysym.XK_Control_L,
    "\ue022": xkeysym.XK_Alt_L, "\ue023": xkeysym.XK_Meta_L,
    "\ue042": xkeysym.XK_Super_L, "\ue043": xkeysym.XK_ISO_Level3_Shift,
    "\ue024": xkeysym.XK_Print, "\ue025": xkeysym.XK_Scroll_Lock,
    "\ue026": xkeysym.XK_Pause, "\ue027": xkeysym.XK_Caps_Lock,
    "\ue03B": xkeysym.XK_Num_Lock,
    # Literal specials (Key.ENTER='\n', etc.)
    "\n": xkeysym.XK_Return,
    "\t": xkeysym.XK_Tab,
    "\b": xkeysym.XK_BackSpace,
    "\x1b": xkeysym.XK_Escape,
}

# Printables that need shift on a US layout — mirrors VNCRobot.requiresShift.
_SHIFT_CHARS: frozenset[str] = frozenset(
    "~!@#$%^&*()_+{}|:\"<>?"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
)


def _char_to_keysym(ch: str) -> int:
    """SikuliPy char → X11 keysym. Raises ValueError for un-mappable chars."""
    if ch in _SPECIAL_TO_XK:
        return _SPECIAL_TO_XK[ch]
    code = ord(ch)
    # X11 latin1 range maps 1:1 to the first plane of keysyms.
    if 0x20 <= code <= 0xFF:
        return code
    # Unicode-prefixed keysyms (X11 convention for anything else).
    if code >= 0x0100:
        return 0x01000000 + code
    raise ValueError(f"cannot map character {ch!r} to an X11 keysym")


class VNCScreen(Region):
    """A VNC remote desktop exposed as a :class:`Region`.

    Usage::

        vnc = VNCScreen.start("10.0.0.5")
        vnc.find(Pattern("button.png")).click()
        vnc.type("hello\\n")
        vnc.stop()

    All :class:`Region` methods (``find``, ``find_text``, ``click``, ``type``,
    ``drag_drop``, ...) work — captures go through the VNC framebuffer and
    actions are translated into RFB pointer/keyboard events.
    """

    # Sikuli compatibility — applied after ``start()`` returns, like Java.
    start_up_wait: float = 0.0

    _screens: dict[str, "VNCScreen"] = {}

    def __init__(self, host: str, port: int, backend: VncBackend) -> None:
        w, h = backend.size
        super().__init__(x=0, y=0, w=int(w), h=int(h))
        self.host = host
        self.port = port
        self._backend: VncBackend | None = backend
        self._button_mask = 0
        self._pressed_keys: set[int] = set()
        self._shift_held = False
        self._last_xy: tuple[int, int] = (0, 0)
        self._id = f"{host}:{port}"

    # ---- Factories --------------------------------------------------
    @classmethod
    def start(
        cls,
        host: str = "127.0.0.1",
        port: int = 5900,
        password: str | None = None,
    ) -> "VNCScreen":
        """Connect to a VNC server and return a new :class:`VNCScreen`.

        Reuses an existing instance if one is already open for the same
        ``host:port`` — matches Java's ``VNCScreen.start()`` behaviour.
        """
        key = f"{host}:{port}"
        existing = cls._screens.get(key)
        if existing is not None and existing.is_running():
            return existing
        backend = get_connector().connect(host, port, password)
        scr = cls(host, port, backend)
        cls._screens[key] = scr
        if cls.start_up_wait > 0:
            time.sleep(cls.start_up_wait)
        return scr

    @classmethod
    def stop_all(cls) -> None:
        for scr in list(cls._screens.values()):
            scr.stop()
        cls._screens.clear()

    def stop(self) -> None:
        if self._backend is not None:
            self._backend.disconnect()
            self._backend = None
        self._screens.pop(self._id, None)

    def is_running(self) -> bool:
        return self._backend is not None

    @property
    def backend(self) -> VncBackend:
        if self._backend is None:
            raise RuntimeError(f"VNCScreen {self._id} is not connected")
        return self._backend

    # ---- Capture ----------------------------------------------------
    def _capture_bgr(self):
        return self.backend.capture()

    # ---- Pointer / buttons ------------------------------------------
    def _pointer_move(self, x: int, y: int) -> None:
        self._last_xy = (int(x), int(y))
        self.backend.pointer(int(x), int(y), self._button_mask)

    def _pointer_press(self, x: int, y: int, button_bit: int) -> None:
        self._button_mask |= button_bit
        self.backend.pointer(int(x), int(y), self._button_mask)

    def _pointer_release(self, x: int, y: int, button_bit: int) -> None:
        self._button_mask &= ~button_bit
        self.backend.pointer(int(x), int(y), self._button_mask)

    def _tap(self, loc: "Location", button_bit: int, count: int = 1) -> None:
        for _ in range(count):
            self._pointer_move(loc.x, loc.y)
            self._pointer_press(loc.x, loc.y, button_bit)
            self._pointer_release(loc.x, loc.y, button_bit)

    # ---- Target resolution (matches Android/Region semantics) -------
    def _loc_for(self, target: PatternLike | None) -> "Location":
        from sikulipy.core.location import Location
        from sikulipy.core.pattern import Pattern

        if target is None:
            return self.center()
        if isinstance(target, Location):
            return target
        if isinstance(target, Pattern):
            m = self.find(target)
            return m.center().offset(target.target_offset.dx, target.target_offset.dy)
        m = self.find(target)
        return m.center()

    # ---- Actions ----------------------------------------------------
    def click(self, target: PatternLike | None = None) -> int:
        self._tap(self._loc_for(target), VNC_BUTTON_1)
        return 1

    def double_click(self, target: PatternLike | None = None) -> int:
        self._tap(self._loc_for(target), VNC_BUTTON_1, count=2)
        return 1

    def right_click(self, target: PatternLike | None = None) -> int:
        self._tap(self._loc_for(target), VNC_BUTTON_3)
        return 1

    def middle_click(self, target: PatternLike | None = None) -> int:
        self._tap(self._loc_for(target), VNC_BUTTON_2)
        return 1

    def hover(self, target: PatternLike | None = None) -> int:
        loc = self._loc_for(target)
        self._pointer_move(loc.x, loc.y)
        return 1

    def drag_drop(
        self, src: PatternLike, dst: PatternLike, *, steps: int = 10
    ) -> int:
        src_loc = self._loc_for(src)
        dst_loc = self._loc_for(dst)
        self._pointer_move(src_loc.x, src_loc.y)
        self._pointer_press(src_loc.x, src_loc.y, VNC_BUTTON_1)
        # Interpolate so servers that care about motion events see a drag.
        for i in range(1, steps):
            fx = src_loc.x + (dst_loc.x - src_loc.x) * i / steps
            fy = src_loc.y + (dst_loc.y - src_loc.y) * i / steps
            self._pointer_move(int(fx), int(fy))
        self._pointer_move(dst_loc.x, dst_loc.y)
        self._pointer_release(dst_loc.x, dst_loc.y, VNC_BUTTON_1)
        return 1

    def wheel(self, direction: int, steps: int = 1, target: PatternLike | None = None) -> int:
        """``direction`` > 0 scrolls up, < 0 scrolls down."""
        bit = VNC_BUTTON_4 if direction > 0 else VNC_BUTTON_5
        if target is not None:
            loc = self._loc_for(target)
            x, y = loc.x, loc.y
        else:
            x, y = self._last_xy
        for _ in range(steps):
            self._pointer_press(x, y, bit)
            self._pointer_release(x, y, bit)
        return steps

    # ---- Keyboard ---------------------------------------------------
    def _key_down(self, keysym: int) -> None:
        self.backend.key_down(keysym)
        self._pressed_keys.add(keysym)
        if keysym in (xkeysym.XK_Shift_L, xkeysym.XK_Shift_R, xkeysym.XK_Shift_Lock):
            self._shift_held = True

    def _key_up(self, keysym: int) -> None:
        self.backend.key_up(keysym)
        self._pressed_keys.discard(keysym)
        if keysym in (xkeysym.XK_Shift_L, xkeysym.XK_Shift_R, xkeysym.XK_Shift_Lock):
            self._shift_held = False

    def _type_char(self, ch: str) -> None:
        keysym = _char_to_keysym(ch)
        needs_shift = ch in _SHIFT_CHARS and not self._shift_held
        if needs_shift:
            self._key_down(xkeysym.XK_Shift_L)
        self._key_down(keysym)
        self._key_up(keysym)
        if needs_shift:
            self._key_up(xkeysym.XK_Shift_L)

    def type(self, text: str, modifiers: int = 0) -> int:
        from sikulipy.core.keyboard import KeyModifier

        held: list[int] = []
        if modifiers & KeyModifier.SHIFT:
            held.append(xkeysym.XK_Shift_L)
        if modifiers & KeyModifier.CTRL:
            held.append(xkeysym.XK_Control_L)
        if modifiers & KeyModifier.ALT:
            held.append(xkeysym.XK_Alt_L)
        if modifiers & KeyModifier.META:
            held.append(xkeysym.XK_Meta_L)
        for k in held:
            self._key_down(k)
        try:
            for ch in text:
                self._type_char(ch)
        finally:
            for k in reversed(held):
                self._key_up(k)
        return len(text)

    def key_up_all(self) -> None:
        """Release every currently-pressed key (mirrors VNCRobot.keyUp())."""
        for k in list(self._pressed_keys):
            self._key_up(k)

    def paste(self, text: str) -> int:
        # No clipboard channel on vanilla RFB; just type it.
        return self.type(text)
