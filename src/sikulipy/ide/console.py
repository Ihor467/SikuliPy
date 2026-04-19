"""Console pane — captures stdout/stderr from running scripts.

Ports the *behaviour* of ``EditorConsolePane.java``: a ring buffer of
``(stream, text)`` chunks with stdout/stderr redirection. The Java pane
also rendered the buffer in Swing; here the buffer is decoupled from
rendering so the Flet view can subscribe via :meth:`ConsoleBuffer.subscribe`.

ANSI colour escapes are stripped on the way in — Sikuli scripts that use
``print('\\x1b[31m...')`` would otherwise leak escape codes into the Flet
text widget.
"""

from __future__ import annotations

import contextlib
import io
import re
import sys
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Literal

StreamName = Literal["stdout", "stderr"]

# ECMA-48 CSI / OSC sequences. Covers the common SGR ("\x1b[31m") plus
# the cursor-movement and OSC title escapes that some libraries emit.
_ANSI_RE = re.compile(
    r"""
    \x1b\[ [0-?]* [ -/]* [@-~]   # CSI
    | \x1b\] .*? (?:\x07|\x1b\\) # OSC
    | \x1b[@-Z\\-_]              # 2-byte escape
    """,
    re.VERBOSE,
)


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from ``text``."""
    return _ANSI_RE.sub("", text)


@dataclass
class ConsoleEntry:
    stream: StreamName
    text: str


@dataclass
class ConsoleBuffer:
    """Ring-buffered console output, optionally observable.

    ``max_entries`` caps the number of write chunks retained. Old entries
    are dropped silently — matching Swing's circular text-area behaviour
    in the Java IDE.
    """

    max_entries: int = 2000
    _entries: deque[ConsoleEntry] = field(default_factory=deque, repr=False)
    _listeners: list[Callable[[ConsoleEntry], None]] = field(
        default_factory=list, repr=False
    )

    def __post_init__(self) -> None:
        # Re-create the deque with the requested cap.
        self._entries = deque(self._entries, maxlen=self.max_entries)

    # ---- Writing ----------------------------------------------------
    def write(self, stream: StreamName, text: str) -> None:
        if not text:
            return
        cleaned = strip_ansi(text)
        if not cleaned:
            return
        entry = ConsoleEntry(stream=stream, text=cleaned)
        self._entries.append(entry)
        for listener in list(self._listeners):
            listener(entry)

    # ---- Reading ----------------------------------------------------
    def entries(self) -> list[ConsoleEntry]:
        return list(self._entries)

    def text(self) -> str:
        """Concatenated text, in arrival order."""
        return "".join(e.text for e in self._entries)

    def clear(self) -> None:
        self._entries.clear()

    # ---- Subscription -----------------------------------------------
    def subscribe(self, listener: Callable[[ConsoleEntry], None]) -> Callable[[], None]:
        """Register ``listener`` for new entries; returns an unsubscribe fn."""
        self._listeners.append(listener)

        def _unsub() -> None:
            with contextlib.suppress(ValueError):
                self._listeners.remove(listener)

        return _unsub


class _StreamProxy(io.TextIOBase):
    """File-like façade that forwards writes to a :class:`ConsoleBuffer`.

    Optionally also forwards to the original stream so users still see
    output in their terminal while the IDE captures it.
    """

    def __init__(
        self,
        buffer: ConsoleBuffer,
        stream: StreamName,
        tee: io.TextIOBase | None = None,
    ) -> None:
        super().__init__()
        self._buffer = buffer
        self._stream = stream
        self._tee = tee

    # io.TextIOBase contract
    def writable(self) -> bool:
        return True

    def write(self, s: str) -> int:
        if not isinstance(s, str):
            s = str(s)
        self._buffer.write(self._stream, s)
        if self._tee is not None:
            try:
                self._tee.write(s)
            except Exception:
                pass
        return len(s)

    def flush(self) -> None:
        if self._tee is not None:
            with contextlib.suppress(Exception):
                self._tee.flush()


@dataclass
class ConsoleRedirect:
    """Context manager swapping ``sys.stdout``/``sys.stderr``.

    ``tee=True`` keeps the original streams attached so output still
    surfaces in the launching terminal — useful when the IDE is invoked
    from a shell and the developer wants both views.
    """

    buffer: ConsoleBuffer
    tee: bool = False

    def __enter__(self) -> "ConsoleRedirect":
        self._saved_stdout = sys.stdout
        self._saved_stderr = sys.stderr
        sys.stdout = _StreamProxy(
            self.buffer, "stdout", tee=self._saved_stdout if self.tee else None
        )
        sys.stderr = _StreamProxy(
            self.buffer, "stderr", tee=self._saved_stderr if self.tee else None
        )
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        sys.stdout = self._saved_stdout
        sys.stderr = self._saved_stderr
