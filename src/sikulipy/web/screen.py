"""WebScreen — a Playwright-driven web page modelled as a :class:`Region`.

Wraps a :class:`BrowserBackend` so the find/OCR pipeline grabs frames
from the browser, and so click/type actions route through Playwright
``page.mouse`` / ``page.keyboard`` instead of the host's input
backend. Singleton-by-URL like :class:`VNCScreen.start`, so a recorded
script that does ``screen = WebScreen.start(url=...)`` keeps reusing
the same browser process across calls.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sikulipy.core.region import Region
from sikulipy.util.action_log import logged_action
from sikulipy.web._backend import BrowserBackend, get_backend

if TYPE_CHECKING:
    from sikulipy.core.location import Location


PatternLike = Any


def _web_surface(self_, *_a, **_k) -> str:
    url = getattr(self_, "url", None)
    return f"web:{url}" if url else "web"


def _fmt_target(_self, *args, **_k) -> str:
    if not args:
        return ""
    try:
        return repr(args[0])
    except Exception as exc:  # pragma: no cover - defensive
        return f"<repr failed: {exc}>"


def _fmt_drag(_self, *args, **_k) -> str:
    if len(args) >= 2:
        return f"{args[0]!r} → {args[1]!r}"
    return _fmt_target(_self, *args)


_REGISTRY: dict[str, "WebScreen"] = {}


class WebScreen(Region):
    """A web page exposed as a :class:`Region`.

    Usage::

        screen = WebScreen.start(url="https://example.com")
        screen.click(Pattern("login_btn.png"))
        screen.type("hello@example.com")
    """

    def __init__(self, url: str, backend: BrowserBackend | None = None) -> None:
        self.url = url
        self._backend: BrowserBackend = backend or get_backend()
        self._backend.launch()
        self._backend.goto(url)
        self._backend.screenshot(_pending_path(url))
        size = self._discover_size()
        super().__init__(x=0, y=0, w=size[0], h=size[1])

    # ---- Factory -----------------------------------------------------
    @classmethod
    def start(cls, *, url: str, backend: BrowserBackend | None = None) -> "WebScreen":
        existing = _REGISTRY.get(url)
        if existing is not None:
            return existing
        screen = cls(url=url, backend=backend)
        _REGISTRY[url] = screen
        return screen

    @classmethod
    def stop_all(cls) -> None:
        """Tear every cached browser down (used by tests + IDE Close)."""
        for screen in list(_REGISTRY.values()):
            try:
                screen._backend.close()
            except Exception:  # pragma: no cover - cleanup
                pass
        _REGISTRY.clear()

    def stop(self) -> None:
        try:
            self._backend.close()
        finally:
            _REGISTRY.pop(self.url, None)

    # ---- Capture -----------------------------------------------------
    def _capture_bgr(self):
        return self._backend.frame()

    # ---- Actions -----------------------------------------------------
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

    @logged_action("web", "click", target=_fmt_target, surface=_web_surface)
    def click(self, target: PatternLike | None = None) -> int:
        loc = self._loc_for(target)
        page = self._page()
        page.mouse.click(loc.x, loc.y)
        return 1

    @logged_action("web", "double_click", target=_fmt_target, surface=_web_surface)
    def double_click(self, target: PatternLike | None = None) -> int:
        loc = self._loc_for(target)
        page = self._page()
        page.mouse.dblclick(loc.x, loc.y)
        return 1

    @logged_action("web", "right_click", target=_fmt_target, surface=_web_surface)
    def right_click(self, target: PatternLike | None = None) -> int:
        loc = self._loc_for(target)
        page = self._page()
        page.mouse.click(loc.x, loc.y, button="right")
        return 1

    @logged_action("web", "hover", target=_fmt_target, surface=_web_surface)
    def hover(self, target: PatternLike | None = None) -> int:
        loc = self._loc_for(target)
        page = self._page()
        page.mouse.move(loc.x, loc.y)
        return 1

    @logged_action("web", "drag_drop", target=_fmt_drag, surface=_web_surface)
    def drag_drop(
        self,
        src: PatternLike,
        dst: PatternLike,
        *,
        duration_ms: int = 400,
    ) -> int:
        page = self._page()
        src_loc = self._loc_for(src)
        dst_loc = self._loc_for(dst)
        page.mouse.move(src_loc.x, src_loc.y)
        page.mouse.down()
        # Playwright doesn't expose a built-in duration; one tween step
        # is enough for the recorder's needs.
        page.mouse.move(dst_loc.x, dst_loc.y, steps=max(1, duration_ms // 16))
        page.mouse.up()
        return 1

    @logged_action("web", "type", target=_fmt_target, surface=_web_surface)
    def type(self, text: str, modifiers: int = 0) -> int:  # noqa: ARG002
        page = self._page()
        page.keyboard.type(text)
        return len(text)

    def paste(self, text: str) -> int:
        return self.type(text)

    # ---- Navigation --------------------------------------------------
    @logged_action("web", "navigate", target=_fmt_target, surface=_web_surface)
    def navigate(self, url: str) -> int:
        self._backend.goto(url)
        self.url = url
        return 1

    @logged_action("web", "reload", surface=_web_surface)
    def reload(self) -> int:
        page = self._page()
        page.reload()
        return 1

    @logged_action("web", "go_back", surface=_web_surface)
    def go_back(self) -> int:
        page = self._page()
        page.go_back()
        return 1

    @logged_action("web", "go_forward", surface=_web_surface)
    def go_forward(self) -> int:
        page = self._page()
        page.go_forward()
        return 1

    # ---- Internals ---------------------------------------------------
    def _discover_size(self) -> tuple[int, int]:
        """Pull the document size out of the discovery payload.

        Done as part of construction so the :class:`Region` width/height
        match the page's actual scrollable area, not the viewport.
        """
        try:
            result = self._backend.discover()
        except Exception:  # pragma: no cover - real browser only
            return (1024, 768)
        if result.document_size and all(result.document_size):
            return result.document_size
        return (1024, 768)

    def _page(self) -> Any:
        page = getattr(self._backend, "_page", None)
        if page is None:
            raise RuntimeError(
                "WebScreen action attempted before the browser was launched"
            )
        return page


def _pending_path(url: str):
    """Lazy import — keep tempfile out of the import chain on test paths
    that never construct a real WebScreen."""
    import tempfile
    from pathlib import Path
    from urllib.parse import urlparse

    host = (urlparse(url).hostname or "page").replace(".", "_")
    return Path(tempfile.gettempdir()) / f"sikulipy_webscreen_{host}.png"
