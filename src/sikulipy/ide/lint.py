"""Headless Python linter for the editor pane.

Wraps :mod:`pyflakes` (a hard dep via the dev stack and shipped with most
Python distributions) so the IDE can show squiggle-free diagnostics
without spawning a subprocess on every keystroke. ``ast.parse`` runs
first so a true ``SyntaxError`` becomes a single, well-located
diagnostic instead of pyflakes' generic ``problem decoding source``.

The module is GUI-agnostic: it returns a list of :class:`Diagnostic`
records keyed by 1-based line numbers, leaving rendering to ``app.py``.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

try:  # pragma: no cover - import-time fallback
    from pyflakes.api import check as _pyflakes_check
    from pyflakes.reporter import Reporter as _PyflakesReporter
    _PYFLAKES_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PYFLAKES_AVAILABLE = False


@dataclass(frozen=True)
class Diagnostic:
    """A single linter finding.

    Attributes:
        line: 1-based line number.
        column: 1-based column (0 if pyflakes didn't report one).
        severity: ``"error"`` for syntax errors, ``"warning"`` otherwise.
        message: human-readable description.
    """

    line: int
    column: int
    severity: str
    message: str


class _ListReporter:
    """Pyflakes ``Reporter`` that captures messages into a list.

    Pyflakes' built-in :class:`pyflakes.reporter.Reporter` writes to file
    handles; we want structured records instead. Same protocol —
    ``unexpectedError``, ``syntaxError``, ``flake`` — but it appends to
    ``self.diagnostics`` so the caller doesn't have to re-parse output
    text.
    """

    def __init__(self) -> None:
        self.diagnostics: list[Diagnostic] = []

    def unexpectedError(self, _filename: str, msg: str) -> None:
        self.diagnostics.append(Diagnostic(1, 0, "error", msg))

    def syntaxError(
        self,
        _filename: str,
        msg: str,
        lineno: int,
        offset: int | None,
        _text: str,
    ) -> None:
        self.diagnostics.append(
            Diagnostic(max(1, lineno), max(0, offset or 0), "error", msg)
        )

    def flake(self, message) -> None:  # pyflakes.messages.Message
        self.diagnostics.append(
            Diagnostic(
                line=getattr(message, "lineno", 1),
                column=getattr(message, "col", 0) or 0,
                severity="warning",
                message=message.message % message.message_args,
            )
        )


def lint_text(text: str, filename: str = "<editor>") -> list[Diagnostic]:
    """Return diagnostics for ``text`` sorted by (line, column).

    A leading :func:`ast.parse` short-circuits on syntax errors so the
    user sees the offending line + offset directly. When the source
    parses cleanly we hand it to pyflakes for the usual undefined-name
    / unused-import / shadowing checks. If pyflakes isn't importable
    (frozen build, stripped venv) the function silently falls back to
    syntax-only checking — better degraded than crashing the IDE.
    """
    if not text.strip():
        return []

    try:
        ast.parse(text, filename=filename)
    except SyntaxError as exc:
        return [
            Diagnostic(
                line=exc.lineno or 1,
                column=(exc.offset or 0),
                severity="error",
                message=exc.msg or "syntax error",
            )
        ]

    if not _PYFLAKES_AVAILABLE:
        return []

    reporter = _ListReporter()
    # ``check`` returns the count of warnings; we only need the captured
    # records on the reporter.
    _pyflakes_check(text, filename, reporter)  # type: ignore[arg-type]
    return sorted(reporter.diagnostics, key=lambda d: (d.line, d.column))
