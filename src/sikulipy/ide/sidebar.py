"""Right sidebar — pattern thumbnails for the current script.

Ports the data side of ``OculixSidebar.java`` / ``SidebarItem.java``.
The Flet view is responsible for rendering the thumbnails; this module
just exposes the *list* of patterns referenced by the editor buffer
(via :meth:`EditorDocument.pattern_absolute_paths`) plus any patterns
the user captured this session.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sikulipy.ide.editor import EditorDocument


@dataclass(frozen=True)
class SidebarItem:
    path: Path
    exists: bool

    @property
    def name(self) -> str:
        return self.path.name


@dataclass
class SidebarModel:
    """Combined view of editor-referenced + recently-captured patterns."""

    document: EditorDocument
    _captured: list[Path] = field(default_factory=list, repr=False)

    def add_captured(self, path: str | Path) -> None:
        p = Path(path).resolve()
        if p not in self._captured:
            self._captured.append(p)

    def captured(self) -> list[Path]:
        return list(self._captured)

    def items(self) -> list[SidebarItem]:
        seen: dict[Path, SidebarItem] = {}
        for p in self.document.pattern_absolute_paths():
            seen[p] = SidebarItem(path=p, exists=p.exists())
        for p in self._captured:
            seen.setdefault(p, SidebarItem(path=p, exists=p.exists()))
        return list(seen.values())

    def clear(self) -> None:
        self._captured.clear()
