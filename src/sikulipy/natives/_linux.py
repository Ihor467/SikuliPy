"""Linux (X11) window-manager backend.

Uses ``python-xlib`` + ``ewmh``; lazy-imported so
:mod:`sikulipy.natives` is safe on hosts without either. Wayland is
currently unsupported — fall back to :class:`_NullBackend`.
"""

from __future__ import annotations

import os
import signal
import subprocess

from sikulipy.natives.types import NotSupportedError, WindowInfo


class _LinuxBackend:
    name = "linux"

    def __init__(self) -> None:
        if not os.environ.get("DISPLAY"):
            raise NotSupportedError("no DISPLAY — X11 backend disabled")
        try:
            from ewmh import EWMH  # noqa: F401
            from Xlib import display  # noqa: F401
        except ImportError as exc:  # pragma: no cover - Linux-only
            raise NotSupportedError(
                "_LinuxBackend requires python-xlib + ewmh; install sikulipy[app]"
            ) from exc
        self._ewmh = None

    def _wm(self):
        if self._ewmh is None:
            from ewmh import EWMH

            self._ewmh = EWMH()
        return self._ewmh

    # ---- Launch / close ------------------------------------------
    def open(self, name: str, *, args: list[str] | None = None) -> int:
        argv = [name, *(args or [])]
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL)  # noqa: S603
        return int(proc.pid)

    def close(self, pid: int) -> bool:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return False
        return True

    # ---- Focus ---------------------------------------------------
    def focus(self, pid: int, *, title: str | None = None) -> bool:
        wm = self._wm()
        target = None
        for w in self.all_windows():
            if w.pid != pid:
                continue
            if title is None or title.lower() in w.title.lower():
                target = w
                break
        if target is None and title is not None:
            target = self.find_by_title(title)
        if target is None:
            return False
        try:
            raw = self._window_by_id(target.handle)
            wm.setActiveWindow(raw)
            wm.display.flush()
        except Exception:
            return False
        return True

    # ---- Enumeration --------------------------------------------
    def focused_window(self) -> WindowInfo | None:
        wm = self._wm()
        try:
            active = wm.getActiveWindow()
        except Exception:
            return None
        if active is None:
            return None
        return self._info_for(active)

    def windows_for(self, pid: int) -> list[WindowInfo]:
        return [w for w in self.all_windows() if w.pid == pid]

    def all_windows(self) -> list[WindowInfo]:
        wm = self._wm()
        try:
            raw_windows = wm.getClientList() or []
        except Exception:
            return []
        out: list[WindowInfo] = []
        for raw in raw_windows:
            info = self._info_for(raw)
            if info is not None:
                out.append(info)
        return out

    def find_by_title(self, title: str) -> WindowInfo | None:
        needle = title.lower()
        for w in self.all_windows():
            if needle in w.title.lower():
                return w
        return None

    # ---- Helpers -------------------------------------------------
    def _info_for(self, raw) -> WindowInfo | None:  # noqa: ANN001 - Xlib Window
        wm = self._wm()
        try:
            title = wm.getWmName(raw) or b""
            if isinstance(title, bytes):
                title = title.decode("utf-8", "replace")
            pid_prop = wm.getWmPid(raw)
            pid = int(pid_prop) if pid_prop else 0
            geom = raw.get_geometry()
        except Exception:
            return None
        try:
            abs_pos = raw.translate_coords(raw.query_tree().root, 0, 0)
            x = -int(abs_pos.x)
            y = -int(abs_pos.y)
        except Exception:
            x, y = int(getattr(geom, "x", 0)), int(getattr(geom, "y", 0))
        return WindowInfo(
            pid=pid,
            title=title,
            bounds=(x, y, int(geom.width), int(geom.height)),
            handle=int(raw.id),
        )

    def _window_by_id(self, wid: int | None):
        if wid is None:
            raise ValueError("window id required")
        wm = self._wm()
        return wm.display.create_resource_object("window", wid)
