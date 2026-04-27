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

def _resolve_bundle(path: Path) -> Path:
    """Map a ``foo.sikuli`` folder to its inner ``foo.py`` script.

    SikuliX stores each script as a bundle directory (``foo.sikuli``)
    holding a same-stem ``.py`` file plus its pattern images. The IDE
    treats the bundle as a single openable unit; everything else
    (non-bundle paths, plain files) passes through unchanged.
    """
    if path.is_dir() and path.suffix.lower() == ".sikuli":
        candidate = path / f"{path.stem}.py"
        if candidate.is_file():
            return candidate
        for child in sorted(path.iterdir()):
            if child.is_file() and child.suffix.lower() == ".py":
                return child
    return path


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
        p = _resolve_bundle(Path(path))
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

    def indent_selection(
        self, start: int, end: int, indent: str = "    "
    ) -> tuple[int, int]:
        """Prepend ``indent`` to every line touched by ``[start, end)``.

        Returns the adjusted ``(start, end)`` so the caller can restore
        the selection. When ``start == end`` (no selection) only the
        single line containing the caret is indented and the caret moves
        right by ``len(indent)``.
        """
        if start > end:
            start, end = end, start
        line_start = self.text.rfind("\n", 0, start) + 1
        line_end = end
        if line_end > line_start and self.text[line_end - 1 : line_end] == "\n":
            # Selection ends at a newline boundary — don't indent the
            # following empty line the user didn't actually select.
            line_end -= 1
        block = self.text[line_start:line_end]
        if not block and start == end:
            block = ""  # caret on empty line: still inserts indent
        new_block = indent + block.replace("\n", "\n" + indent)
        self._snapshot()
        self.text = self.text[:line_start] + new_block + self.text[line_end:]
        self.dirty = True
        added_first = len(indent)
        added_total = len(new_block) - len(block)
        new_start = start + added_first
        new_end = end + added_total
        self.cursor = new_end
        return new_start, new_end

    def dedent_selection(
        self, start: int, end: int, indent: str = "    "
    ) -> tuple[int, int]:
        """Remove up to one ``indent`` worth of leading whitespace per line.

        Mirrors :meth:`indent_selection` but pops at most ``len(indent)``
        leading spaces (or one tab) from each touched line. Lines that
        don't start with whitespace are left alone. Returns the adjusted
        ``(start, end)``.
        """
        if start > end:
            start, end = end, start
        line_start = self.text.rfind("\n", 0, start) + 1
        line_end = end
        if line_end > line_start and self.text[line_end - 1 : line_end] == "\n":
            line_end -= 1
        block = self.text[line_start:line_end]
        new_lines: list[str] = []
        first_strip = 0
        total_strip = 0
        width = len(indent)
        for i, line in enumerate(block.split("\n")):
            if line.startswith("\t"):
                stripped = line[1:]
                removed = 1
            else:
                # Strip up to ``width`` leading spaces — fewer if the
                # line is only partially indented.
                j = 0
                while j < width and j < len(line) and line[j] == " ":
                    j += 1
                stripped = line[j:]
                removed = j
            if i == 0:
                first_strip = removed
            total_strip += removed
            new_lines.append(stripped)
        new_block = "\n".join(new_lines)
        if new_block == block:
            return start, end
        self._snapshot()
        self.text = self.text[:line_start] + new_block + self.text[line_end:]
        self.dirty = True
        new_start = max(line_start, start - first_strip)
        new_end = end - total_strip
        self.cursor = new_end
        return new_start, new_end

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

    def pattern_at_offset(self, offset: int) -> Path | None:
        """Return the absolute path of the image literal under ``offset``.

        Looks for any string literal ending in an image extension whose
        span contains the caret. Returns the resolved absolute path
        (against the document's folder) or ``None`` if the caret isn't
        on an image reference.
        """
        if not 0 <= offset <= len(self.text):
            return None
        base = self.path.parent if self.path is not None else Path.cwd()
        for m in _IMAGE_LITERAL_RE.finditer(self.text):
            if m.start() <= offset <= m.end():
                p = Path(m.group("path"))
                if not p.is_absolute():
                    p = base / p
                return p
        return None

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
