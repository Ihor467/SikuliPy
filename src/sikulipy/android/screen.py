"""ADBScreen — the Android device modelled as a :class:`Region`.

Overrides ``_capture_bgr`` so the find/OCR pipeline grabs frames from the
device. Overrides the action hooks (``click``, ``double_click``,
``right_click``, ``hover``, ``drag_drop``, ``type``, ``paste``) so they
dispatch through ADB (``input tap`` / ``input swipe`` / ``input text``)
instead of the desktop mouse/keyboard.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sikulipy.android.client import ADBClient, ADBDevice
from sikulipy.core.region import Region, _resolve_pattern
from sikulipy.util.action_log import logged_action


def _adb_surface(self_, *_a, **_k) -> str:
    serial = getattr(getattr(self_, "device", None), "serial", None)
    return f"adb:{serial}" if serial else "adb"


def _fmt_target(_self, *args, **_k) -> str:
    if not args:
        return ""
    try:
        return repr(args[0])
    except Exception as exc:
        return f"<repr failed: {exc}>"


def _fmt_drag(_self, *args, **_k) -> str:
    if len(args) >= 2:
        return f"{args[0]!r} → {args[1]!r}"
    return _fmt_target(_self, *args)

if TYPE_CHECKING:
    from sikulipy.core.location import Location


PatternLike = Any


class ADBScreen(Region):
    """An Android device exposed as a ``Region``.

    Usage::

        screen = ADBScreen.start()             # first attached device
        screen = ADBScreen.start(serial="…")   # specific device
        screen = ADBScreen.connect("192.168.1.10:5555")  # WiFi ADB

    After construction, all ``Region`` operations (``find``, ``find_text``,
    ``click``, ``type``, ``drag_drop``) work — but actions are dispatched
    through ADB instead of the local desktop.
    """

    def __init__(self, device: ADBDevice) -> None:
        self.device: ADBDevice = device
        self._surface_name = f"adb:{device.serial}" if getattr(device, "serial", None) else "adb"
        w, h = device.size()
        super().__init__(x=0, y=0, w=w, h=h)

    # ---- Factories --------------------------------------------------
    @classmethod
    def start(
        cls, serial: str | None = None, *, host: str = "127.0.0.1", port: int = 5037
    ) -> "ADBScreen":
        client = ADBClient(host=host, port=port)
        return cls(client.device(serial))

    @classmethod
    def connect(
        cls, address: str, *, host: str = "127.0.0.1", port: int = 5037
    ) -> "ADBScreen":
        client = ADBClient(host=host, port=port)
        return cls(client.connect(address))

    def stop(self) -> None:  # noqa: D401
        """No-op — kept for API parity with SikuliX's ``ADBScreen.stop()``."""

    # ---- Capture ----------------------------------------------------
    def _capture_bgr(self):
        """Capture the whole device; Finder handles sub-region cropping."""
        shot = self.device.screencap()
        return shot.bitmap

    # ---- Actions ----------------------------------------------------
    def _loc_for(self, target: PatternLike | None) -> "Location":
        """Shared resolve: None → centre, Location → as-is, Pattern/Image → find."""
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

    @logged_action("android", "click", target=_fmt_target, surface=_adb_surface)
    def click(self, target: PatternLike | None = None) -> int:
        loc = self._loc_for(target)
        self.device.tap(loc.x, loc.y)
        return 1

    @logged_action("android", "double_click", target=_fmt_target, surface=_adb_surface)
    def double_click(self, target: PatternLike | None = None) -> int:
        loc = self._loc_for(target)
        # No native double-tap; two quick taps is the standard ADB idiom.
        self.device.tap(loc.x, loc.y)
        self.device.tap(loc.x, loc.y)
        return 1

    @logged_action("android", "right_click", target=_fmt_target, surface=_adb_surface)
    def right_click(self, target: PatternLike | None = None) -> int:
        # Android has no right-click; treat as long press.
        loc = self._loc_for(target)
        self.device.long_press(loc.x, loc.y)
        return 1

    @logged_action("android", "hover", target=_fmt_target, surface=_adb_surface)
    def hover(self, target: PatternLike | None = None) -> int:
        # ADB has no hover concept.
        return 0

    @logged_action("android", "drag_drop", target=_fmt_drag, surface=_adb_surface)
    def drag_drop(
        self,
        src: PatternLike,
        dst: PatternLike,
        *,
        duration_ms: int = 400,
    ) -> int:
        src_loc = self._loc_for(src)
        dst_loc = self._loc_for(dst)
        self.device.swipe(src_loc.x, src_loc.y, dst_loc.x, dst_loc.y, duration_ms)
        return 1

    @logged_action("android", "swipe", target=_fmt_drag, surface=_adb_surface)
    def swipe(
        self,
        src: PatternLike,
        dst: PatternLike,
        *,
        duration_ms: int = 400,
    ) -> int:
        return self.drag_drop(src, dst, duration_ms=duration_ms)

    @logged_action("android", "type", target=_fmt_target, surface=_adb_surface)
    def type(self, text: str, modifiers: int = 0) -> int:  # noqa: ARG002 - no modifiers on ADB
        self.device.input_text(text)
        return len(text)

    def paste(self, text: str) -> int:
        # No clipboard route on vanilla ADB; just type it.
        return self.type(text)

    # ---- Utility ----------------------------------------------------
    @logged_action("android", "find_text_coordinates", target=_fmt_target, surface=_adb_surface)
    def find_text_coordinates(self, needle: str) -> tuple[int, int, int, int] | None:
        """Parity with OculiX Java: return (x, y, w, h) for the first OCR match."""
        needle_bgr = self._capture_bgr()
        from sikulipy.ocr import OCR

        word = OCR.find_text(needle_bgr, needle)
        if word is None:
            return None
        return (word.x, word.y, word.w, word.h)


# Silence "unused import" when callers only pull _resolve_pattern from region.
_ = _resolve_pattern
