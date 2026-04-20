"""Window-manager backend Protocol + singleton hook.

Same shape as the other backend Protocols in this project
(:mod:`sikulipy.core._input_backend`, :mod:`sikulipy.vnc._backend`,
:mod:`sikulipy.android._backend`, :mod:`sikulipy.runners._subprocess`):
a Protocol with the operations, a lazy default resolved at first call,
and an override setter for tests.

The default backend picks itself based on ``sys.platform``; on a
headless CI box with neither a display nor a platform SDK installed
we fall back to :class:`_NullBackend` which degrades cleanly.
"""

from __future__ import annotations

import os
import sys
from typing import Protocol

from sikulipy.natives.types import WindowInfo


class WindowManagerBackend(Protocol):
    """Operations every window-manager backend has to provide."""

    def open(self, name: str, *, args: list[str] | None = None) -> int: ...
    def close(self, pid: int) -> bool: ...
    def focus(self, pid: int, *, title: str | None = None) -> bool: ...
    def focused_window(self) -> WindowInfo | None: ...
    def windows_for(self, pid: int) -> list[WindowInfo]: ...
    def all_windows(self) -> list[WindowInfo]: ...
    def find_by_title(self, title: str) -> WindowInfo | None: ...


# ---------------------------------------------------------------------------
# Singleton hook
# ---------------------------------------------------------------------------


_backend: WindowManagerBackend | None = None


def get_backend() -> WindowManagerBackend:
    global _backend
    if _backend is None:
        _backend = _resolve_default()
    return _backend


def set_backend(backend: WindowManagerBackend | None) -> None:
    """Install a custom backend (or ``None`` to reset to the default)."""
    global _backend
    _backend = backend


def _resolve_default() -> WindowManagerBackend:
    """Pick the best backend for this host, falling back to null."""
    plat = sys.platform
    try:
        if plat == "win32":
            from sikulipy.natives._win32 import _Win32Backend

            return _Win32Backend()
        if plat == "darwin":
            from sikulipy.natives._macos import _MacOSBackend

            return _MacOSBackend()
        if plat.startswith("linux") and os.environ.get("DISPLAY"):
            from sikulipy.natives._linux import _LinuxBackend

            return _LinuxBackend()
    except Exception:
        # The platform backend could not initialise (missing pywin32,
        # Xlib, pyobjc, ...). Fall through to the null backend rather
        # than raising at import time.
        pass
    from sikulipy.natives._null import _NullBackend

    return _NullBackend()
