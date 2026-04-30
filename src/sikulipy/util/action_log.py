"""Runtime action logging.

A tiny logger that surfaces every script interaction (click, find,
wait, drag, type, swipe, App.open, …) as a structured record so the
IDE Console can show what the script is actually doing.

Design constraints:

* Off by default. Plain ``python script.py`` callers pay essentially
  nothing — the decorator's hot path is one ``logger.level <
  Level.ACTION`` compare and a passthrough call.
* No dependency on :mod:`logging`. The codebase has no existing
  logging conventions; introducing an indirection layer here would
  cost more than it buys. Sinks are plain callables.
* Instrumented methods preserve their signatures and docstrings via
  :func:`functools.wraps`.
* Sinks are called on whatever thread invoked the action; the logger
  guards its own state with a :class:`threading.Lock` so the IDE's
  toolbar thread can attach/detach a sink while the runner thread is
  actively logging.
"""

from __future__ import annotations

import functools
import threading
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Iterable


class Level(IntEnum):
    """Verbosity ladder; values are ordered so ``level >= ACTION`` works."""

    OFF = 0
    ACTION = 1   # one record on entry, one on exit
    VERBOSE = 2  # plus internal events (find attempts, capture sizes, …)


# A "phase" tells the sink whether this record is the start of an
# action ("→ click …") or its result ("✓ in 42 ms" / "✗ FindFailed").
# VERBOSE-only records use Phase.NOTE so they don't pair up.
class Phase(IntEnum):
    START = 0
    OK = 1
    FAIL = 2
    NOTE = 3


@dataclass(frozen=True)
class ActionRecord:
    """One structured log line.

    ``category`` groups records by subsystem (``"region"``, ``"mouse"``,
    ``"app"``, ``"android"``); the IDE may colour them differently. ``verb``
    is the action name (``"click"``, ``"find"``). ``target`` is the
    human-readable subject (``'Pattern("ok.png", 0.7)'`` etc.). ``result``
    carries the success/failure detail for OK/FAIL phases. ``duration_ms``
    is wall-clock time from START → terminal phase. ``surface`` records
    which surface the action ran against (``"desktop"``, an ADB serial,
    or ``None`` if not applicable).
    """

    timestamp: float
    category: str
    verb: str
    target: str
    phase: Phase
    result: str = ""
    duration_ms: float | None = None
    surface: str | None = None


Sink = Callable[[ActionRecord], None]


@dataclass
class ActionLogger:
    """Singleton-style record router.

    The logger holds a verbosity level and a list of sinks. Records
    below the current level are dropped before any sink runs, so the
    perf cost of an instrumented call at ``Level.OFF`` is one int read.
    """

    level: Level = Level.OFF
    _sinks: list[Sink] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def add_sink(self, sink: Sink) -> Callable[[], None]:
        """Register a sink; return an unregister callable."""
        with self._lock:
            self._sinks.append(sink)
        def _remove() -> None:
            with self._lock:
                try:
                    self._sinks.remove(sink)
                except ValueError:
                    pass
        return _remove

    def clear_sinks(self) -> None:
        with self._lock:
            self._sinks.clear()

    def emit(self, record: ActionRecord, *, min_level: Level = Level.ACTION) -> None:
        """Dispatch ``record`` to every sink iff ``self.level >= min_level``.

        ``min_level`` lets the decorator gate START/OK/FAIL records at
        ACTION while letting VERBOSE-only call sites use ``Level.VERBOSE``.
        """
        if self.level < min_level:
            return
        with self._lock:
            sinks = list(self._sinks)
        for sink in sinks:
            try:
                sink(record)
            except Exception:
                # A misbehaving sink mustn't break the script — drop the
                # record on the floor and keep going. Tests assert on
                # *successful* sinks; a broken one is a bug for the IDE
                # to surface, not the runner.
                pass


_logger = ActionLogger()


def get_action_logger() -> ActionLogger:
    """Module-level accessor; the IDE attaches/detaches sinks via this."""
    return _logger


# ---------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------


def logged_action(
    category: str,
    verb: str,
    *,
    target: Callable[..., str] | str | None = None,
    surface: Callable[..., str | None] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Wrap a method so each call emits START + OK/FAIL records.

    ``target`` controls the subject string. Pass a callable
    ``(self, *args, **kwargs) -> str`` for argument-aware formatting,
    a plain string for a fixed label, or ``None`` to use ``repr`` of
    the first positional arg (or ``""`` if there is none).

    ``surface`` is an optional callable that returns the surface name
    for the record — useful on Region/Screen methods where the same
    decorator instance is used across desktop and Android subclasses.

    Hot-path cost at :attr:`Level.OFF`: one ``logger.level`` read and
    a function call. Nothing else runs. At :attr:`Level.ACTION`: two
    record allocations + ``time.perf_counter()`` calls per invocation.
    """

    def _format_target(self_: Any, args: tuple, kwargs: dict) -> str:
        if callable(target):
            try:
                return target(self_, *args, **kwargs)
            except Exception as exc:
                return f"<target-repr failed: {exc}>"
        if isinstance(target, str):
            return target
        if args:
            try:
                return repr(args[0])
            except Exception as exc:
                return f"<repr failed: {exc}>"
        return ""

    def _format_surface(self_: Any, args: tuple, kwargs: dict) -> str | None:
        if surface is None:
            return None
        try:
            return surface(self_, *args, **kwargs)
        except Exception:
            return None

    def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            logger = _logger
            if logger.level < Level.ACTION:
                return fn(self, *args, **kwargs)
            target_str = _format_target(self, args, kwargs)
            surface_str = _format_surface(self, args, kwargs)
            t0 = time.perf_counter()
            logger.emit(
                ActionRecord(
                    timestamp=time.time(),
                    category=category,
                    verb=verb,
                    target=target_str,
                    phase=Phase.START,
                    surface=surface_str,
                )
            )
            try:
                result = fn(self, *args, **kwargs)
            except BaseException as exc:
                duration = (time.perf_counter() - t0) * 1000.0
                logger.emit(
                    ActionRecord(
                        timestamp=time.time(),
                        category=category,
                        verb=verb,
                        target=target_str,
                        phase=Phase.FAIL,
                        result=f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__,
                        duration_ms=duration,
                        surface=surface_str,
                    )
                )
                raise
            duration = (time.perf_counter() - t0) * 1000.0
            logger.emit(
                ActionRecord(
                    timestamp=time.time(),
                    category=category,
                    verb=verb,
                    target=target_str,
                    phase=Phase.OK,
                    result=_short_repr(result),
                    duration_ms=duration,
                    surface=surface_str,
                )
            )
            return result

        return wrapper

    return decorate


def _short_repr(value: Any, *, limit: int = 80) -> str:
    """Compact repr used for OK results.

    Truncates at ``limit`` chars so a Match-with-large-image doesn't
    flood the Console. Returns ``""`` for ``None``.
    """
    if value is None:
        return ""
    try:
        text = repr(value)
    except Exception as exc:
        return f"<repr failed: {exc}>"
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


# ---------------------------------------------------------------------
# Formatting + coalescing helpers (used by sinks)
# ---------------------------------------------------------------------


def format_record(record: ActionRecord) -> str:
    """Render ``record`` as a single Console line.

    Format::

        [12:34:56.789] click Pattern("ok.png") @ desktop in 42 ms
        [12:34:57.001] ✗ click Pattern("missing.png") FindFailed in 3000 ms

    The arrow on START / ✓ on OK / ✗ on FAIL is enough for the user
    to scan a long log; the duration goes only on terminal phases.
    """
    ts = time.strftime("%H:%M:%S", time.localtime(record.timestamp))
    millis = int((record.timestamp - int(record.timestamp)) * 1000)
    head = f"[{ts}.{millis:03d}]"
    icon = {Phase.START: "→", Phase.OK: "✓", Phase.FAIL: "✗", Phase.NOTE: "·"}[record.phase]
    parts = [head, icon, record.verb]
    if record.target:
        parts.append(record.target)
    if record.surface:
        parts.extend(["@", record.surface])
    if record.duration_ms is not None:
        parts.append(f"in {record.duration_ms:.0f} ms")
    if record.result and record.phase == Phase.FAIL:
        parts.extend(["—", record.result])
    return " ".join(parts)


@dataclass
class Coalescer:
    """Stateful filter that collapses identical consecutive records.

    Use it inside a sink: feed each incoming record through
    :meth:`feed`, get back a list of *output* lines (the previous run
    flushed plus the new line, or just the new line, or empty when
    we're still mid-run). Call :meth:`flush` when the script exits to
    drain any pending count.

    Two records "match" iff their (category, verb, target, phase) tuple
    is equal. We deliberately ignore ``duration_ms`` and ``result`` so
    a tight find loop coalesces even when timings vary by µs.
    """

    _key: tuple | None = None
    _count: int = 0
    _last_line: str = ""

    def feed(self, record: ActionRecord) -> list[str]:
        key = (record.category, record.verb, record.target, record.phase)
        line = format_record(record)
        if key == self._key:
            self._count += 1
            return []
        out: list[str] = []
        if self._key is not None:
            if self._count > 1:
                out.append(f"{self._last_line}  × {self._count}")
            else:
                out.append(self._last_line)
        self._key = key
        self._count = 1
        self._last_line = line
        return out

    def flush(self) -> list[str]:
        if self._key is None:
            return []
        if self._count > 1:
            line = f"{self._last_line}  × {self._count}"
        else:
            line = self._last_line
        self._key = None
        self._count = 0
        self._last_line = ""
        return [line]


def collect_records(level: Level = Level.ACTION) -> tuple[list[ActionRecord], Callable[[], None]]:
    """Test helper: attach a list-sink at ``level`` and return ``(records, restore)``.

    Saves and restores the logger's prior level so tests don't leak
    state into each other. Always run ``restore()`` in a teardown.
    """
    prior = _logger.level
    _logger.level = level
    records: list[ActionRecord] = []
    unsubscribe = _logger.add_sink(records.append)

    def restore() -> None:
        unsubscribe()
        _logger.level = prior

    return records, restore


__all__ = [
    "ActionLogger",
    "ActionRecord",
    "Coalescer",
    "Level",
    "Phase",
    "Sink",
    "collect_records",
    "format_record",
    "get_action_logger",
    "logged_action",
]
