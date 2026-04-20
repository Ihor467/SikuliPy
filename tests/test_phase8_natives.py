"""Phase 8 tests — native window management.

All tests run against an injected :class:`RecordingBackend`; the real
Win32/macOS/Linux backends are exercised by their platform CI.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from sikulipy.natives import App, WindowInfo, set_backend
from sikulipy.natives._null import _NullBackend
from sikulipy.natives.types import NotSupportedError


# ---------------------------------------------------------------------------
# Recording fake backend
# ---------------------------------------------------------------------------


@dataclass
class RecordingBackend:
    opened: list[tuple[str, list[str] | None]] = field(default_factory=list)
    focused: list[tuple[int, str | None]] = field(default_factory=list)
    closed: list[int] = field(default_factory=list)
    windows: list[WindowInfo] = field(default_factory=list)
    next_pid: int = 1000

    def open(self, name, *, args=None):  # noqa: ANN001
        self.opened.append((name, args))
        pid = self.next_pid
        self.next_pid += 1
        self.windows.append(
            WindowInfo(pid=pid, title=name, bounds=(0, 0, 800, 600), handle=pid)
        )
        return pid

    def close(self, pid: int) -> bool:
        self.closed.append(pid)
        self.windows = [w for w in self.windows if w.pid != pid]
        return True

    def focus(self, pid, *, title=None):  # noqa: ANN001
        self.focused.append((pid, title))
        return any(w.pid == pid for w in self.windows)

    def focused_window(self):
        return self.windows[0] if self.windows else None

    def windows_for(self, pid: int):
        return [w for w in self.windows if w.pid == pid]

    def all_windows(self):
        return list(self.windows)

    def find_by_title(self, title: str):
        needle = title.lower()
        for w in self.windows:
            if needle in w.title.lower():
                return w
        return None


@pytest.fixture
def backend():
    b = RecordingBackend()
    set_backend(b)
    yield b
    set_backend(None)


# ---------------------------------------------------------------------------
# App API
# ---------------------------------------------------------------------------


def test_app_open_routes_to_backend(backend):
    app = App.open("code", args=["--new-window"])
    assert backend.opened == [("code", ["--new-window"])]
    assert app.pid == 1000
    assert app.name == "code"


def test_app_focus_dispatches_pid(backend):
    app = App.open("editor")
    assert app.focus()
    assert backend.focused == [(1000, None)]


def test_app_focus_by_title_resolves_pid(backend):
    backend.windows.append(
        WindowInfo(pid=42, title="Some Editor", bounds=(0, 0, 100, 100), handle=42)
    )
    app = App(name="Some Editor")
    assert app.focus(title="Some Editor") is True
    assert app.pid == 42


def test_app_close_clears_pid_windows(backend):
    app = App.open("browser")
    app.close()
    assert backend.closed == [1000]
    assert app.is_running() is False


def test_app_window_returns_region(backend):
    app = App.open("paint")
    # Region import pulls in numpy/cv2 which may be unavailable.
    try:
        region = app.window(0)
    except RuntimeError as exc:
        pytest.skip(f"Region unavailable: {exc}")
    assert region is not None
    assert (region.x, region.y, region.w, region.h) == (0, 0, 800, 600)


def test_app_all_windows_returns_snapshot(backend):
    App.open("a")
    App.open("b")
    names = [w.title for w in App.all_windows()]
    assert names == ["a", "b"]


def test_app_focused_builds_handle(backend):
    App.open("winmost")
    app = App.focused()
    assert app is not None
    assert app.name == "winmost"


def test_app_find_returns_none_when_absent(backend):
    assert App.find("nothing") is None


def test_app_find_matches_substring(backend):
    App.open("Spreadsheet 2024")
    app = App.find("SPREADSHEET")
    assert app is not None
    assert app.name == "Spreadsheet 2024"


# ---------------------------------------------------------------------------
# Null backend — must not raise on query, must raise on mutate
# ---------------------------------------------------------------------------


def test_null_backend_queries_return_empty():
    b = _NullBackend()
    assert b.all_windows() == []
    assert b.focused_window() is None
    assert b.find_by_title("x") is None
    assert b.windows_for(123) == []


def test_null_backend_close_raises():
    b = _NullBackend()
    with pytest.raises(NotSupportedError):
        b.close(1)


def test_null_backend_focus_raises():
    b = _NullBackend()
    with pytest.raises(NotSupportedError):
        b.focus(1)
