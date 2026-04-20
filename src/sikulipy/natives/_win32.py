"""Windows window-manager backend.

Lazy-imports ``pywin32`` so ``sikulipy.natives`` remains importable on
hosts without the package (the installer-level ``app`` extra pulls it in
only on Windows).
"""

from __future__ import annotations

import ctypes
import subprocess
from typing import TYPE_CHECKING

from sikulipy.natives.types import NotSupportedError, WindowInfo

if TYPE_CHECKING:  # pragma: no cover - only evaluated by type checkers
    import win32gui  # noqa: F401
    import win32process  # noqa: F401


class _Win32Backend:
    name = "win32"

    def __init__(self) -> None:
        try:
            import win32con  # noqa: F401
            import win32gui  # noqa: F401
            import win32process  # noqa: F401
        except ImportError as exc:  # pragma: no cover - only on hosts without pywin32
            raise NotSupportedError(
                "_Win32Backend requires pywin32; install sikulipy[app]"
            ) from exc

    # ---- Launch / close -------------------------------------------
    def open(self, name: str, *, args: list[str] | None = None) -> int:
        argv = [name, *(args or [])]
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL)  # noqa: S603
        return int(proc.pid)

    def close(self, pid: int) -> bool:
        import win32api
        import win32con

        handle = win32api.OpenProcess(win32con.PROCESS_TERMINATE, False, pid)
        if not handle:
            return False
        try:
            win32api.TerminateProcess(handle, 0)
        finally:
            win32api.CloseHandle(handle)
        return True

    # ---- Focus ----------------------------------------------------
    def focus(self, pid: int, *, title: str | None = None) -> bool:
        import win32gui

        target_hwnd = None
        for info in self.windows_for(pid):
            if title is None or title.lower() in info.title.lower():
                target_hwnd = info.handle
                break
        if target_hwnd is None and title is not None:
            target = self.find_by_title(title)
            if target is not None:
                target_hwnd = target.handle
        if target_hwnd is None:
            return False
        try:
            win32gui.ShowWindow(target_hwnd, 9)  # SW_RESTORE
            win32gui.SetForegroundWindow(target_hwnd)
        except Exception:
            return False
        return True

    # ---- Enumeration ---------------------------------------------
    def focused_window(self) -> WindowInfo | None:
        import win32gui

        hwnd = win32gui.GetForegroundWindow()
        return self._info_for(hwnd)

    def windows_for(self, pid: int) -> list[WindowInfo]:
        return [w for w in self.all_windows() if w.pid == pid]

    def all_windows(self) -> list[WindowInfo]:
        import win32gui

        results: list[WindowInfo] = []

        def _cb(hwnd: int, _) -> bool:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            info = self._info_for(hwnd)
            if info is not None and info.title:
                results.append(info)
            return True

        win32gui.EnumWindows(_cb, None)
        return results

    def find_by_title(self, title: str) -> WindowInfo | None:
        needle = title.lower()
        for w in self.all_windows():
            if needle in w.title.lower():
                return w
        return None

    # ---- Helpers -------------------------------------------------
    def _info_for(self, hwnd: int) -> WindowInfo | None:
        if not hwnd:
            return None
        import win32gui
        import win32process

        try:
            title = win32gui.GetWindowText(hwnd)
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
        except Exception:
            return None
        return WindowInfo(
            pid=int(pid),
            title=title,
            bounds=(left, top, right - left, bottom - top),
            handle=int(hwnd),
        )
