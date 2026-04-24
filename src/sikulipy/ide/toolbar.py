"""Toolbar actions — Run, Stop, Capture, New, Open, Save.

Ports the *behaviour* of ``ButtonCapture.java`` and the run/stop buttons
in ``ButtonOnToolbar.java``. The Flet toolbar in :mod:`sikulipy.ide.app`
binds its buttons to a :class:`ToolbarActions` instance.

Script execution is delegated through a :class:`RunnerHost` Protocol so
unit tests can assert which file was launched without spawning a real
process.
"""

from __future__ import annotations

import threading
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from sikulipy.ide.capture import CaptureSession
from sikulipy.ide.console import ConsoleBuffer, ConsoleRedirect
from sikulipy.ide.editor import EditorDocument


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
                        _body()
                else:
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
