"""Phase 10 step 2 — every instrumented method emits the right record.

We don't run a real display, real ADB, or pynput here. Each test
swaps in a fake for the relevant subsystem (mouse, ADB device, window
manager) and walks one decorated method through, asserting on the
``(category, verb)`` tuple plus a target-string sanity check. The
START-then-OK ordering is already covered by ``test_phase10_action_log``;
here we only care that the wiring landed on the right methods.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from sikulipy.core import _input_backend
from sikulipy.core.location import Location
from sikulipy.core.match import Match
from sikulipy.core.mouse import Mouse
from sikulipy.core.region import Region
from sikulipy.natives import _backend as _natives_backend
from sikulipy.natives.app import App
from sikulipy.natives.types import WindowInfo
from sikulipy.util.action_log import Phase, collect_records


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class _FakeMouse:
    calls: list[tuple] = field(default_factory=list)
    pos: tuple[int, int] = (0, 0)

    def position(self) -> tuple[int, int]:
        return self.pos

    def move(self, x: int, y: int) -> None:
        self.calls.append(("move", x, y))
        self.pos = (x, y)

    def press(self, button: str) -> None:
        self.calls.append(("press", button))

    def release(self, button: str) -> None:
        self.calls.append(("release", button))

    def click(self, button: str, count: int = 1) -> None:
        self.calls.append(("click", button, count))

    def scroll(self, dx: int, dy: int) -> None:
        self.calls.append(("scroll", dx, dy))


class _FakeRegion(Region):
    """Region whose find/capture is mocked so click() doesn't need cv2."""

    def _capture_bgr(self):
        return None

    def _find_once(self, target: Any):
        return Match(x=self.x + 5, y=self.y + 7, w=2, h=2, score=1.0)


@pytest.fixture
def fake_mouse():
    fake = _FakeMouse()
    _input_backend.set_mouse(fake)
    yield fake
    _input_backend.set_mouse(None)


# ---------------------------------------------------------------------------
# Region instrumentation
# ---------------------------------------------------------------------------


def _verbs(records, *, phase: Phase = Phase.START) -> list[tuple[str, str]]:
    return [(r.category, r.verb) for r in records if r.phase == phase]


def test_region_find_emits_region_find(fake_mouse):
    region = _FakeRegion(x=0, y=0, w=10, h=10)
    records, restore = collect_records()
    try:
        region.find("needle.png")
    finally:
        restore()
    assert ("region", "find") in _verbs(records)
    start = next(r for r in records if r.phase == Phase.START)
    assert start.target == "'needle.png'"
    assert start.surface == "desktop"


def test_region_click_emits_region_click_then_mouse_click(fake_mouse):
    region = _FakeRegion(x=0, y=0, w=10, h=10)
    records, restore = collect_records()
    try:
        region.click()
    finally:
        restore()
    starts = _verbs(records)
    # Region.click is the outermost; Mouse.move + Mouse.click nest inside.
    assert ("region", "click") in starts
    assert ("mouse", "click") in starts
    assert ("mouse", "move") in starts


@pytest.mark.parametrize(
    "method,args,expected",
    [
        ("exists", ("x.png", 0.0), ("region", "exists")),
        ("wait", ("x.png", 0.0), ("region", "wait")),
        ("wait_vanish", ("x.png", 0.0), ("region", "wait_vanish")),
        ("double_click", (), ("region", "double_click")),
        ("right_click", (), ("region", "right_click")),
        ("hover", (), ("region", "hover")),
        ("find_all", ("x.png",), ("region", "find_all")),
    ],
)
def test_region_methods_each_emit_their_verb(fake_mouse, method, args, expected):
    region = _FakeRegion(x=0, y=0, w=10, h=10)
    records, restore = collect_records()
    try:
        try:
            getattr(region, method)(*args)
        except Exception:
            # find_all hits the real Finder/_resolve_pattern path which
            # needs cv2; we only care that the decorator emitted FAIL.
            pass
    finally:
        restore()
    assert any(
        r.category == expected[0] and r.verb == expected[1] for r in records
    ), f"missing {expected} in {[(r.category, r.verb, r.phase.name) for r in records]}"


def test_region_drag_drop_target_shows_arrow(fake_mouse):
    region = _FakeRegion(x=0, y=0, w=10, h=10)
    records, restore = collect_records()
    try:
        region.drag_drop("a.png", "b.png")
    finally:
        restore()
    drag_starts = [
        r for r in records if r.category == "region" and r.verb == "drag_drop" and r.phase == Phase.START
    ]
    assert drag_starts
    assert "→" in drag_starts[0].target


def test_region_type_target_is_text(fake_mouse, monkeypatch):
    # Stub keyboard so .type() doesn't hit pynput.
    monkeypatch.setattr(
        "sikulipy.core.keyboard.Key.type",
        staticmethod(lambda text, modifiers=0: len(text)),
    )
    region = _FakeRegion(x=0, y=0, w=10, h=10)
    records, restore = collect_records()
    try:
        region.type("hi")
    finally:
        restore()
    start = next(r for r in records if r.category == "region" and r.verb == "type")
    assert start.target == "'hi'"


# ---------------------------------------------------------------------------
# Mouse instrumentation
# ---------------------------------------------------------------------------


def test_mouse_click_emits_mouse_click(fake_mouse):
    records, restore = collect_records()
    try:
        Mouse.click(Location(10, 20))
    finally:
        restore()
    assert ("mouse", "click") in _verbs(records)
    assert ("mouse", "move") in _verbs(records)


def test_mouse_drag_drop_emits_with_arrow(fake_mouse):
    records, restore = collect_records()
    try:
        Mouse.drag_drop(Location(1, 2), Location(3, 4))
    finally:
        restore()
    starts = [r for r in records if r.category == "mouse" and r.verb == "drag_drop"]
    assert starts
    assert "→" in starts[0].target


def test_mouse_wheel_records_direction_and_steps(fake_mouse):
    records, restore = collect_records()
    try:
        Mouse.wheel(Mouse.WHEEL_UP, steps=3)
    finally:
        restore()
    starts = [r for r in records if r.verb == "wheel" and r.phase == Phase.START]
    assert starts
    assert "direction=1" in starts[0].target
    assert "steps=3" in starts[0].target


# ---------------------------------------------------------------------------
# Android instrumentation
# ---------------------------------------------------------------------------


@dataclass
class _FakeAdbDevice:
    serial: str = "ADB-0001"
    shell_calls: list[str] = field(default_factory=list)

    def size(self) -> tuple[int, int]:
        return (1080, 1920)

    def tap(self, x: int, y: int) -> None:
        self.shell_calls.append(f"tap {x} {y}")

    def long_press(self, x: int, y: int, duration_ms: int = 1000) -> None:
        self.shell_calls.append(f"long_press {x} {y}")

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 400) -> None:
        self.shell_calls.append(f"swipe {x1} {y1} {x2} {y2}")

    def input_text(self, text: str) -> None:
        self.shell_calls.append(f"text {text}")

    def screencap(self):
        raise NotImplementedError


def _make_adb_screen() -> Any:
    from sikulipy.android.screen import ADBScreen

    return ADBScreen.__new__(ADBScreen).__class__(_FakeAdbDevice())


def test_android_click_emits_with_adb_surface():
    screen = _make_adb_screen()
    records, restore = collect_records()
    try:
        screen.click(Location(100, 200))
    finally:
        restore()
    starts = [r for r in records if r.category == "android" and r.verb == "click"]
    assert starts
    assert starts[0].surface == "adb:ADB-0001"


def test_android_swipe_drag_double_long_emit():
    screen = _make_adb_screen()
    records, restore = collect_records()
    try:
        screen.double_click(Location(1, 1))
        screen.right_click(Location(1, 1))
        screen.drag_drop(Location(1, 1), Location(2, 2))
        screen.swipe(Location(1, 1), Location(2, 2))
        screen.type("hello")
    finally:
        restore()
    seen = {(r.category, r.verb) for r in records if r.phase == Phase.START}
    for verb in ("double_click", "right_click", "drag_drop", "swipe", "type"):
        assert ("android", verb) in seen


# ---------------------------------------------------------------------------
# App instrumentation
# ---------------------------------------------------------------------------


@dataclass
class _FakeWMBackend:
    opened: list[str] = field(default_factory=list)
    closed: list[int] = field(default_factory=list)
    focused: list[int] = field(default_factory=list)

    def open(self, name: str, *, args: list[str] | None = None) -> int:
        self.opened.append(name)
        return 4242

    def close(self, pid: int) -> bool:
        self.closed.append(pid)
        return True

    def focus(self, pid: int, *, title: str | None = None) -> bool:
        self.focused.append(pid)
        return True

    def focused_window(self) -> WindowInfo | None:
        return None

    def windows_for(self, pid: int) -> list[WindowInfo]:
        return []

    def all_windows(self) -> list[WindowInfo]:
        return []

    def find_by_title(self, title: str) -> WindowInfo | None:
        return None


@pytest.fixture
def fake_wm():
    backend = _FakeWMBackend()
    _natives_backend.set_backend(backend)
    yield backend
    _natives_backend.set_backend(None)


def test_app_open_focus_close_emit(fake_wm):
    records, restore = collect_records()
    try:
        app = App.open("editor")
        app.focus()
        app.close()
    finally:
        restore()
    seen = {(r.category, r.verb) for r in records if r.phase == Phase.START}
    assert ("app", "open") in seen
    assert ("app", "focus") in seen
    assert ("app", "close") in seen
    open_start = next(r for r in records if r.verb == "open" and r.phase == Phase.START)
    assert open_start.target == "'editor'"
