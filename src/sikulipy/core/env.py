"""Port of ``org.sikuli.script.Env`` + ``SX`` + ``Sikulix`` — environment helpers.

Exposes platform detection, clipboard access, OS-level utilities. Phase 1-2.
"""

from __future__ import annotations

import platform
import sys


class Env:
    @staticmethod
    def get_os() -> str:
        return platform.system().lower()

    @staticmethod
    def is_windows() -> bool:
        return sys.platform.startswith("win")

    @staticmethod
    def is_macos() -> bool:
        return sys.platform == "darwin"

    @staticmethod
    def is_linux() -> bool:
        return sys.platform.startswith("linux")

    @staticmethod
    def get_clipboard() -> str:
        import pyperclip

        return pyperclip.paste()

    @staticmethod
    def set_clipboard(text: str) -> None:
        import pyperclip

        pyperclip.copy(text)
