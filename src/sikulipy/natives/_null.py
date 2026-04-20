"""Null window-manager backend — used on unsupported hosts.

Queries return empty results; mutating calls raise
:class:`NotSupportedError` so the caller can distinguish "nothing
running" from "this host can't manage windows at all". Importing
:mod:`sikulipy.natives` on a headless CI box therefore still works —
only the mutating operations (``open``/``close``/``focus``) are gated.
"""

from __future__ import annotations

import subprocess

from sikulipy.natives.types import NotSupportedError, WindowInfo


class _NullBackend:
    name = "null"

    def open(self, name: str, *, args: list[str] | None = None) -> int:
        # ``App.open`` is sometimes legitimately useful on a headless
        # host (running a CLI via Region.type; process management
        # without focus control). We therefore do try to launch the
        # executable, but return -1 for "no window" rather than a PID
        # if that fails.
        try:
            argv = [name, *(args or [])]
            proc = subprocess.Popen(  # noqa: S603 - user-supplied argv by design
                argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return int(proc.pid)
        except Exception as exc:
            raise NotSupportedError(
                f"null backend cannot launch {name!r}: {exc}"
            ) from exc

    def close(self, pid: int) -> bool:
        raise NotSupportedError("window close requires a platform backend")

    def focus(self, pid: int, *, title: str | None = None) -> bool:
        raise NotSupportedError("window focus requires a platform backend")

    def focused_window(self) -> WindowInfo | None:
        return None

    def windows_for(self, pid: int) -> list[WindowInfo]:
        return []

    def all_windows(self) -> list[WindowInfo]:
        return []

    def find_by_title(self, title: str) -> WindowInfo | None:
        return None
