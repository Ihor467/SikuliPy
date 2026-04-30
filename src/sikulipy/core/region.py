"""Port of ``org.sikuli.script.Region`` — rectangular region of the screen.

Phase 1 wires: ``find``, ``find_all``, ``exists``, ``wait``, ``wait_vanish``,
plus the geometry helpers. Actions (click/type/...) stay stubbed for Phase 2.

Source: API/src/main/java/org/sikuli/script/Region.java (~3000 lines).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sikulipy.core.element import Element
from sikulipy.script.exceptions import FindFailed
from sikulipy.util.action_log import logged_action


def _region_surface(self_, *_a, **_k) -> str:
    return getattr(self_, "_surface_name", None) or "desktop"


def _fmt_target(self_, *args, **_k) -> str:
    if not args:
        return ""
    try:
        return repr(args[0])
    except Exception as exc:
        return f"<repr failed: {exc}>"


def _fmt_wait(self_, *args, **kwargs) -> str:
    target = repr(args[0]) if args else ""
    timeout = kwargs.get("timeout", args[1] if len(args) > 1 else None)
    return f"{target} timeout={timeout}" if timeout is not None else target


def _fmt_drag(self_, *args, **_k) -> str:
    if len(args) >= 2:
        return f"{args[0]!r} → {args[1]!r}"
    return _fmt_target(self_, *args)


def _fmt_type(self_, *args, **_k) -> str:
    return repr(args[0]) if args else ""

if TYPE_CHECKING:
    from sikulipy.core.image import Image
    from sikulipy.core.location import Location
    from sikulipy.core.match import Match
    from sikulipy.core.pattern import Pattern


PatternLike = Any  # Pattern | Image | str | Path | np.ndarray


def _sleep(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def _resolve_pattern(target: PatternLike):
    """Return (needle_bgr_array, similarity, Pattern-or-None).

    Accepts a Pattern, Image, path string, Path, or raw numpy array.
    When the caller passes a bare image (no explicit Pattern), the
    similarity threshold falls back to the global default exposed
    through :mod:`sikulipy.core._defaults`. The SikuliX-compatible
    ``Settings.MinSimilarity`` alias writes through to that module, so
    ``Settings.MinSimilarity = 0.9`` actually changes every subsequent
    find().
    """
    from sikulipy.core._defaults import get_min_similarity
    from sikulipy.core.image import Image
    from sikulipy.core.pattern import Pattern

    if isinstance(target, Pattern):
        img = target.image
        image_obj = img if isinstance(img, Image) else Image(img)
        return image_obj.load(), target.similarity, target

    default = get_min_similarity()
    if isinstance(target, Image):
        return target.load(), default, None
    # numpy array, str, or Path
    try:
        import numpy as np  # local import

        if isinstance(target, np.ndarray):
            return target, default, None
    except ImportError:  # pragma: no cover
        pass
    return Image(target).load(), default, None


@dataclass
class Region(Element):
    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 0

    # ---- Geometry ----------------------------------------------------
    def center(self) -> "Location":
        from sikulipy.core.location import Location

        return Location(self.x + self.w // 2, self.y + self.h // 2)

    def top_left(self) -> "Location":
        from sikulipy.core.location import Location

        return Location(self.x, self.y)

    def top_right(self) -> "Location":
        from sikulipy.core.location import Location

        return Location(self.x + self.w, self.y)

    def bottom_left(self) -> "Location":
        from sikulipy.core.location import Location

        return Location(self.x, self.y + self.h)

    def bottom_right(self) -> "Location":
        from sikulipy.core.location import Location

        return Location(self.x + self.w, self.y + self.h)

    def is_valid(self) -> bool:
        return self.w > 0 and self.h > 0

    # ---- Highlight --------------------------------------------------
    def highlight(self, seconds: float = 2.0, color: str = "red"):
        """Briefly outline this region (Phase 8 guide overlay)."""
        from sikulipy.util.highlight import Highlight

        hl = Highlight(self, color=color, duration=seconds)
        hl.show()
        return hl

    # ---- Capture helper ---------------------------------------------
    def _capture_bgr(self):
        """Grab this region's pixels as a BGR numpy array.

        If the region was produced by :func:`sikuli.selectRegion` (or any
        caller that attached a frozen full-screen bitmap via
        :meth:`_attach_frozen_bitmap`), we crop from that bitmap rather
        than doing a fresh ``mss`` grab. This avoids a second compositor
        round-trip — important on KDE/X11 where kwin's "unredirect
        fullscreen windows" optimisation can cause a subsequent
        ``XGetImage`` of the root window to return solid black where an
        accelerated window (konsole, alacritty, kitty, a video player…)
        is drawn. Spectacle uses kwin's DBus API and doesn't hit this;
        ``mss`` does hit it, so we prefer the already-captured pixels
        whenever we have them.
        """
        frozen = getattr(self, "_frozen_bitmap", None)
        if frozen is not None:
            bg, ox, oy = frozen
            # Clamp the crop to the frozen bitmap's bounds.
            x0 = max(0, self.x - ox)
            y0 = max(0, self.y - oy)
            x1 = min(bg.shape[1], x0 + self.w)
            y1 = min(bg.shape[0], y0 + self.h)
            if x1 > x0 and y1 > y0:
                return bg[y0:y1, x0:x1].copy()
            # Degenerate crop — fall through to a live grab.

        # Delay imports to keep Region cheap to import.
        from sikulipy.core.screen import Screen

        screen = Screen.get_primary()
        shot = screen.capture(self)
        return shot.bitmap

    def _attach_frozen_bitmap(self, bitmap, origin_x: int, origin_y: int) -> None:
        """Attach a pre-grabbed BGR bitmap that covers this region.

        ``(origin_x, origin_y)`` is the virtual-screen coordinate of the
        bitmap's ``(0, 0)`` pixel — usually the mss virtual monitor's
        top-left. Subsequent :meth:`_capture_bgr` calls will crop from
        this bitmap instead of calling ``mss`` again. See the docstring
        on :meth:`_capture_bgr` for why this matters on KDE/X11.
        """
        self._frozen_bitmap = (bitmap, int(origin_x), int(origin_y))

    # ---- Finding (Phase 1) -------------------------------------------
    @logged_action("region", "find", target=_fmt_target, surface=_region_surface)
    def find(self, target: PatternLike) -> "Match":
        m = self._find_once(target)
        if m is None:
            raise FindFailed(f"Pattern not found in region {self!r}")
        return m

    @logged_action("region", "find_all", target=_fmt_target, surface=_region_surface)
    def find_all(self, target: PatternLike) -> list["Match"]:
        from sikulipy.core.finder import Finder

        needle, similarity, _ = _resolve_pattern(target)
        haystack = self._capture_bgr()
        finder = Finder(haystack, region=self)
        return finder.find_all(needle, similarity=similarity)

    @logged_action("region", "exists", target=_fmt_wait, surface=_region_surface)
    def exists(self, target: PatternLike, timeout: float = 0.0) -> "Match | None":
        return self._wait_for(target, timeout, want_match=True)

    @logged_action("region", "wait", target=_fmt_wait, surface=_region_surface)
    def wait(self, target: PatternLike, timeout: float = 3.0) -> "Match":
        m = self._wait_for(target, timeout, want_match=True)
        if m is None:
            raise FindFailed(f"wait({target!r}) timed out after {timeout}s")
        return m

    @logged_action("region", "wait_vanish", target=_fmt_wait, surface=_region_surface)
    def wait_vanish(self, target: PatternLike, timeout: float = 3.0) -> bool:
        return self._wait_for(target, timeout, want_match=False) is None or True  # type: ignore[return-value]

    # ---- Internals ---------------------------------------------------
    def _find_once(self, target: PatternLike) -> "Match | None":
        from sikulipy.core.finder import Finder

        needle, similarity, _ = _resolve_pattern(target)
        haystack = self._capture_bgr()
        finder = Finder(haystack, region=self)
        return finder.find(needle, similarity=similarity)

    def _wait_for(
        self, target: PatternLike, timeout: float, *, want_match: bool
    ) -> "Match | None":
        """Poll ``_find_once`` until it matches (want_match) or until it vanishes."""
        deadline = time.monotonic() + max(0.0, timeout)
        poll = 0.25
        while True:
            m = self._find_once(target)
            if want_match and m is not None:
                return m
            if not want_match and m is None:
                return None
            if time.monotonic() >= deadline:
                return m if not want_match else None
            time.sleep(poll)

    # ---- Actions (Phase 2) -------------------------------------------
    def _resolve_click_point(self, target: PatternLike | None):
        """Return (Location, post_delay) for an action target.

        * ``None``            -> region centre
        * ``Location``        -> used as-is (no wait_after)
        * ``Pattern``         -> find, offset by target_offset, honour wait_after
        * anything else       -> treated as image-like and found
        """
        from sikulipy.core.location import Location
        from sikulipy.core.pattern import Pattern

        if target is None:
            return self.center(), 0.0
        if isinstance(target, Location):
            return target, 0.0
        if isinstance(target, Pattern):
            m = self.find(target)
            loc = m.center().offset(target.target_offset.dx, target.target_offset.dy)
            return loc, target.wait_after
        # Image-like
        m = self.find(target)
        return m.center(), 0.0

    @logged_action("region", "click", target=_fmt_target, surface=_region_surface)
    def click(self, target: PatternLike | None = None) -> int:
        from sikulipy.core.mouse import Mouse

        loc, post = self._resolve_click_point(target)
        Mouse.click(loc)
        if post:
            _sleep(post)
        return 1

    @logged_action("region", "double_click", target=_fmt_target, surface=_region_surface)
    def double_click(self, target: PatternLike | None = None) -> int:
        from sikulipy.core.mouse import Mouse

        loc, post = self._resolve_click_point(target)
        Mouse.double_click(loc)
        if post:
            _sleep(post)
        return 1

    @logged_action("region", "right_click", target=_fmt_target, surface=_region_surface)
    def right_click(self, target: PatternLike | None = None) -> int:
        from sikulipy.core.mouse import Mouse

        loc, post = self._resolve_click_point(target)
        Mouse.right_click(loc)
        if post:
            _sleep(post)
        return 1

    @logged_action("region", "hover", target=_fmt_target, surface=_region_surface)
    def hover(self, target: PatternLike | None = None) -> int:
        from sikulipy.core.mouse import Mouse

        loc, _ = self._resolve_click_point(target)
        Mouse.move(loc)
        return 1

    @logged_action("region", "drag_drop", target=_fmt_drag, surface=_region_surface)
    def drag_drop(self, src: PatternLike, dst: PatternLike) -> int:
        from sikulipy.core.mouse import Mouse

        src_loc, _ = self._resolve_click_point(src)
        dst_loc, _ = self._resolve_click_point(dst)
        Mouse.drag_drop(src_loc, dst_loc)
        return 1

    @logged_action("region", "type", target=_fmt_type, surface=_region_surface)
    def type(self, text: str, modifiers: int = 0) -> int:
        from sikulipy.core.keyboard import Key

        return Key.type(text, modifiers=modifiers)

    def paste(self, text: str) -> int:
        """Set the clipboard and paste with platform-appropriate hotkey."""
        from sikulipy.core.env import Env
        from sikulipy.core.keyboard import Key

        Env.set_clipboard(text)
        modifier = Key.CMD if Env.is_macos() else Key.CTRL
        Key.hotkey(modifier, "v")
        return len(text)

    # ---- OCR (Phase 3) -----------------------------------------------
    @logged_action("region", "text", target="", surface=_region_surface)
    def text(self) -> str:
        """OCR this region and return the recognised text."""
        from sikulipy.ocr import OCR

        return OCR.read(self._capture_bgr())

    def words(self):
        """Return a list of recognised :class:`sikulipy.ocr.Word`s in screen coords."""
        from sikulipy.ocr import OCR

        raw = OCR.read_words(self._capture_bgr())
        # Translate from region-local coordinates to absolute screen coords.
        return [w.offset(self.x, self.y) for w in raw]

    @logged_action("region", "find_text", target=_fmt_target, surface=_region_surface)
    def find_text(self, needle: str) -> "Match":
        from sikulipy.core.match import Match
        from sikulipy.ocr import OCR
        from sikulipy.script.exceptions import FindFailed

        w = OCR.find_text(self._capture_bgr(), needle)
        if w is None:
            raise FindFailed(f"Text {needle!r} not found in region {self!r}")
        return Match(
            x=self.x + w.x, y=self.y + w.y, w=w.w, h=w.h, score=float(w.confidence)
        )

    @logged_action("region", "find_all_text", target=_fmt_target, surface=_region_surface)
    def find_all_text(self, needle: str) -> list["Match"]:
        from sikulipy.core.match import Match
        from sikulipy.ocr import OCR

        hits = OCR.find_all_text(self._capture_bgr(), needle)
        return [
            Match(x=self.x + w.x, y=self.y + w.y, w=w.w, h=w.h, score=float(w.confidence))
            for w in hits
        ]

    def has_text(self, needle: str) -> bool:
        from sikulipy.ocr import OCR

        return OCR.find_text(self._capture_bgr(), needle) is not None

    # ---- Observation (Phase 7) ---------------------------------------
    def on_appear(self, target: PatternLike, callback) -> None:
        raise NotImplementedError("Phase 7")

    def on_vanish(self, target: PatternLike, callback) -> None:
        raise NotImplementedError("Phase 7")

    def on_change(self, callback) -> None:
        raise NotImplementedError("Phase 7")

    def observe(self, timeout: float = float("inf")) -> None:
        raise NotImplementedError("Phase 7")
