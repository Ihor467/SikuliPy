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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from sikulipy.ide.capture import CaptureSession
from sikulipy.ide.editor import EditorDocument


class RunnerHost(Protocol):
    """Launches scripts. Default impl shells out to :mod:`sikulipy.runners`."""

    def run(self, path: Path) -> int: ...
    def stop(self) -> None: ...
    def is_running(self) -> bool: ...


@dataclass
class _DefaultRunnerHost:
    """Background-thread runner that calls :func:`sikulipy.runners.run_file`."""

    _thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _exit_code: int | None = field(default=None, init=False, repr=False)

    def run(self, path: Path) -> int:
        from sikulipy.runners import run_file

        if self.is_running():
            raise RuntimeError("a script is already running")

        self._exit_code = None

        def _target() -> None:
            try:
                self._exit_code = run_file(str(path))
            except BaseException as exc:  # pragma: no cover
                self._exit_code = 1
                raise exc

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
    runner: RunnerHost = field(default_factory=_DefaultRunnerHost)
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
