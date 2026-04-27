"""Phase 8 — recorder unit tests.

Headless coverage of the workflow state machine, code generators, and
RecorderSession integration. The Flet dialog is exercised via a smoke
import only, like the rest of the IDE.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sikulipy.ide.recorder import (
    PythonGenerator,
    RecorderAction,
    RecorderSession,
    RecorderState,
    RecorderWorkflow,
    default_generator,
)
from sikulipy.ide.recorder.codegen import GenInput


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------


def test_workflow_idle_to_capturing_for_image_actions():
    wf = RecorderWorkflow()
    seen: list[tuple[RecorderState, RecorderAction | None]] = []
    wf.subscribe(lambda s, a: seen.append((s, a)))

    wf.begin(RecorderAction.CLICK)
    assert wf.state is RecorderState.CAPTURING_REGION
    assert wf.pending is RecorderAction.CLICK

    wf.finish()
    assert wf.is_idle()
    assert wf.pending is None
    assert seen == [
        (RecorderState.CAPTURING_REGION, RecorderAction.CLICK),
        (RecorderState.IDLE, None),
    ]


def test_workflow_idle_to_user_input_for_payload_actions():
    wf = RecorderWorkflow()
    wf.begin(RecorderAction.TYPE)
    assert wf.state is RecorderState.WAITING_USER_INPUT


def test_workflow_rejects_overlapping_begin():
    wf = RecorderWorkflow()
    wf.begin(RecorderAction.CLICK)
    with pytest.raises(RuntimeError):
        wf.begin(RecorderAction.WAIT)


def test_workflow_unsubscribe_stops_notifications():
    wf = RecorderWorkflow()
    seen: list = []
    unsub = wf.subscribe(lambda s, a: seen.append(s))
    wf.begin(RecorderAction.PAUSE)
    unsub()
    wf.finish()
    assert seen == [RecorderState.WAITING_USER_INPUT]


# ---------------------------------------------------------------------------
# Code generation
# ---------------------------------------------------------------------------


def test_python_generator_image_actions():
    g = PythonGenerator()
    gi = GenInput(pattern="btn.png", timeout=10)
    assert g.generate(RecorderAction.CLICK, gi) == 'wait(Pattern("btn.png"), 10).click()'
    assert (
        g.generate(RecorderAction.DBLCLICK, gi)
        == 'wait(Pattern("btn.png"), 10).doubleClick()'
    )
    assert (
        g.generate(RecorderAction.RCLICK, gi)
        == 'wait(Pattern("btn.png"), 10).rightClick()'
    )
    assert g.generate(RecorderAction.WAIT, gi) == 'wait(Pattern("btn.png"), 10)'
    assert (
        g.generate(RecorderAction.WAIT_VANISH, gi)
        == 'waitVanish(Pattern("btn.png"), 10)'
    )


def test_python_generator_similarity_override():
    g = PythonGenerator()
    gi = GenInput(pattern="btn.png", timeout=5, similarity=0.85)
    assert (
        g.generate(RecorderAction.CLICK, gi)
        == 'wait(Pattern("btn.png").similar(0.85), 5).click()'
    )


def test_python_generator_type_escapes_quotes():
    g = PythonGenerator()
    assert (
        g.generate(RecorderAction.TYPE, GenInput(payload='He said "hi"'))
        == 'type("He said \\"hi\\"")'
    )


def test_python_generator_key_combo_with_modifiers():
    g = PythonGenerator()
    out = g.generate(
        RecorderAction.KEY_COMBO, GenInput(payload="Ctrl+Shift+c")
    )
    assert out == 'type("c", KeyModifier.CTRL | KeyModifier.SHIFT)'


def test_python_generator_key_combo_named_key():
    g = PythonGenerator()
    out = g.generate(RecorderAction.KEY_COMBO, GenInput(payload="Alt+ENTER"))
    assert out == "type(Key.ENTER, KeyModifier.ALT)"


def test_python_generator_pause_formats_seconds():
    g = PythonGenerator()
    assert g.generate(RecorderAction.PAUSE, GenInput(payload="3")) == "sleep(3)"
    assert (
        g.generate(RecorderAction.PAUSE, GenInput(payload="1.5")) == "sleep(1.5)"
    )


def test_python_generator_launch_app_emits_open_and_focus():
    g = PythonGenerator()
    out = g.generate(RecorderAction.LAUNCH_APP, GenInput(payload="code"))
    assert out == 'code = App.open("code")\ncode.focus()'


def test_python_generator_launch_app_sanitizes_var_name():
    g = PythonGenerator()
    out = g.generate(RecorderAction.LAUNCH_APP, GenInput(payload="/usr/bin/Sublime Text 4"))
    # Path basename -> identifier; spaces become underscores, lowercased.
    assert out == 'sublime_text_4 = App.open("/usr/bin/Sublime Text 4")\nsublime_text_4.focus()'


def test_python_generator_close_app_uses_find():
    g = PythonGenerator()
    out = g.generate(RecorderAction.CLOSE_APP, GenInput(payload="firefox"))
    assert out == 'App.find("firefox").close()'


def test_python_generator_app_actions_require_payload():
    g = PythonGenerator()
    with pytest.raises(ValueError):
        g.generate(RecorderAction.LAUNCH_APP, GenInput())
    with pytest.raises(ValueError):
        g.generate(RecorderAction.CLOSE_APP, GenInput())


def test_python_generator_text_actions():
    g = PythonGenerator()
    assert (
        g.generate(RecorderAction.TEXT_CLICK, GenInput(payload="OK"))
        == 'click(findText("OK"))'
    )
    assert (
        g.generate(RecorderAction.TEXT_WAIT, GenInput(payload="Loading", timeout=10))
        == 'wait(findText("Loading"), 10)'
    )
    assert (
        g.generate(RecorderAction.TEXT_EXISTS, GenInput(payload="Done", timeout=5))
        == 'exists(findText("Done"), 5)'
    )
    with pytest.raises(ValueError):
        g.generate(RecorderAction.TEXT_CLICK, GenInput())


def test_python_generator_drag_drop_two_patterns():
    g = PythonGenerator()
    gi = GenInput(pattern="src.png", pattern2="dst.png", timeout=5)
    assert g.generate(RecorderAction.DRAG_DROP, gi) == (
        'dragDrop(wait(Pattern("src.png"), 5), wait(Pattern("dst.png"), 5))'
    )


def test_python_generator_swipe_uses_screen():
    g = PythonGenerator()
    gi = GenInput(pattern="a.png", pattern2="b.png", timeout=10)
    assert g.generate(RecorderAction.SWIPE, gi) == (
        'Screen().swipe(wait(Pattern("a.png"), 10), wait(Pattern("b.png"), 10))'
    )


def test_python_generator_two_pattern_requires_both():
    g = PythonGenerator()
    with pytest.raises(ValueError):
        g.generate(RecorderAction.DRAG_DROP, GenInput(pattern="src.png"))


def test_python_generator_wheel_payload():
    g = PythonGenerator()
    assert g.generate(RecorderAction.WHEEL, GenInput(payload="down")) == "wheel(1, 1)"
    assert g.generate(RecorderAction.WHEEL, GenInput(payload="up 3")) == "wheel(-1, 3)"
    assert g.generate(RecorderAction.WHEEL, GenInput(payload="-1, 5")) == "wheel(-1, 5)"
    with pytest.raises(ValueError):
        g.generate(RecorderAction.WHEEL, GenInput(payload="sideways"))
    with pytest.raises(ValueError):
        g.generate(RecorderAction.WHEEL, GenInput())


def test_python_generator_pattern_required():
    g = PythonGenerator()
    with pytest.raises(ValueError):
        g.generate(RecorderAction.CLICK, GenInput())


def test_default_generator_is_python():
    assert default_generator().name == "python"


# ---------------------------------------------------------------------------
# RecorderSession
# ---------------------------------------------------------------------------


def test_session_records_pattern_and_payload(tmp_path: Path):
    session = RecorderSession()
    seen: list[int] = []
    session.on_change = lambda: seen.append(len(session.lines()))

    img = session.temp_dir() / "btn.png"
    img.write_bytes(b"\x89PNG fake")

    session.record_pattern(RecorderAction.CLICK, img, timeout=5)
    session.record_payload(RecorderAction.TYPE, "hello")
    session.record_payload(RecorderAction.PAUSE, "2")

    assert session.preview_text() == (
        'wait(Pattern("btn.png"), 5).click()\n'
        'type("hello")\n'
        "sleep(2)"
    )
    assert seen == [1, 2, 3]


def test_session_finalize_copies_pngs_and_returns_code(tmp_path: Path):
    session = RecorderSession()
    img = session.temp_dir() / "btn.png"
    img.write_bytes(b"\x89PNG fake")
    session.record_pattern(RecorderAction.CLICK, img, timeout=5)
    session.record_payload(RecorderAction.PAUSE, "1")

    target = tmp_path / "script_dir"
    code, moved = session.finalize(target)

    assert moved == [(target / "btn.png").resolve()]
    assert (target / "btn.png").read_bytes() == b"\x89PNG fake"
    assert code == 'wait(Pattern("btn.png"), 5).click()\nsleep(1)\n'


def test_session_records_two_patterns_for_drag_drop(tmp_path: Path):
    session = RecorderSession()
    src = session.temp_dir() / "src.png"
    dst = session.temp_dir() / "dst.png"
    src.write_bytes(b"src")
    dst.write_bytes(b"dst")

    session.record_two_patterns(RecorderAction.DRAG_DROP, src, dst, timeout=5)
    session.record_payload(RecorderAction.WHEEL, "down 2")

    assert session.preview_text() == (
        'dragDrop(wait(Pattern("src.png"), 5), wait(Pattern("dst.png"), 5))\n'
        "wheel(1, 2)"
    )


def test_session_finalize_copies_both_patterns(tmp_path: Path):
    session = RecorderSession()
    src = session.temp_dir() / "src.png"
    dst = session.temp_dir() / "dst.png"
    src.write_bytes(b"src")
    dst.write_bytes(b"dst")
    session.record_two_patterns(RecorderAction.SWIPE, src, dst)

    target = tmp_path / "out"
    code, moved = session.finalize(target)

    assert sorted(p.name for p in moved) == ["dst.png", "src.png"]
    assert (target / "src.png").read_bytes() == b"src"
    assert (target / "dst.png").read_bytes() == b"dst"
    assert 'Screen().swipe(wait(Pattern("src.png")' in code
    assert 'wait(Pattern("dst.png")' in code


def test_session_two_patterns_rejects_single_pattern_action():
    session = RecorderSession()
    src = session.temp_dir() / "a.png"
    src.write_bytes(b"a")
    with pytest.raises(ValueError):
        session.record_two_patterns(RecorderAction.CLICK, src, src)


def test_session_finalize_renames_on_collision(tmp_path: Path):
    target = tmp_path / "script_dir"
    target.mkdir()
    (target / "btn.png").write_bytes(b"existing")

    session = RecorderSession()
    img = session.temp_dir() / "btn.png"
    img.write_bytes(b"new")
    session.record_pattern(RecorderAction.CLICK, img)

    code, moved = session.finalize(target)
    assert moved[0].name == "btn-1.png"
    assert (target / "btn.png").read_bytes() == b"existing"
    assert (target / "btn-1.png").read_bytes() == b"new"
    assert 'Pattern("btn-1.png")' in code


def test_session_finalize_keeps_pattern_already_in_target(tmp_path: Path):
    """When the user captured straight into the project's assets dir,
    finalize should not copy the file onto itself; it should rewrite the
    code to use the relative path so the script can find it."""
    target = tmp_path / "proj"
    assets = target / "assets"
    assets.mkdir(parents=True)
    pat = assets / "btn.png"
    pat.write_bytes(b"data")

    session = RecorderSession()
    session.record_pattern(RecorderAction.CLICK, pat, timeout=5)

    code, moved = session.finalize(target)
    assert moved == [pat.resolve()]
    assert pat.read_bytes() == b"data"  # not corrupted by self-copy
    assert 'Pattern("assets/btn.png")' in code


def test_session_remove_last_undoes_recording(tmp_path: Path):
    session = RecorderSession()
    img = session.temp_dir() / "btn.png"
    img.write_bytes(b"data")
    session.record_pattern(RecorderAction.CLICK, img)
    session.record_payload(RecorderAction.PAUSE, "2")
    session.remove_last()
    assert len(session.lines()) == 1
    assert session.lines()[0].action is RecorderAction.CLICK


def test_session_discard_clears_temp_dir(tmp_path: Path):
    session = RecorderSession()
    tmp = session.temp_dir()
    (tmp / "btn.png").write_bytes(b"data")
    assert tmp.exists()
    session.discard()
    assert not tmp.exists()
    assert session.lines() == []
