"""Browser backend Protocol + Playwright impl + in-memory fake.

The IDE and tests both talk to a :class:`BrowserBackend`; only one
implementation actually drives Chromium. ``get_backend()`` is a lazy
singleton — if the user installs the ``web`` extra, ``set_backend()``
swaps in the Playwright impl on first call; otherwise the fake stays
in place. This mirrors the pattern used by ocr / natives / guide.

Discovery returns a ``DiscoveryResult`` (a typed dict alias for what
the JS payload yields) so the IDE controller can pull both the element
list and the device-pixel-ratio out of one round-trip.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from sikulipy.web.elements import DISCOVERY_JS, WebElement, from_record

if TYPE_CHECKING:
    import numpy as np


@dataclass(frozen=True)
class DiscoveryResult:
    """Output of one ``BrowserBackend.discover()`` call."""

    elements: list[WebElement]
    device_pixel_ratio: float = 1.0
    document_size: tuple[int, int] = (0, 0)


@runtime_checkable
class BrowserBackend(Protocol):
    """Drives a real or fake browser for the Web Auto recorder."""

    def launch(self, *, headed: bool = True) -> None:
        """Start the browser process. No-op if already running."""

    def goto(self, url: str, *, timeout_ms: int = 30000) -> None:
        """Navigate to ``url`` and wait for ``networkidle``."""

    def screenshot(self, target: Path) -> Path:
        """Write a full-page PNG to ``target`` and return the path."""

    def frame(self) -> "np.ndarray":
        """Return the latest screenshot as a BGR ndarray."""

    def discover(self) -> DiscoveryResult:
        """Run the discovery JS and return the result."""

    def close(self) -> None:
        """Tear the browser down. Idempotent."""


# ---------------------------------------------------------------------------
# Fake (tests + headless CI)
# ---------------------------------------------------------------------------


@dataclass
class _FakeBackend:
    """In-memory backend used in tests.

    Tests prime ``elements_payload`` (raw discovery records) and
    optionally a ``frame_factory`` so the controller can exercise the
    full ``launch → goto → discover → screenshot`` loop without a real
    browser. Every public call appends to ``calls`` so assertions can
    pin behaviour without monkey-patching.
    """

    name: str = "fake"
    elements_payload: list[dict] = field(default_factory=list)
    device_pixel_ratio: float = 1.0
    document_size: tuple[int, int] = (1024, 768)
    frame_factory: Any = None
    """Callable returning a BGR ndarray, or None to skip cv2 entirely."""
    screenshot_factory: Any = None
    """Callable ``(target: Path) -> Path``; default writes a stub file."""
    calls: list[tuple[str, tuple, dict]] = field(default_factory=list)
    closed: bool = False
    launched: bool = False
    current_url: str | None = None

    def _record(self, name: str, *args, **kwargs) -> None:
        self.calls.append((name, args, kwargs))

    def launch(self, *, headed: bool = True) -> None:
        self._record("launch", headed=headed)
        self.launched = True
        self.closed = False

    def goto(self, url: str, *, timeout_ms: int = 30000) -> None:
        self._record("goto", url, timeout_ms=timeout_ms)
        self.current_url = url

    def screenshot(self, target: Path) -> Path:
        self._record("screenshot", target)
        if self.screenshot_factory is not None:
            return self.screenshot_factory(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Write a 1x1 PNG so callers that try to load the file get
        # something rather than a missing path.
        target.write_bytes(_TINY_PNG)
        return target

    def frame(self) -> "np.ndarray":
        self._record("frame")
        if self.frame_factory is None:
            raise RuntimeError("_FakeBackend.frame_factory not set")
        return self.frame_factory()

    def discover(self) -> DiscoveryResult:
        self._record("discover")
        elements = [from_record(rec) for rec in self.elements_payload]
        return DiscoveryResult(
            elements=elements,
            device_pixel_ratio=self.device_pixel_ratio,
            document_size=self.document_size,
        )

    def close(self) -> None:
        self._record("close")
        self.closed = True
        self.launched = False


# 1x1 transparent PNG — small enough to inline, lets fake screenshots
# round-trip through Pillow / Flet without errors.
_TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae"
    "426082"
)


# ---------------------------------------------------------------------------
# Playwright (real browser)
# ---------------------------------------------------------------------------


class _PlaywrightBackend:
    """Headed Chromium driven via Playwright sync API.

    Playwright's sync API refuses to run inside an asyncio event loop
    (and Flet runs one), and the resulting handles are pinned to the
    thread that created them. So every call is routed through a
    dedicated worker thread with its own loop-free context.
    """

    name: str = "playwright"

    def __init__(self) -> None:
        import queue
        import threading

        self._pw: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._last_screenshot: Path | None = None
        self._last_frame_bytes: bytes | None = None
        self._calls: "queue.Queue[Any]" = queue.Queue()
        self._thread: threading.Thread | None = None

    def _ensure_worker(self) -> None:
        import threading

        if self._thread is not None and self._thread.is_alive():
            return

        def _run() -> None:
            while True:
                item = self._calls.get()
                if item is None:
                    return
                fn, result_q = item
                try:
                    result_q.put(("ok", fn()))
                except BaseException as exc:  # noqa: BLE001
                    result_q.put(("err", exc))

        self._thread = threading.Thread(
            target=_run, name="sikulipy-playwright", daemon=True
        )
        self._thread.start()

    def _submit(self, fn: Any) -> Any:
        import queue

        self._ensure_worker()
        result_q: "queue.Queue[Any]" = queue.Queue(maxsize=1)
        self._calls.put((fn, result_q))
        kind, payload = result_q.get()
        if kind == "err":
            raise payload
        return payload

    def launch(self, *, headed: bool = True) -> None:  # pragma: no cover - real browser
        def _do() -> None:
            if self._page is not None:
                return
            from playwright.sync_api import sync_playwright

            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(headless=not headed)
            self._context = self._browser.new_context()
            self._page = self._context.new_page()

        self._submit(_do)

    def goto(self, url: str, *, timeout_ms: int = 30000) -> None:  # pragma: no cover
        def _do() -> None:
            if self._page is None:
                raise RuntimeError("call launch() before goto()")
            # ``networkidle`` is unreliable on modern sites — analytics,
            # ads and websockets keep the network busy past the 30 s
            # default and the whole goto raises. ``load`` returns once
            # the page's load event fires; if even that times out we
            # swallow the error and keep whatever rendered so far so
            # the IDE can still snapshot + discover.
            try:
                self._page.goto(url, timeout=timeout_ms, wait_until="load")
            except Exception:
                try:
                    self._page.wait_for_load_state(
                        "domcontentloaded", timeout=2000
                    )
                except Exception:
                    pass

        self._submit(_do)

    def screenshot(self, target: Path) -> Path:  # pragma: no cover
        def _do() -> Path:
            if self._page is None:
                raise RuntimeError("call launch() before screenshot()")
            target.parent.mkdir(parents=True, exist_ok=True)
            png_bytes = self._page.screenshot(full_page=True, type="png")
            target.write_bytes(png_bytes)
            self._last_screenshot = target
            self._last_frame_bytes = png_bytes
            return target

        return self._submit(_do)

    def frame(self) -> "np.ndarray":  # pragma: no cover
        import cv2
        import numpy as np

        if self._last_frame_bytes is None:
            raise RuntimeError("call screenshot() before frame()")
        arr = np.frombuffer(self._last_frame_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError("cv2.imdecode failed")
        return img

    def discover(self) -> DiscoveryResult:  # pragma: no cover
        def _do() -> DiscoveryResult:
            if self._page is None:
                raise RuntimeError("call launch() before discover()")
            payload = self._page.evaluate(DISCOVERY_JS)
            records = payload.get("elements") or []
            dpr = float(payload.get("devicePixelRatio") or 1.0)
            size = payload.get("documentSize") or [0, 0]
            return DiscoveryResult(
                elements=[from_record(rec) for rec in records],
                device_pixel_ratio=dpr,
                document_size=(int(size[0]), int(size[1])),
            )

        return self._submit(_do)

    def close(self) -> None:  # pragma: no cover
        def _do() -> None:
            try:
                if self._page is not None:
                    self._page.close()
                if self._context is not None:
                    self._context.close()
                if self._browser is not None:
                    self._browser.close()
                if self._pw is not None:
                    self._pw.stop()
            finally:
                self._page = self._context = self._browser = self._pw = None

        try:
            self._submit(_do)
        finally:
            if self._thread is not None and self._thread.is_alive():
                self._calls.put(None)
                self._thread.join(timeout=2)
            self._thread = None


# ---------------------------------------------------------------------------
# Module singleton
# ---------------------------------------------------------------------------

_backend: BrowserBackend | None = None


def get_backend() -> BrowserBackend:
    """Return the active backend, creating one on first call.

    On hosts with the ``web`` extra installed we instantiate
    :class:`_PlaywrightBackend`; otherwise we fall back to
    :class:`_FakeBackend` so import-time failures don't take the IDE
    down. The IDE's Web Auto button surfaces a hint to ``pip install
    sikulipy[web]`` when the active backend is the fake one.
    """
    global _backend
    if _backend is not None:
        return _backend
    try:
        import playwright  # noqa: F401  -- existence probe only
    except ImportError:
        _backend = _FakeBackend()
        return _backend
    _backend = _PlaywrightBackend()
    return _backend


def set_backend(backend: BrowserBackend) -> None:
    """Replace the active backend (used by tests)."""
    global _backend
    _backend = backend


def reset_backend() -> None:
    """Drop the singleton so the next ``get_backend()`` re-resolves."""
    global _backend
    _backend = None
