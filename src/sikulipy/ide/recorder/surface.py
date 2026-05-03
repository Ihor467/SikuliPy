"""Recording target abstraction.

A ``TargetSurface`` answers "where do recorded actions land?". The two
real implementations today are :class:`_DesktopSurface` (the host's
monitor, captured via ``mss``) and :class:`_AndroidSurface` (a tablet
or phone reachable over ADB, captured via ``screencap``). Tests pin a
:class:`_FakeSurface` so they don't pull in cv2 / mss / adb.

Design notes:

* The surface is the single switch that decides which dispatch verbs
  the codegen should emit (``Screen().click(...)`` vs
  ``screen.click(...)``). It is bound to a :class:`RecorderSession` for
  the session's whole lifetime — switching surfaces drops prior lines.
* ``frame()`` returns a BGR ``ndarray`` rather than a written file so
  the capture overlay (Step 4) can grab a fresh frame for every
  pattern without paying a disk round-trip. The recorder temp dir is
  still where final PNGs live.
* The ``android`` extra (``pure-python-adb``) and ``cv2`` are
  lazy-imported. Installing SikuliPy without those extras must still
  let the recorder run on the desktop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    import numpy as np

    from sikulipy.android.client import ADBDevice


@runtime_checkable
class TargetSurface(Protocol):
    """Where does the next recorded action land?"""

    name: str
    """Stable identifier — ``"desktop"`` / ``"android"`` / ``"fake"``."""

    def frame(self) -> "np.ndarray":
        """Return a fresh BGR snapshot of the surface."""

    def bounds(self) -> tuple[int, int, int, int]:
        """``(x, y, w, h)`` in surface coordinates."""

    def header_imports(self) -> list[str]:
        """Lines to prepend to the generated script's import block."""

    def header_setup(self) -> list[str]:
        """Lines that run after the imports (e.g. ``screen = ADBScreen.start()``).

        Empty list when the desktop generator's bare verbs already
        cover the dispatch path.
        """


# ---------------------------------------------------------------------------
# Desktop
# ---------------------------------------------------------------------------


@dataclass
class _DesktopSurface:
    """The host's primary monitor, captured via ``mss``.

    Matches the behaviour the recorder has shipped with since Phase 7 —
    no surface-specific imports, no per-line receiver. The codegen
    emits ``wait(Pattern(...), t).click()`` etc.
    """

    name: str = "desktop"
    _bounds: tuple[int, int, int, int] | None = field(default=None, repr=False)

    def frame(self) -> "np.ndarray":
        # Lazy imports keep mss / cv2 / numpy out of tests that only
        # care about codegen routing.
        import cv2
        import mss
        import numpy as np

        with mss.mss() as sct:
            mon = sct.monitors[1]
            shot = np.asarray(sct.grab(mon))  # BGRA
        # mss returns BGRA on Linux/macOS; the rest of the pipeline
        # expects BGR (matches OpenCV's default). cv2.cvtColor is
        # cheaper than slicing for large frames.
        bgr = cv2.cvtColor(shot, cv2.COLOR_BGRA2BGR)
        return bgr

    def bounds(self) -> tuple[int, int, int, int]:
        if self._bounds is None:
            import mss

            with mss.mss() as sct:
                mon = sct.monitors[1]
                self._bounds = (
                    int(mon["left"]),
                    int(mon["top"]),
                    int(mon["width"]),
                    int(mon["height"]),
                )
        return self._bounds

    def header_imports(self) -> list[str]:
        return ["from sikulipy import *"]

    def header_setup(self) -> list[str]:
        return []


# ---------------------------------------------------------------------------
# Android (over ADB)
# ---------------------------------------------------------------------------


@dataclass
class _AndroidSurface:
    """An Android device captured via ADB ``screencap``.

    Carries the originating address (USB serial or Wi-Fi ``IP:PORT``)
    so :meth:`header_setup` can emit the matching ``ADBScreen.start()``
    or ``ADBScreen.connect()`` call when the recording is finalized.
    """

    device: "ADBDevice"
    address: str | None = None
    """Wi-Fi address (e.g. ``"192.168.1.50:5555"``); ``None`` for USB."""
    serial: str | None = None
    """USB serial; populated lazily from ``device.serial`` if available."""
    name: str = "android"
    _bounds: tuple[int, int, int, int] | None = field(default=None, repr=False)

    def frame(self) -> "np.ndarray":
        # screencap() already returns a ScreenImage with a BGR ndarray.
        shot = self.device.screencap()
        return shot.bitmap

    def bounds(self) -> tuple[int, int, int, int]:
        if self._bounds is None:
            w, h = self.device.size()
            self._bounds = (0, 0, int(w), int(h))
        return self._bounds

    def header_imports(self) -> list[str]:
        return [
            "from sikulipy import *",
            "from sikulipy.android.screen import ADBScreen",
        ]

    def header_setup(self) -> list[str]:
        if self.address:
            return [f'screen = ADBScreen.connect("{self.address}")']
        if self.serial or (self.device is not None and getattr(self.device, "serial", None)):
            serial = self.serial or self.device.serial
            return [f'screen = ADBScreen.start(serial="{serial}")']
        return ["screen = ADBScreen.start()"]


# ---------------------------------------------------------------------------
# Web (Playwright)
# ---------------------------------------------------------------------------


@dataclass
class _WebSurface:
    """A web page captured via Playwright (Phase 11).

    Holds the URL the recording is bound to so :meth:`header_setup` can
    emit the matching ``WebScreen.start(url=...)`` line. Frames come
    from the active :class:`BrowserBackend`; tests pin a fake.
    """

    url: str
    backend: Any = None
    """A :class:`sikulipy.web.BrowserBackend`. ``None`` resolves to
    ``get_backend()`` lazily so import-time costs stay off the desktop
    surface path."""
    name: str = "web"
    _bounds: tuple[int, int, int, int] | None = field(default=None, repr=False)

    def _resolve_backend(self) -> Any:
        if self.backend is not None:
            return self.backend
        from sikulipy.web import get_backend

        self.backend = get_backend()
        return self.backend

    def frame(self) -> "np.ndarray":
        backend = self._resolve_backend()
        return backend.frame()

    def bounds(self) -> tuple[int, int, int, int]:
        if self._bounds is None:
            backend = self._resolve_backend()
            try:
                result = backend.discover()
            except Exception:
                result = None
            if result is not None and all(result.document_size):
                w, h = result.document_size
            else:
                w, h = 1024, 768
            self._bounds = (0, 0, int(w), int(h))
        return self._bounds

    def header_imports(self) -> list[str]:
        return [
            "from sikulipy import *",
            "from sikulipy.web.screen import WebScreen",
        ]

    def header_setup(self) -> list[str]:
        url = (self.url or "").replace("\\", "\\\\").replace('"', '\\"')
        return [f'screen = WebScreen.start(url="{url}")']


# ---------------------------------------------------------------------------
# Fake (tests)
# ---------------------------------------------------------------------------


@dataclass
class _FakeSurface:
    """In-memory surface for tests.

    Holds an in-memory frame (``Any`` so tests can pass a sentinel
    instead of a real ndarray) and pre-canned bounds. Generates no
    headers / setup unless the test sets ``imports`` / ``setup``
    explicitly — tests that exercise the codegen surface dispatch
    use this to stand in for both desktop and android cases.
    """

    name: str = "fake"
    _frame: Any = None
    _bounds_value: tuple[int, int, int, int] = (0, 0, 100, 100)
    imports: list[str] = field(default_factory=list)
    setup: list[str] = field(default_factory=list)
    frame_calls: int = 0

    def frame(self) -> Any:
        self.frame_calls += 1
        return self._frame

    def bounds(self) -> tuple[int, int, int, int]:
        return self._bounds_value

    def header_imports(self) -> list[str]:
        return list(self.imports)

    def header_setup(self) -> list[str]:
        return list(self.setup)


def default_surface() -> TargetSurface:
    """Factory used by :class:`RecorderSession` when no surface is passed."""
    return _DesktopSurface()
