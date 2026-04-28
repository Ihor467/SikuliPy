"""Phase 9 step 2 — surface-aware code generation.

Same RecorderAction must emit the desktop verb (``Screen().click(...)``-style
via the Sikuli star-import) on a desktop surface and the session-bound
``screen.method(...)`` form on an Android surface. Surface-only actions
must reject mismatched surfaces at codegen time.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sikulipy.ide.recorder import (
    PythonGenerator,
    RecorderAction,
    RecorderSession,
    _FakeSurface,
)
from sikulipy.ide.recorder.codegen import GenInput


# ---------------------------------------------------------------------------
# Same action on desktop vs android
# ---------------------------------------------------------------------------


def test_click_emits_wait_chain_on_desktop():
    gen = PythonGenerator()
    code = gen.generate(
        RecorderAction.CLICK,
        GenInput(pattern="btn.png", surface="desktop"),
    )
    assert code == 'wait(Pattern("btn.png"), 10).click()'


def test_click_emits_screen_call_on_android():
    gen = PythonGenerator()
    code = gen.generate(
        RecorderAction.CLICK,
        GenInput(pattern="btn.png", surface="android"),
    )
    assert code == 'screen.click(Pattern("btn.png"))'


def test_double_click_on_android():
    gen = PythonGenerator()
    code = gen.generate(
        RecorderAction.DBLCLICK,
        GenInput(pattern="btn.png", surface="android"),
    )
    assert code == 'screen.double_click(Pattern("btn.png"))'


def test_wait_and_wait_vanish_on_android_pass_timeout():
    gen = PythonGenerator()
    a = gen.generate(
        RecorderAction.WAIT,
        GenInput(pattern="btn.png", timeout=5, surface="android"),
    )
    b = gen.generate(
        RecorderAction.WAIT_VANISH,
        GenInput(pattern="btn.png", timeout=2.5, surface="android"),
    )
    assert a == 'screen.wait(Pattern("btn.png"), 5)'
    assert b == 'screen.wait_vanish(Pattern("btn.png"), 2.5)'


def test_drag_drop_and_swipe_on_android():
    gen = PythonGenerator()
    drag = gen.generate(
        RecorderAction.DRAG_DROP,
        GenInput(pattern="a.png", pattern2="b.png", surface="android"),
    )
    swipe = gen.generate(
        RecorderAction.SWIPE,
        GenInput(pattern="a.png", pattern2="b.png", surface="android"),
    )
    assert drag == 'screen.drag_drop(Pattern("a.png"), Pattern("b.png"))'
    assert swipe == 'screen.swipe(Pattern("a.png"), Pattern("b.png"))'


def test_type_routes_to_screen_on_android():
    gen = PythonGenerator()
    code = gen.generate(
        RecorderAction.TYPE,
        GenInput(payload="hello", surface="android"),
    )
    assert code == 'screen.type("hello")'


def test_pause_uses_sleep_on_android():
    gen = PythonGenerator()
    code = gen.generate(
        RecorderAction.PAUSE,
        GenInput(payload="2", surface="android"),
    )
    assert code == "sleep(2)"


# ---------------------------------------------------------------------------
# Android KEY_COMBO drops modifiers
# ---------------------------------------------------------------------------


def test_key_combo_on_android_keeps_only_final_key():
    gen = PythonGenerator()
    code = gen.generate(
        RecorderAction.KEY_COMBO,
        GenInput(payload="CTRL+SHIFT+A", surface="android"),
    )
    assert code == 'screen.device.key_event("KEYCODE_A")'


def test_key_combo_on_android_with_bare_key():
    gen = PythonGenerator()
    code = gen.generate(
        RecorderAction.KEY_COMBO,
        GenInput(payload="enter", surface="android"),
    )
    assert code == 'screen.device.key_event("KEYCODE_ENTER")'


# ---------------------------------------------------------------------------
# Hardware keys (android-only)
# ---------------------------------------------------------------------------


def test_hardware_keys_emit_key_event():
    gen = PythonGenerator()
    back = gen.generate(RecorderAction.BACK, GenInput(surface="android"))
    home = gen.generate(RecorderAction.HOME, GenInput(surface="android"))
    recents = gen.generate(RecorderAction.RECENTS, GenInput(surface="android"))
    assert back == 'screen.device.key_event("KEYCODE_BACK")'
    assert home == 'screen.device.key_event("KEYCODE_HOME")'
    assert recents == 'screen.device.key_event("KEYCODE_APP_SWITCH")'


# ---------------------------------------------------------------------------
# Text-find actions (android variant)
# ---------------------------------------------------------------------------


def test_text_actions_route_to_screen_on_android():
    gen = PythonGenerator()
    click = gen.generate(
        RecorderAction.TEXT_CLICK, GenInput(payload="OK", surface="android")
    )
    wait = gen.generate(
        RecorderAction.TEXT_WAIT,
        GenInput(payload="Loading", timeout=3, surface="android"),
    )
    exists = gen.generate(
        RecorderAction.TEXT_EXISTS, GenInput(payload="Done", surface="android")
    )
    assert click == 'screen.click(screen.find_text("OK"))'
    assert wait == 'screen.wait_text("Loading", 3)'
    assert exists == 'screen.has_text("Done")'


# ---------------------------------------------------------------------------
# Surface mismatches reject at codegen time
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "action",
    [
        RecorderAction.RCLICK,
        RecorderAction.WHEEL,
        RecorderAction.LAUNCH_APP,
        RecorderAction.CLOSE_APP,
    ],
)
def test_desktop_only_actions_rejected_on_android(action):
    gen = PythonGenerator()
    with pytest.raises(ValueError, match="not available on the android"):
        gen.generate(action, GenInput(payload="x", surface="android"))


@pytest.mark.parametrize(
    "action",
    [RecorderAction.BACK, RecorderAction.HOME, RecorderAction.RECENTS],
)
def test_android_only_actions_rejected_on_desktop(action):
    gen = PythonGenerator()
    with pytest.raises(ValueError, match="not available on the desktop"):
        gen.generate(action, GenInput(surface="desktop"))


# ---------------------------------------------------------------------------
# Session wires the active surface into GenInput
# ---------------------------------------------------------------------------


def test_session_records_against_active_surface(tmp_path: Path):
    sess = RecorderSession()
    sess.set_surface(_FakeSurface(name="android"))
    pat = tmp_path / "btn.png"
    pat.write_bytes(b"\x89PNG\r\n")
    line = sess.record_pattern(RecorderAction.CLICK, pat)
    assert line.code == 'screen.click(Pattern("btn.png"))'


def test_session_payload_uses_active_surface():
    sess = RecorderSession()
    sess.set_surface(_FakeSurface(name="android"))
    line = sess.record_payload(RecorderAction.TYPE, "hi")
    assert line.code == 'screen.type("hi")'


def test_session_two_pattern_uses_active_surface(tmp_path: Path):
    sess = RecorderSession()
    sess.set_surface(_FakeSurface(name="android"))
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    a.write_bytes(b"\x89PNG\r\n")
    b.write_bytes(b"\x89PNG\r\n")
    line = sess.record_two_patterns(RecorderAction.SWIPE, a, b)
    assert line.code == 'screen.swipe(Pattern("a.png"), Pattern("b.png"))'


def test_session_desktop_default_keeps_existing_codegen(tmp_path: Path):
    """Smoke test — desktop session still emits ``wait(...).click()``."""
    sess = RecorderSession()
    pat = tmp_path / "btn.png"
    pat.write_bytes(b"\x89PNG\r\n")
    line = sess.record_pattern(RecorderAction.CLICK, pat)
    assert line.code == 'wait(Pattern("btn.png"), 10).click()'


# ---------------------------------------------------------------------------
# applies_on metadata on RecorderAction
# ---------------------------------------------------------------------------


def test_applies_on_desktop_excludes_android_only():
    assert not RecorderAction.BACK.applies_on("desktop")
    assert not RecorderAction.HOME.applies_on("desktop")
    assert not RecorderAction.RECENTS.applies_on("desktop")


def test_applies_on_android_excludes_desktop_only():
    assert not RecorderAction.RCLICK.applies_on("android")
    assert not RecorderAction.WHEEL.applies_on("android")
    assert not RecorderAction.LAUNCH_APP.applies_on("android")
    assert not RecorderAction.CLOSE_APP.applies_on("android")


def test_applies_on_shared_actions_run_anywhere():
    for a in (
        RecorderAction.CLICK,
        RecorderAction.TYPE,
        RecorderAction.PAUSE,
        RecorderAction.WAIT,
        RecorderAction.DRAG_DROP,
        RecorderAction.TEXT_CLICK,
    ):
        assert a.applies_on("desktop")
        assert a.applies_on("android")
