"""High-level :class:`App` facade — port of ``org.sikuli.script.App``.

Wraps a window-manager backend (see :mod:`sikulipy.natives._backend`)
so user scripts can write::

    from sikulipy.natives import App
    editor = App.open("code")
    editor.focus()
    region = editor.window()

Every call dispatches through :func:`get_backend()`, which tests can
override with :func:`set_backend()`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sikulipy.natives._backend import get_backend
from sikulipy.natives.types import WindowInfo

if TYPE_CHECKING:  # avoid the numpy/opencv import on module load
    from sikulipy.core.region import Region


@dataclass
class App:
    """Running application handle."""

    name: str
    pid: int | None = None
    _window_cache: list[WindowInfo] = field(default_factory=list, repr=False)

    # ---- Construction ---------------------------------------------
    @classmethod
    def open(cls, name: str, *, args: list[str] | None = None) -> "App":
        pid = get_backend().open(name, args=args)
        return cls(name=name, pid=pid)

    @classmethod
    def focused(cls) -> "App | None":
        info = get_backend().focused_window()
        if info is None:
            return None
        return cls(name=info.title, pid=info.pid)

    @classmethod
    def find(cls, title: str) -> "App | None":
        info = get_backend().find_by_title(title)
        if info is None:
            return None
        return cls(name=info.title, pid=info.pid)

    # ---- Process control ------------------------------------------
    def focus(self, *, title: str | None = None) -> bool:
        if self.pid is None:
            candidate = get_backend().find_by_title(title or self.name)
            if candidate is None:
                return False
            self.pid = candidate.pid
        return get_backend().focus(self.pid, title=title)

    def close(self) -> bool:
        if self.pid is None:
            return False
        ok = get_backend().close(self.pid)
        if ok:
            self._window_cache.clear()
        return ok

    def is_running(self) -> bool:
        if self.pid is None:
            return False
        return bool(get_backend().windows_for(self.pid))

    # ---- Windows --------------------------------------------------
    def windows(self) -> list[WindowInfo]:
        if self.pid is None:
            return []
        self._window_cache = list(get_backend().windows_for(self.pid))
        return list(self._window_cache)

    def window(self, n: int = 0) -> "Region | None":
        wins = self.windows()
        if not wins:
            return None
        if n < 0 or n >= len(wins):
            return None
        return _to_region(wins[n])

    @classmethod
    def all_windows(cls) -> list[WindowInfo]:
        return list(get_backend().all_windows())


def _to_region(info: WindowInfo) -> "Region":
    # Import lazily so ``App`` stays importable on the NumPy-less CPU.
    from sikulipy.core.region import Region

    return Region(x=info.x, y=info.y, w=info.w, h=info.h)
