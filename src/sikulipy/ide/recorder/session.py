"""High-level recorder façade — owns the temp dir, preview list, codegen.

The Flet dialog drives this with three calls:

* :meth:`record_pattern` — user picked an action that needs an image; we
  already have the saved PNG from the overlay flow.
* :meth:`record_payload` — user picked an action with text/key/seconds.
* :meth:`finalize` — user clicked Insert & Close; copy the saved PNGs
  next to the script and return the joined source.

Everything here is headless. The dialog only forwards events.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from sikulipy.ide.recorder.codegen import (
    CodeGenerator,
    GenInput,
    default_generator,
)
from sikulipy.ide.recorder.workflow import RecorderAction, RecorderWorkflow


@dataclass
class RecordedLine:
    action: RecorderAction
    code: str
    pattern_path: Path | None = None  # absolute path inside the temp dir
    pattern_path2: Path | None = None  # second pattern (drag_drop / swipe)


@dataclass
class RecorderSession:
    generator: CodeGenerator = field(default_factory=default_generator)
    workflow: RecorderWorkflow = field(default_factory=RecorderWorkflow)
    on_change: Callable[[], None] | None = None
    _lines: list[RecordedLine] = field(default_factory=list, repr=False)
    _tmpdir: Path | None = field(default=None, repr=False)

    # ---- Temp dir ---------------------------------------------------
    def temp_dir(self) -> Path:
        if self._tmpdir is None:
            self._tmpdir = Path(tempfile.mkdtemp(prefix="sikulipy_recorder_"))
        return self._tmpdir

    def discard(self) -> None:
        """Throw away preview + temp dir without inserting anything."""
        if self._tmpdir is not None and self._tmpdir.exists():
            shutil.rmtree(self._tmpdir, ignore_errors=True)
        self._tmpdir = None
        self._lines.clear()
        self.workflow.cancel()
        self._notify()

    # ---- Recording --------------------------------------------------
    def record_pattern(
        self,
        action: RecorderAction,
        pattern_path: Path,
        timeout: float = 10.0,
        similarity: float | None = None,
    ) -> RecordedLine:
        if not action.needs_pattern:
            raise ValueError(f"{action.value} does not take a pattern")
        gi = GenInput(
            pattern=pattern_path.name, timeout=timeout, similarity=similarity
        )
        code = self.generator.generate(action, gi)
        line = RecordedLine(action=action, code=code, pattern_path=pattern_path)
        self._lines.append(line)
        self._notify()
        return line

    def record_payload(
        self, action: RecorderAction, payload: str
    ) -> RecordedLine:
        if action.needs_pattern or action.needs_two_patterns:
            raise ValueError(f"{action.value} requires a pattern, not a payload")
        gi = GenInput(payload=payload)
        code = self.generator.generate(action, gi)
        line = RecordedLine(action=action, code=code)
        self._lines.append(line)
        self._notify()
        return line

    def record_two_patterns(
        self,
        action: RecorderAction,
        src_path: Path,
        dst_path: Path,
        timeout: float = 10.0,
        similarity: float | None = None,
    ) -> RecordedLine:
        if not action.needs_two_patterns:
            raise ValueError(f"{action.value} does not take two patterns")
        gi = GenInput(
            pattern=src_path.name,
            pattern2=dst_path.name,
            timeout=timeout,
            similarity=similarity,
        )
        code = self.generator.generate(action, gi)
        line = RecordedLine(
            action=action,
            code=code,
            pattern_path=src_path,
            pattern_path2=dst_path,
        )
        self._lines.append(line)
        self._notify()
        return line

    def remove_last(self) -> RecordedLine | None:
        if not self._lines:
            return None
        line = self._lines.pop()
        self._notify()
        return line

    def lines(self) -> list[RecordedLine]:
        return list(self._lines)

    def preview_text(self) -> str:
        return "\n".join(l.code for l in self._lines)

    # ---- Finalization -----------------------------------------------
    def finalize(self, target_dir: Path) -> tuple[str, list[Path]]:
        """Move recorded PNGs into ``target_dir`` and return joined code.

        Returns ``(code, moved_paths)``. Image basenames are preserved
        — collisions are resolved with a ``-1``/``-2`` suffix and the
        line referencing the colliding pattern is rewritten.
        """
        target_dir = target_dir.resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        moved: list[Path] = []
        rewritten_lines: list[str] = []
        for line in self._lines:
            if line.pattern_path is None:
                rewritten_lines.append(line.code)
                continue
            new_code, dest = _place_pattern(line.pattern_path, target_dir, line.code)
            moved.append(dest)
            if line.pattern_path2 is not None:
                new_code, dest2 = _place_pattern(line.pattern_path2, target_dir, new_code)
                moved.append(dest2)
            rewritten_lines.append(new_code)
        joined = "\n".join(rewritten_lines)
        if joined and not joined.endswith("\n"):
            joined += "\n"
        return joined, moved

    # ---- Internals --------------------------------------------------
    def _notify(self) -> None:
        if self.on_change is not None:
            self.on_change()


def _place_pattern(src: Path, target_dir: Path, code: str) -> tuple[str, Path]:
    """Ensure ``src`` ends up inside ``target_dir`` and rewrite ``code``.

    If ``src`` is already inside ``target_dir`` (e.g. saved straight to
    ``./assets`` by the capture overlay), don't copy — just point the
    code at the relative ``assets/<name>`` path. Otherwise copy to
    ``target_dir/<name>`` (with collision suffix) and rewrite the
    referenced pattern name.
    """
    src = src.resolve()
    target_dir = target_dir.resolve()
    try:
        rel = src.relative_to(target_dir)
        # Already inside — keep the file in place; rewrite to a path
        # that's relative to the target_dir so the script can find it.
        new_code = code.replace(f'"{src.name}"', f'"{rel.as_posix()}"', 1)
        return new_code, src
    except ValueError:
        pass
    dest = _unique_destination(target_dir / src.name)
    shutil.copy2(src, dest)
    new_code = code.replace(f'"{src.name}"', f'"{dest.name}"', 1)
    return new_code, dest


def _unique_destination(target: Path) -> Path:
    if not target.exists():
        return target
    stem, suffix = target.stem, target.suffix
    n = 1
    while True:
        candidate = target.with_name(f"{stem}-{n}{suffix}")
        if not candidate.exists():
            return candidate
        n += 1
