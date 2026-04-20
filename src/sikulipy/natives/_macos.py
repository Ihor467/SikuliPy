"""macOS window-manager backend.

Uses ``Quartz`` / ``AppKit`` via ``pyobjc`` — lazy-imported so the
module is safe to reference on non-macOS hosts.
"""

from __future__ import annotations

import signal
import subprocess

from sikulipy.natives.types import NotSupportedError, WindowInfo


class _MacOSBackend:
    name = "darwin"

    def __init__(self) -> None:
        try:
            import Quartz  # noqa: F401
            from AppKit import NSWorkspace  # noqa: F401
        except ImportError as exc:  # pragma: no cover - macOS-only
            raise NotSupportedError(
                "_MacOSBackend requires pyobjc; install sikulipy[app]"
            ) from exc

    # ---- Launch / close ------------------------------------------
    def open(self, name: str, *, args: list[str] | None = None) -> int:
        # ``open -a`` is the canonical way to launch a macOS app by
        # name. For a plain executable path we fall back to Popen.
        if "/" in name or name.endswith(".app"):
            argv = [name, *(args or [])]
        else:
            argv = ["open", "-a", name]
            if args:
                argv += ["--args", *args]
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL)  # noqa: S603
        return int(proc.pid)

    def close(self, pid: int) -> bool:
        try:
            import os

            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return False
        return True

    # ---- Focus ---------------------------------------------------
    def focus(self, pid: int, *, title: str | None = None) -> bool:
        from AppKit import NSRunningApplication

        app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
        if app is None:
            return False
        # NSApplicationActivateIgnoringOtherApps = 1 << 1
        return bool(app.activateWithOptions_(1 << 1))

    # ---- Enumeration --------------------------------------------
    def focused_window(self) -> WindowInfo | None:
        from AppKit import NSWorkspace

        active = NSWorkspace.sharedWorkspace().frontmostApplication()
        if active is None:
            return None
        pid = int(active.processIdentifier())
        wins = self.windows_for(pid)
        return wins[0] if wins else None

    def windows_for(self, pid: int) -> list[WindowInfo]:
        return [w for w in self.all_windows() if w.pid == pid]

    def all_windows(self) -> list[WindowInfo]:
        import Quartz

        opts = (
            Quartz.kCGWindowListOptionOnScreenOnly
            | Quartz.kCGWindowListExcludeDesktopElements
        )
        raw = Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID) or []
        out: list[WindowInfo] = []
        for w in raw:
            title = str(w.get("kCGWindowName", "") or "")
            pid = int(w.get("kCGWindowOwnerPID", 0) or 0)
            bounds = w.get("kCGWindowBounds") or {}
            x = int(bounds.get("X", 0))
            y = int(bounds.get("Y", 0))
            width = int(bounds.get("Width", 0))
            height = int(bounds.get("Height", 0))
            out.append(
                WindowInfo(
                    pid=pid,
                    title=title,
                    bounds=(x, y, width, height),
                    handle=int(w.get("kCGWindowNumber", 0) or 0),
                )
            )
        return out

    def find_by_title(self, title: str) -> WindowInfo | None:
        needle = title.lower()
        for w in self.all_windows():
            if needle in w.title.lower():
                return w
        return None
