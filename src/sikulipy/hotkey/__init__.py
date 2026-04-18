"""Global hotkeys — port of ``org.sikuli.hotkey`` + ``com.tulskiy.keymaster``.

Backed by ``pynput.keyboard.GlobalHotKeys``. Phase 2.
"""

from sikulipy.hotkey.manager import HotkeyEvent, HotkeyManager, Keys, translate

__all__ = ["HotkeyEvent", "HotkeyManager", "Keys", "translate"]
