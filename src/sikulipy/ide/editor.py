"""Code editor — buffer + cursor + undo/redo model.

Ports the non-UI behaviour of ``EditorPane.java`` and its helpers:
dirty-tracking, undo/redo, pattern-reference scanning. The Flet widget
(``app.py``) binds its ``TextField`` to an :class:`EditorDocument` so
the same state powers both unit tests and the IDE.

Pattern-reference scanning deliberately stays regex-based. SikuliX's
Java version relied on a full tokenizer pass to render inline image
thumbnails; we only need to know *which* pattern paths appear in the
buffer so the sidebar can list them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_PATTERN_CALL_RE = re.compile(
    r"""Pattern\s*\(\s*               # Pattern(
        ['"](?P<path>[^'"]+)['"]      # "…"
    """,
    re.VERBOSE,
)
_IMAGE_LITERAL_RE = re.compile(
    r"""['"](?P<path>[^'"]+\.(?:png|jpg|jpeg|bmp|gif|tiff|webp))['"]""",
    re.IGNORECASE,
)


@dataclass
class _HistoryEntry:
    text: str
    cursor: int


@dataclass
class EditorDocument:
    """In-memory buffer backing a single editor tab.

    Attributes:
        text: the full buffer contents.
        path: backing file path, if any.
        cursor: zero-based character offset (caret position).
        dirty: True if ``text`` has diverged from the file on disk.
    """

    text: str = ""
    path: Path | None = None
    cursor: int = 0
    dirty: bool = False
    _undo: list[_HistoryEntry] = field(default_factory=list, repr=False)
    _redo: list[_HistoryEntry] = field(default_factory=list, repr=False)
    _history_limit: int = 100

    # ---- Loading / saving ------------------------------------------
    @classmethod
    def open(cls, path: str | Path) -> "EditorDocument":
        p = Path(path)
        text = p.read_text(encoding="utf-8") if p.exists() else ""
        return cls(text=text, path=p.resolve(), cursor=0, dirty=False)

    def save(self, path: str | Path | None = None) -> Path:
        target = Path(path).resolve() if path is not None else self.path
        if target is None:
            raise ValueError("EditorDocument.save() needs a path")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.text, encoding="utf-8")
        self.path = target
        self.dirty = False
        return target

    # ---- Mutation --------------------------------------------------
    def _snapshot(self) -> None:
        self._undo.append(_HistoryEntry(text=self.text, cursor=self.cursor))
        if len(self._undo) > self._history_limit:
            self._undo.pop(0)
        self._redo.clear()

    def set_text(self, new_text: str) -> None:
        if new_text == self.text:
            return
        self._snapshot()
        self.text = new_text
        self.cursor = min(self.cursor, len(new_text))
        self.dirty = True

    def insert(self, text: str, at: int | None = None) -> None:
        if not text:
            return
        self._snapshot()
        pos = self.cursor if at is None else max(0, min(at, len(self.text)))
        self.text = self.text[:pos] + text + self.text[pos:]
        self.cursor = pos + len(text)
        self.dirty = True

    def delete_range(self, start: int, end: int) -> None:
        start = max(0, min(start, len(self.text)))
        end = max(0, min(end, len(self.text)))
        if start == end:
            return
        if start > end:
            start, end = end, start
        self._snapshot()
        self.text = self.text[:start] + self.text[end:]
        self.cursor = start
        self.dirty = True

    # ---- Undo / redo -----------------------------------------------
    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(_HistoryEntry(text=self.text, cursor=self.cursor))
        entry = self._undo.pop()
        self.text = entry.text
        self.cursor = entry.cursor
        self.dirty = True
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(_HistoryEntry(text=self.text, cursor=self.cursor))
        entry = self._redo.pop()
        self.text = entry.text
        self.cursor = entry.cursor
        self.dirty = True
        return True

    # ---- Pattern-reference scanning ---------------------------------
    def pattern_references(self) -> list[str]:
        """Return the pattern image paths referenced by the buffer.

        Collects both ``Pattern("x.png")`` calls and any bare string
        literal ending in an image extension, de-duplicated, ordered by
        first appearance.
        """
        seen: dict[str, None] = {}
        for m in _PATTERN_CALL_RE.finditer(self.text):
            seen.setdefault(m.group("path"), None)
        for m in _IMAGE_LITERAL_RE.finditer(self.text):
            seen.setdefault(m.group("path"), None)
        return list(seen.keys())

    def pattern_absolute_paths(self) -> list[Path]:
        """Resolve :meth:`pattern_references` against the document's folder.

        Paths that don't exist on disk are returned as-is (caller decides
        what to do with a broken reference).
        """
        base = self.path.parent if self.path is not None else Path.cwd()
        out: list[Path] = []
        for ref in self.pattern_references():
            p = Path(ref)
            if not p.is_absolute():
                p = (base / p)
            out.append(p)
        return out
