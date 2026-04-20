"""Guide backend Protocol + swappable singletons.

Same pattern as every other backend module in this project: a Protocol,
a lazy default, and an override setter for tests.

The default is :class:`_FletGuideBackend`, which paints the composed
shapes onto a transparent Flet window. On hosts without Flet or a
display, the resolver falls back to :class:`_NullGuideBackend` which
simply records the call — perfectly fine for unit tests.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:  # numpy/cv2 are optional
    import numpy as np

    from sikulipy.guide.shapes import Shape


class GuideBackend(Protocol):
    def show(self, shapes: "list[Shape]", *, duration: float | None = None) -> None: ...
    def hide(self) -> None: ...
    def is_visible(self) -> bool: ...


# ---------------------------------------------------------------------------
# Null (test) backend
# ---------------------------------------------------------------------------


@dataclass
class _NullGuideBackend:
    """Records show/hide calls — the default on hosts without a display."""

    shown: list[tuple[list, float | None]] = field(default_factory=list)
    hidden: int = 0
    _visible: bool = False

    def show(self, shapes, *, duration=None):  # noqa: ANN001
        self.shown.append((list(shapes), duration))
        self._visible = True
        if duration is not None and duration > 0:
            # Keep the null backend truly synchronous for tests: sleep
            # only when the caller asks for a blocking display.
            time.sleep(duration)
            self._visible = False

    def hide(self):
        self.hidden += 1
        self._visible = False

    def is_visible(self) -> bool:
        return self._visible


# ---------------------------------------------------------------------------
# Flet backend
# ---------------------------------------------------------------------------


class _FletGuideBackend:
    """Paint shapes into a frameless transparent Flet window.

    Composition: build a BGR canvas sized to the virtual screen,
    ``draw()`` each shape onto it, PNG-encode, and hand it to an
    ``ft.Image`` control in a frameless, translucent window.
    """

    def __init__(self) -> None:
        # Deferred import so the null backend still works when flet is
        # missing.
        import flet as ft  # noqa: F401

        self._page = None
        self._image_control = None
        self._visible = False
        self._hide_timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def show(self, shapes, *, duration=None):  # noqa: ANN001
        import flet as ft

        canvas, width, height = _compose(shapes)
        png_bytes = _encode_png(canvas)

        def _render(page: ft.Page) -> None:
            page.window_frameless = True
            page.window_always_on_top = True
            page.window_bgcolor = ft.Colors.TRANSPARENT
            page.bgcolor = ft.Colors.TRANSPARENT
            page.window_width = width
            page.window_height = height
            page.window_left = 0
            page.window_top = 0
            page.padding = 0
            image = ft.Image(src_base64=_b64(png_bytes), width=width, height=height)
            self._image_control = image
            self._page = page
            page.controls.clear()
            page.add(image)
            page.update()

        with self._lock:
            threading.Thread(
                target=lambda: ft.app(target=_render),  # type: ignore[arg-type]
                daemon=True,
            ).start()
            self._visible = True
            if duration is not None and duration > 0:
                self._hide_timer = threading.Timer(duration, self.hide)
                self._hide_timer.daemon = True
                self._hide_timer.start()

    def hide(self):
        with self._lock:
            if self._hide_timer is not None:
                self._hide_timer.cancel()
                self._hide_timer = None
            if self._page is not None:
                try:
                    self._page.window_close()  # type: ignore[attr-defined]
                except Exception:
                    pass
                self._page = None
            self._visible = False

    def is_visible(self) -> bool:
        return self._visible


# ---------------------------------------------------------------------------
# Composition helpers
# ---------------------------------------------------------------------------


def _virtual_screen_size() -> tuple[int, int]:
    try:
        from sikulipy.core.screen import Screen

        screen = Screen.get_primary()
        return int(screen.w or 1920), int(screen.h or 1080)
    except Exception:
        return 1920, 1080


def _compose(shapes) -> "tuple[np.ndarray, int, int]":  # noqa: ANN001
    import numpy as np

    width, height = _virtual_screen_size()
    # Union every shape's bounds with the primary screen so the canvas
    # is always big enough to host the shape in screen coordinates.
    for shape in shapes:
        x, y, w, h = shape.bounds()
        width = max(width, x + w)
        height = max(height, y + h)
    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    for shape in shapes:
        shape.draw(canvas)
    return canvas, width, height


def _encode_png(canvas: "np.ndarray") -> bytes:
    import cv2

    ok, buf = cv2.imencode(".png", canvas)
    if not ok:
        raise RuntimeError("cv2.imencode failed for guide canvas")
    return bytes(buf)


def _b64(data: bytes) -> str:
    import base64

    return base64.b64encode(data).decode("ascii")


# ---------------------------------------------------------------------------
# Singleton hook
# ---------------------------------------------------------------------------


_backend: GuideBackend | None = None


def get_backend() -> GuideBackend:
    global _backend
    if _backend is None:
        _backend = _resolve_default()
    return _backend


def set_backend(backend: GuideBackend | None) -> None:
    """Swap the active backend. ``None`` forces a re-resolve."""
    global _backend
    _backend = backend


def _resolve_default() -> GuideBackend:
    try:
        import flet  # noqa: F401
        import cv2  # noqa: F401
    except Exception:
        return _NullGuideBackend()
    try:
        return _FletGuideBackend()
    except Exception:
        return _NullGuideBackend()
