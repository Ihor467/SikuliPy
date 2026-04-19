"""Status bar — port of ``SikuliIDEStatusBar.java``.

A pure data container: the Flet status bar reads the formatted strings
from :class:`StatusModel` and renders them. Keeping the formatting here
keeps the view layer thin.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from sikulipy import __version__


@dataclass
class StatusModel:
    """Holds the strings displayed in the IDE status bar."""

    file_path: Path | None = None
    dirty: bool = False
    cursor_line: int = 1
    cursor_column: int = 1
    message: str = "Ready"
    runner_name: str = "Python"
    _python_version: str = field(
        default_factory=lambda: f"{sys.version_info.major}.{sys.version_info.minor}"
    )

    # ---- Updates ---------------------------------------------------
    def set_cursor(self, line: int, column: int) -> None:
        self.cursor_line = max(1, line)
        self.cursor_column = max(1, column)

    def set_message(self, msg: str) -> None:
        self.message = msg

    def set_file(self, path: Path | None, dirty: bool = False) -> None:
        self.file_path = path
        self.dirty = dirty

    # ---- Rendering -------------------------------------------------
    def file_label(self) -> str:
        if self.file_path is None:
            return "<unsaved>"
        suffix = " *" if self.dirty else ""
        return f"{self.file_path.name}{suffix}"

    def cursor_label(self) -> str:
        return f"Ln {self.cursor_line}, Col {self.cursor_column}"

    def segments(self) -> list[str]:
        """Ordered segments suited for joining with a separator."""
        return [
            f"SikuliPy {__version__}",
            f"Python {self._python_version}",
            f"Runner: {self.runner_name}",
            self.file_label(),
            self.cursor_label(),
            self.message,
        ]

    def render(self, sep: str = " · ") -> str:
        return sep.join(self.segments())
