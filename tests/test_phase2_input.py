"""Phase 2 tests — Mouse, Keyboard, Region actions, Hotkey translation.

Backends are swapped with ``FakeMouse`` / ``FakeKeyboard`` recorders so the
tests exercise dispatch logic without touching real input devices.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from sikulipy.core import _input_backend as backend_mod
from sikulipy.core.keyboard import Key, KeyModifier
from sikulipy.core.location import Location
from sikulipy.core.match import Match
from sikulipy.core.mouse import Mouse
from sikulipy.core.region import Region
from sikulipy.hotkey.manager import translate


# -----------------------------------------------------------------------------
# Fake backends
# -----------------------------------------------------------------------------


@dataclass
class FakeMouse:
    pos: tuple[int, int] = (0, 0)
    calls: list[tuple] = field(default_factory=list)

    def position(self) -> tuple[int, int]:
        return self.pos

    def move(self, x: int, y: int) -> None:
        self.pos = (x, y)
        self.calls.append(("move", x, y))

    def press(self, button: str) -> None:
        self.calls.append(("press", button))

    def release(self, button: str) -> None:
        self.calls.append(("release", button))

    def click(self, button: str, count: int = 1) -> None:
        self.calls.append(("click", button, count))

    def scroll(self, dx: int, dy: int) -> None:
        self.calls.append(("scroll", dx, dy))


@dataclass
class FakeKeyboard:
    calls: list[tuple] = field(default_factory=list)

    def press(self, key: str) -> None:
        self.calls.append(("press", key))

    def release(self, key: str) -> None:
        self.calls.append(("release", key))

    def type(self, text: str) -> None:
        self.calls.append(("type", text))


@pytest.fixture
def fake_mouse():
    m = FakeMouse()
    backend_mod.set_mouse(m)
    yield m
    backend_mod.set_mouse(None)


@pytest.fixture
def fake_keyboard():
    k = FakeKeyboard()
    backend_mod.set_keyboard(k)
    yield k
    backend_mod.set_keyboard(None)


# -----------------------------------------------------------------------------
# Mouse
# -----------------------------------------------------------------------------


def test_mouse_click_moves_then_clicks(fake_mouse):
    Mouse.click(Location(120, 240))
    assert ("move", 120, 240) in fake_mouse.calls
    assert ("click", "left", 1) in fake_mouse.calls


def test_mouse_double_click(fake_mouse):
    Mouse.double_click(Location(5, 7))
    assert ("click", "left", 2) in fake_mouse.calls


def test_mouse_right_click(fake_mouse):
    Mouse.right_click(Location(1, 2))
    assert ("click", "right", 1) in fake_mouse.calls


def test_mouse_drag_drop_press_and_release(fake_mouse):
    Mouse.drag_drop(Location(0, 0), Location(100, 100))
    kinds = [c[0] for c in fake_mouse.calls]
    # move -> press -> move -> release
    assert kinds == ["move", "press", "move", "release"]
    assert fake_mouse.calls[2] == ("move", 100, 100)


def test_mouse_wheel(fake_mouse):
    Mouse.wheel(Mouse.WHEEL_DOWN, steps=3)
    assert fake_mouse.calls == [("scroll", 0, -3)]


# -----------------------------------------------------------------------------
# Keyboard
# -----------------------------------------------------------------------------


def test_key_type_plain_text_uses_type(fake_keyboard):
    Key.type("hello")
    assert fake_keyboard.calls == [("type", "hello")]


def test_key_type_special_keys_press_release(fake_keyboard):
    Key.type("hi" + Key.ENTER)
    # Plain "hi" typed in one run; ENTER press+release.
    assert ("type", "hi") in fake_keyboard.calls
    assert ("press", Key.ENTER) in fake_keyboard.calls
    assert ("release", Key.ENTER) in fake_keyboard.calls


def test_key_type_with_modifiers_wraps_text(fake_keyboard):
    Key.type("a", modifiers=KeyModifier.CTRL | KeyModifier.SHIFT)
    # Modifiers go down before, come up after, in reverse order.
    assert fake_keyboard.calls[0] == ("press", Key.SHIFT)
    assert fake_keyboard.calls[1] == ("press", Key.CTRL)
    assert ("type", "a") in fake_keyboard.calls
    # Last two calls are the releases in reverse.
    assert fake_keyboard.calls[-2:] == [("release", Key.CTRL), ("release", Key.SHIFT)]


def test_key_hotkey_presses_and_releases_in_reverse(fake_keyboard):
    Key.hotkey(Key.CTRL, "s")
    assert fake_keyboard.calls == [
        ("press", Key.CTRL),
        ("press", "s"),
        ("release", "s"),
        ("release", Key.CTRL),
    ]


# -----------------------------------------------------------------------------
# Region actions
# -----------------------------------------------------------------------------


def test_region_click_no_target_clicks_centre(fake_mouse):
    r = Region(100, 200, 40, 20)
    r.click()
    # centre is (120, 210)
    assert ("move", 120, 210) in fake_mouse.calls


def test_region_click_location(fake_mouse):
    r = Region(0, 0, 10, 10)
    r.click(Location(77, 88))
    assert ("move", 77, 88) in fake_mouse.calls


def test_region_type_dispatches_to_keyboard(fake_keyboard):
    Region(0, 0, 10, 10).type("abc")
    assert fake_keyboard.calls == [("type", "abc")]


def test_region_click_pattern_finds_and_offsets(monkeypatch, fake_mouse):
    """Pattern target: find() is consulted, target_offset is applied, wait_after respected."""
    from sikulipy.core.pattern import Pattern

    sentinel = Match(x=500, y=600, w=40, h=20, score=0.99)

    r = Region(0, 0, 10, 10)
    captured: dict = {}

    def fake_find(self, target):  # noqa: ARG001
        captured["called"] = True
        return sentinel

    monkeypatch.setattr(Region, "find", fake_find)

    r.click(Pattern(image="x.png").targetOffset(3, 4))
    # centre of sentinel is (520, 610); offset applied -> (523, 614)
    assert captured["called"] is True
    assert ("move", 523, 614) in fake_mouse.calls


def test_region_drag_drop_between_locations(fake_mouse):
    r = Region(0, 0, 1000, 1000)
    r.drag_drop(Location(10, 20), Location(100, 200))
    kinds = [c[0] for c in fake_mouse.calls]
    assert kinds == ["move", "press", "move", "release"]


# -----------------------------------------------------------------------------
# Hotkey translation
# -----------------------------------------------------------------------------


def test_translate_simple_letter():
    assert translate("a", KeyModifier.CTRL) == "<ctrl>+a"


def test_translate_multi_modifier_order():
    combo = translate("s", KeyModifier.CTRL | KeyModifier.SHIFT | KeyModifier.ALT)
    assert combo == "<ctrl>+<alt>+<shift>+s"


def test_translate_special_key_constant():
    assert translate(Key.F5, 0) == "<f5>"
    assert translate(Key.ENTER, KeyModifier.CTRL) == "<ctrl>+<enter>"


def test_translate_pre_formatted_token_passthrough():
    assert translate("<f12>", KeyModifier.ALT) == "<alt>+<f12>"
