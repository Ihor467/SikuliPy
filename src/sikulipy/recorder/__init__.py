"""Recorder — port of ``org.sikuli.support.recorder``.

Captures user interactions (clicks, keystrokes, swipes) and generates an
equivalent Python ``sikulipy`` script.

Architecture mirrors the rest of the port:

* :class:`InputListener` is a Protocol — the default implementation uses
  ``pynput`` global listeners; tests inject a recording fake.
* :class:`ActionRecorder` collects :class:`RecordedAction` events and can
  emit ready-to-run script source via :meth:`generate_script`.
* :func:`set_listener_factory` swaps the listener at runtime, so unit
  tests never need pynput.

The recorder optionally captures pattern PNGs around each click so the
generated script can use :class:`Pattern` references; if no
``screenshotter`` is supplied, clicks are emitted as bare coordinates.
"""

from __future__ import annotations

import string
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Literal, Protocol

if TYPE_CHECKING:  # numpy is optional on this host
    import numpy as np

ActionKind = Literal["click", "double_click", "right_click", "type", "wait"]


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


@dataclass
class RecordedAction:
    kind: ActionKind
    timestamp: float
    x: int | None = None
    y: int | None = None
    text: str | None = None
    duration: float | None = None
    pattern: Path | None = None


# ---------------------------------------------------------------------------
# Listener Protocol
# ---------------------------------------------------------------------------


class InputListener(Protocol):
    """Receives raw input events and forwards them to a recorder."""

    def start(self) -> None: ...
    def stop(self) -> None: ...


@dataclass
class _PynputListener:
    """Default :class:`InputListener` backed by ``pynput``."""

    on_click: Callable[[int, int, str, bool], None]
    on_key: Callable[[str], None]
    _mouse: object | None = field(default=None, init=False, repr=False)
    _keyboard: object | None = field(default=None, init=False, repr=False)

    def start(self) -> None:  # pragma: no cover - requires a display server
        from pynput import keyboard, mouse  # type: ignore[import-not-found]

        def _click(x, y, button, pressed):  # noqa: ANN001
            if not pressed:
                return
            name = getattr(button, "name", str(button))
            self.on_click(int(x), int(y), name, False)

        def _press(key):  # noqa: ANN001
            try:
                ch = key.char
            except AttributeError:
                ch = f"<{getattr(key, 'name', 'key')}>"
            if ch is not None:
                self.on_key(ch)

        self._mouse = mouse.Listener(on_click=_click)
        self._keyboard = keyboard.Listener(on_press=_press)
        self._mouse.start()
        self._keyboard.start()

    def stop(self) -> None:  # pragma: no cover
        for listener in (self._mouse, self._keyboard):
            if listener is not None:
                listener.stop()


_listener_factory: Callable[..., InputListener] = _PynputListener


def set_listener_factory(factory: Callable[..., InputListener] | None) -> None:
    """Override the listener constructor (e.g. in tests). ``None`` resets."""
    global _listener_factory
    _listener_factory = factory if factory is not None else _PynputListener


def get_listener_factory() -> Callable[..., InputListener]:
    return _listener_factory


# ---------------------------------------------------------------------------
# Recorder
# ---------------------------------------------------------------------------


# Time gap (seconds) above which we emit a wait() between actions.
_WAIT_THRESHOLD = 0.5
# Pattern crop half-size in pixels around the click point.
_PATTERN_HALF = 24


@dataclass
class ActionRecorder:
    """Collects recorded actions and synthesises a sikulipy script.

    ``screenshotter`` (optional) is a zero-arg callable returning the
    current screen as a BGR ndarray. When provided, each click captures
    a small pattern crop into ``pattern_dir`` and the generated script
    references it via ``Pattern("clickN.png")``.
    """

    pattern_dir: Path | None = None
    screenshotter: Callable[[], "np.ndarray"] | None = None
    _actions: list[RecordedAction] = field(default_factory=list, repr=False)
    _pending_text: list[str] = field(default_factory=list, repr=False)
    _pending_text_ts: float | None = field(default=None, repr=False)
    _listener: InputListener | None = field(default=None, init=False, repr=False)
    _running: bool = field(default=False, init=False, repr=False)
    _click_seq: int = field(default=0, init=False, repr=False)
    _now: Callable[[], float] = field(default=time.monotonic, repr=False)

    # ---- Lifecycle --------------------------------------------------
    def start(self) -> None:
        if self._running:
            return
        factory = get_listener_factory()
        self._listener = factory(on_click=self._record_click, on_key=self._record_key)
        self._listener.start()
        self._running = True

    def stop(self) -> None:
        if not self._running:
            return
        self._flush_text()
        if self._listener is not None:
            self._listener.stop()
        self._listener = None
        self._running = False

    # ---- Event handlers --------------------------------------------
    def _record_click(self, x: int, y: int, button: str, double: bool) -> None:
        self._flush_text()
        ts = self._now()
        self._maybe_emit_wait(ts)
        kind: ActionKind = "click"
        if button == "right":
            kind = "right_click"
        elif double:
            kind = "double_click"
        pattern = self._capture_pattern(x, y)
        self._actions.append(
            RecordedAction(kind=kind, timestamp=ts, x=x, y=y, pattern=pattern)
        )

    def _record_key(self, ch: str) -> None:
        ts = self._now()
        if not self._pending_text:
            self._maybe_emit_wait(ts)
            self._pending_text_ts = ts
        self._pending_text.append(ch)

    def _flush_text(self) -> None:
        if not self._pending_text:
            return
        text = "".join(self._pending_text)
        ts = self._pending_text_ts or self._now()
        self._actions.append(RecordedAction(kind="type", timestamp=ts, text=text))
        self._pending_text.clear()
        self._pending_text_ts = None

    def _maybe_emit_wait(self, ts: float) -> None:
        if not self._actions:
            return
        gap = ts - self._actions[-1].timestamp
        if gap >= _WAIT_THRESHOLD:
            self._actions.append(
                RecordedAction(kind="wait", timestamp=ts, duration=round(gap, 2))
            )

    # ---- Pattern capture -------------------------------------------
    def _capture_pattern(self, x: int, y: int) -> Path | None:
        if self.screenshotter is None or self.pattern_dir is None:
            return None
        try:
            import cv2  # type: ignore[import-not-found]
        except Exception:
            return None
        try:
            img = self.screenshotter()
        except Exception:
            return None
        if img is None:
            return None
        h, w = img.shape[:2]
        x0 = max(0, x - _PATTERN_HALF)
        y0 = max(0, y - _PATTERN_HALF)
        x1 = min(w, x + _PATTERN_HALF)
        y1 = min(h, y + _PATTERN_HALF)
        if x1 <= x0 or y1 <= y0:
            return None
        crop = img[y0:y1, x0:x1]
        self._click_seq += 1
        self.pattern_dir.mkdir(parents=True, exist_ok=True)
        target = self.pattern_dir / f"click{self._click_seq}.png"
        if not bool(cv2.imwrite(str(target), crop)):
            return None
        return target

    # ---- Output -----------------------------------------------------
    def actions(self) -> list[RecordedAction]:
        # Don't expose pending text — it isn't a complete action yet.
        return list(self._actions)

    def clear(self) -> None:
        self._actions.clear()
        self._pending_text.clear()
        self._pending_text_ts = None
        self._click_seq = 0

    def generate_script(self) -> str:
        """Return runnable Python source equivalent to the recording."""
        self._flush_text()
        lines = [
            "# Auto-generated by sikulipy.recorder",
            "from sikulipy.core.region import Region",
            "from sikulipy.core.screen import Screen",
            "from sikulipy.core.pattern import Pattern",
            "import time",
            "",
            "screen = Screen.get_primary()",
            "",
        ]
        for action in self._actions:
            lines.append(_emit(action))
        return "\n".join(lines) + "\n"


def _emit(a: RecordedAction) -> str:
    if a.kind == "wait":
        return f"time.sleep({a.duration!r})"
    if a.kind == "type":
        return f"screen.type({_py_string(a.text or '')})"
    target = (
        f"Pattern({str(a.pattern)!r})"
        if a.pattern is not None
        else f"({a.x}, {a.y})"
    )
    method = {"click": "click", "double_click": "double_click", "right_click": "right_click"}[a.kind]
    return f"screen.{method}({target})"


def _py_string(text: str) -> str:
    """Repr a string preferring double quotes if no awkward chars."""
    if all(c in string.printable and c not in "\\\"\n\r\t" for c in text):
        return f'"{text}"'
    return repr(text)
