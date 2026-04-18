"""Platform-specific native helpers.

Java sources: WinUtil.dll/.cc, MacUtil.m, LinuxSupport.java.

Python will rely on:
* Windows  -> ``pywin32`` + ``ctypes``
* macOS    -> ``pyobjc`` + Quartz
* Linux    -> ``Xlib``/``python-xlib`` or ``ewmh`` for X11; plus ``pywayland``

Phase 8 — only as needed (most work is covered by pyautogui/mss/pynput).
"""
