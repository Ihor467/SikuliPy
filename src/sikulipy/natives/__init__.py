"""Platform-specific native helpers.

Java sources: ``App.java``, ``WinUtil.dll/.cc``, ``MacUtil.m``,
``LinuxSupport.java``. Python replacement uses ``pywin32`` / ``pyobjc``
/ ``python-xlib`` behind a single :class:`WindowManagerBackend`
Protocol — install the extras with ``pip install sikulipy[app]``.

Hosts without the platform SDK (or without a display on Linux) fall
back to a :class:`_NullBackend` so importing this package never fails.
"""

from sikulipy.natives._backend import (
    WindowManagerBackend,
    get_backend,
    set_backend,
)
from sikulipy.natives.app import App
from sikulipy.natives.types import NotSupportedError, WindowInfo

__all__ = [
    "App",
    "NotSupportedError",
    "WindowInfo",
    "WindowManagerBackend",
    "get_backend",
    "set_backend",
]
