"""Phase 8 — IDE-level recorder integration.

Exercises the small bridge between ``_IDEState`` and ``RecorderSession``:
starting a session, finalizing into the document, and cancellation.
The Flet widget tree is not instantiated — these are pure model tests.
"""

from __future__ import annotations

from pathlib import Path

from sikulipy.ide.app import _IDEState
from sikulipy.ide.recorder import RecorderAction, RecorderSession


def test_state_starts_with_no_recorder(tmp_path: Path):
    state = _IDEState(root=tmp_path)
    assert state.recorder is None


def test_starting_recorder_sets_session(tmp_path: Path):
    state = _IDEState(root=tmp_path)
    state.recorder = RecorderSession()
    assert state.recorder is not None
    assert state.recorder.lines() == []


def test_finalize_inserts_into_document(tmp_path: Path):
    state = _IDEState(root=tmp_path)
    state.recorder = RecorderSession()

    img = state.recorder.temp_dir() / "btn.png"
    img.write_bytes(b"\x89PNG fake")
    state.recorder.record_pattern(RecorderAction.CLICK, img, timeout=5)
    state.recorder.record_payload(RecorderAction.PAUSE, "1")

    target = tmp_path / "scripts"
    code, moved = state.recorder.finalize(target)
    state.document.insert(code, at=state.document.cursor)
    state.recorder = None

    assert 'wait(Pattern("btn.png"), 5).click()' in state.document.text
    assert "sleep(1)" in state.document.text
    assert state.document.dirty is True
    assert (target / "btn.png").exists()
    assert moved == [(target / "btn.png").resolve()]


def test_cancel_clears_temp_dir_and_session(tmp_path: Path):
    state = _IDEState(root=tmp_path)
    state.recorder = RecorderSession()
    tmp = state.recorder.temp_dir()
    (tmp / "btn.png").write_bytes(b"data")
    assert tmp.exists()

    state.recorder.discard()
    state.recorder = None

    assert state.recorder is None
    assert not tmp.exists()
