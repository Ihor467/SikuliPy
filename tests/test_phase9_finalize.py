"""Phase 9 step 5 — finalize for the Android surface.

The session has to surface the active target's headers so the IDE can
prepend ``from sikulipy.android.screen import ADBScreen`` and
``screen = ADBScreen.start(...)`` exactly once per script. ``finalize``
itself still only deals with PNG placement — those concerns stay
separate so a non-IDE caller (e.g. a CLI export) can pick which header
strategy to apply.
"""

from __future__ import annotations

from pathlib import Path

from sikulipy.ide.recorder import (
    RecorderAction,
    RecorderSession,
    _FakeSurface,
)


def _png(path: Path) -> Path:
    path.write_bytes(b"\x89PNG\r\n\x1a\n")
    return path


# ---------------------------------------------------------------------------
# required_imports / required_setup
# ---------------------------------------------------------------------------


def test_desktop_session_has_no_setup_lines():
    sess = RecorderSession()
    assert sess.required_imports() == ["from sikulipy import *"]
    assert sess.required_setup() == []


def test_android_session_exposes_adbscreen_header():
    sess = RecorderSession()
    sess.set_surface(
        _FakeSurface(
            name="android",
            imports=[
                "from sikulipy import *",
                "from sikulipy.android.screen import ADBScreen",
            ],
            setup=['screen = ADBScreen.start(serial="abc123")'],
        )
    )
    assert "from sikulipy.android.screen import ADBScreen" in sess.required_imports()
    assert sess.required_setup() == ['screen = ADBScreen.start(serial="abc123")']


def test_required_imports_returns_a_copy():
    """Mutating the returned list must not bleed into the surface."""
    surface = _FakeSurface(
        name="android",
        imports=["from sikulipy import *"],
        setup=["screen = ADBScreen.start()"],
    )
    sess = RecorderSession()
    sess.set_surface(surface)
    sess.required_imports().append("garbage")
    sess.required_setup().append("garbage")
    assert "garbage" not in surface.header_imports()
    assert "garbage" not in surface.header_setup()


# ---------------------------------------------------------------------------
# Finalize keeps producing the recorded code lines unchanged
# ---------------------------------------------------------------------------


def test_finalize_emits_android_call_lines(tmp_path: Path):
    sess = RecorderSession()
    sess.set_surface(_FakeSurface(name="android"))
    sess.record_payload(RecorderAction.TYPE, "hi")
    captured = _png(tmp_path / "btn.png")
    sess.record_pattern(RecorderAction.CLICK, captured)

    out_dir = tmp_path / "out"
    code, moved = sess.finalize(out_dir)
    lines = [ln for ln in code.splitlines() if ln]
    assert lines == [
        'screen.type("hi")',
        'screen.click(Pattern("btn.png"))',
    ]
    # finalize copies the PNG into the script's directory.
    assert moved == [out_dir.resolve() / "btn.png"]


def test_finalize_does_not_inject_surface_header(tmp_path: Path):
    """Header injection is the IDE's job — keep ``finalize`` purely
    concerned with code+pattern placement so a non-IDE caller doesn't
    get unexpected import lines glued onto the output."""
    sess = RecorderSession()
    sess.set_surface(
        _FakeSurface(
            name="android",
            imports=["from sikulipy.android.screen import ADBScreen"],
            setup=["screen = ADBScreen.start()"],
        )
    )
    sess.record_payload(RecorderAction.TYPE, "x")
    code, _ = sess.finalize(tmp_path)
    assert "ADBScreen" not in code
    assert "screen = " not in code
