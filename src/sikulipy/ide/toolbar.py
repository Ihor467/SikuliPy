"""Toolbar actions — Run, Stop, Capture, New, Open, Save.

Ports the *behaviour* of ``ButtonCapture.java`` and the run/stop buttons
in ``ButtonOnToolbar.java``. The Flet toolbar in :mod:`sikulipy.ide.app`
binds its buttons to a :class:`ToolbarActions` instance.

Script execution is delegated through a :class:`RunnerHost` Protocol so
unit tests can assert which file was launched without spawning a real
process.
"""

from __future__ import annotations

import contextlib
import threading
import traceback
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from sikulipy.ide.capture import CaptureSession
from sikulipy.ide.console import ConsoleBuffer, ConsoleEntry, ConsoleRedirect
from sikulipy.ide.editor import EditorDocument
from sikulipy.util.action_log import (
    Coalescer,
    Level,
    format_record,
    get_action_logger,
)


# Bump the Console ring buffer while the logger is active. A tight
# wait()/exists() loop can fire dozens of records per second; the
# default 2000-entry cap fills in seconds. Restored on script exit so
# memory doesn't grow without bound across sessions.
_RUNNING_CONSOLE_CAP = 10_000


class RunnerHost(Protocol):
    """Launches scripts. Default impl shells out to :mod:`sikulipy.runners`."""

    def run(self, path: Path) -> int: ...
    def stop(self) -> None: ...
    def is_running(self) -> bool: ...


@dataclass
class DefaultRunnerHost:
    """Background-thread runner that calls :func:`sikulipy.runners.run_file`.

    When ``console`` is provided, stdout/stderr from the running script
    (including any uncaught traceback) are redirected into the given
    :class:`ConsoleBuffer` via :class:`ConsoleRedirect`, so the IDE's
    console pane shows script output instead of the terminal that
    launched the IDE.

    ``on_finished`` (optional) is invoked from the runner thread once the
    script returns, with the integer exit code. Useful for the Flet view
    to refresh toolbar state and the status line when a script ends.
    """

    console: ConsoleBuffer | None = None
    on_finished: Callable[[int], None] | None = None
    # Action-log level applied for the duration of each run. None means
    # "leave the logger alone" — useful for tests that don't want the
    # runner to clobber a level they set up.
    action_log_level: Level | None = Level.ACTION
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _exit_code: int | None = field(default=None, init=False, repr=False)

    @property
    def exit_code(self) -> int | None:
        return self._exit_code

    def run(self, path: Path) -> int:
        from sikulipy.runners import run_file

        if self.is_running():
            raise RuntimeError("a script is already running")

        self._exit_code = None

        def _body() -> None:
            try:
                self._exit_code = run_file(str(path))
            except BaseException:
                # Route the traceback through the (possibly redirected)
                # sys.stderr so it lands in the IDE console rather than
                # the launching terminal. Re-raising here would just be
                # swallowed by the thread with a "Exception in thread …"
                # banner on the real stderr — no help to the user.
                self._exit_code = 1
                traceback.print_exc()

        def _target() -> None:
            try:
                if self.console is not None:
                    with ConsoleRedirect(self.console, tee=True):
                        with self._action_log_session(self.console):
                            _body()
                else:
                    with self._action_log_session(None):
                        _body()
            finally:
                if self.on_finished is not None:
                    try:
                        self.on_finished(self._exit_code if self._exit_code is not None else 0)
                    except Exception:
                        traceback.print_exc()

        self._thread = threading.Thread(target=_target, daemon=True)
        self._thread.start()
        return 0

    def stop(self) -> None:
        # In-process runners can't be cancelled mid-flight without nasty
        # signalling — match the Java behaviour: best-effort no-op when
        # the script doesn't poll for a stop flag.
        pass

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @contextlib.contextmanager
    def _action_log_session(self, console: ConsoleBuffer | None):
        """Bind the global ActionLogger to ``console`` for one script run.

        Sets the level (if requested), bumps the console capacity to
        absorb log volume from tight loops, attaches a Coalescer-backed
        sink that writes ``format_record`` lines to the console, and
        restores all three on exit. Safe to nest with no console — then
        only the level is touched.
        """
        logger = get_action_logger()
        prior_level = logger.level
        if self.action_log_level is not None:
            logger.level = self.action_log_level

        prior_cap: int | None = None
        prior_entries: deque[ConsoleEntry] | None = None
        unsubscribe: Callable[[], None] | None = None
        coalescer: Coalescer | None = None

        if console is not None and logger.level >= Level.ACTION:
            # Resize the ring buffer in place so existing subscribers
            # (the Flet view) keep their reference. deque(maxlen=N) is
            # the cheapest way to grow it; old entries carry over.
            prior_cap = console.max_entries
            if prior_cap < _RUNNING_CONSOLE_CAP:
                prior_entries = console._entries
                console.max_entries = _RUNNING_CONSOLE_CAP
                console._entries = deque(prior_entries, maxlen=_RUNNING_CONSOLE_CAP)

            coalescer = Coalescer()

            def _sink(record) -> None:  # noqa: ANN001 — ActionRecord
                lines = coalescer.feed(record)
                for line in lines:
                    console.write("stdout", line + "\n")

            unsubscribe = logger.add_sink(_sink)

        try:
            yield
        finally:
            if unsubscribe is not None:
                # Drain the coalescer so the last buffered run lands in
                # the console rather than getting silently dropped.
                if coalescer is not None and console is not None:
                    for line in coalescer.flush():
                        console.write("stdout", line + "\n")
                unsubscribe()
            if prior_cap is not None and console is not None:
                console.max_entries = prior_cap
                # Don't rebuild _entries — shrinking would discard log
                # output the user can still scroll back to. The next
                # write() will trim naturally as new entries arrive.
            logger.level = prior_level


@dataclass
class ToolbarActions:
    """Bridges UI buttons to editor + runner + capture state."""

    document: EditorDocument
    runner: RunnerHost = field(default_factory=DefaultRunnerHost)
    capture: CaptureSession = field(default_factory=CaptureSession)
    on_open: Callable[[Path], None] | None = None
    on_status: Callable[[str], None] | None = None

    # ---- File actions ----------------------------------------------
    def new(self) -> None:
        self.document.set_text("")
        self.document.path = None
        self.document.dirty = False
        self._status("New buffer")

    def open(self, path: str | Path) -> None:
        opened = EditorDocument.open(path)
        self.document.text = opened.text
        self.document.path = opened.path
        self.document.cursor = opened.cursor
        self.document.dirty = False
        if self.on_open is not None:
            self.on_open(opened.path) if opened.path else None
        self._status(f"Opened {opened.path}")

    def save(self, path: str | Path | None = None) -> Path:
        target = self.document.save(path)
        self._status(f"Saved {target}")
        return target

    # ---- Run / stop ------------------------------------------------
    def run(self) -> None:
        if self.document.path is None:
            raise RuntimeError("cannot run an unsaved buffer — save it first")
        if self.document.dirty:
            self.document.save()
        self.runner.run(self.document.path)
        self._status(f"Running {self.document.path.name}")

    def stop(self) -> None:
        self.runner.stop()
        self._status("Stop requested")

    def is_running(self) -> bool:
        return self.runner.is_running()

    # ---- Capture ---------------------------------------------------
    def begin_capture(self) -> CaptureSession:
        self.capture.reset()
        self._status("Capture: drag to select")
        return self.capture

    # ---- Helpers ---------------------------------------------------
    def _status(self, msg: str) -> None:
        if self.on_status is not None:
            self.on_status(msg)
