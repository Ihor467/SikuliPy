"""Phase 7 tests — headless IDE models.

Every model in :mod:`sikulipy.ide` is exercised without Flet. The Flet
view in ``app.py`` is a thin adaptor — its contract is covered by these
model tests plus a smoke import.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from sikulipy.ide.capture import CaptureRect, CaptureSession
from sikulipy.ide.console import ConsoleBuffer, ConsoleRedirect, strip_ansi
from sikulipy.ide.editor import EditorDocument
from sikulipy.ide.explorer import build_tree, classify
from sikulipy.ide.sidebar import SidebarModel
from sikulipy.ide.statusbar import StatusModel
from sikulipy.ide.toolbar import ToolbarActions


# ---------------------------------------------------------------------------
# Explorer
# ---------------------------------------------------------------------------


def test_classify_recognises_kinds(tmp_path: Path):
    bundle = tmp_path / "demo.sikuli"
    bundle.mkdir()
    script = tmp_path / "s.py"
    script.write_text("")
    image = tmp_path / "img.png"
    image.write_bytes(b"")
    unknown = tmp_path / "x.txt"
    unknown.write_text("")

    assert classify(tmp_path) == "dir"
    assert classify(bundle) == "bundle"
    assert classify(script) == "script"
    assert classify(image) == "image"
    assert classify(unknown) is None


def test_build_tree_lists_scripts_bundles_and_hidden(tmp_path: Path):
    (tmp_path / "a.py").write_text("")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.py").write_text("")
    bundle = tmp_path / "c.sikuli"
    bundle.mkdir()
    (bundle / "c.py").write_text("")
    (bundle / "btn.png").write_bytes(b"")
    (tmp_path / ".hidden.py").write_text("")

    tree = build_tree(tmp_path)
    kinds = {n.kind for n in tree.iter_descendants()}
    assert kinds == {"dir", "bundle", "script", "image"}

    bundle_node = tree.find(bundle.resolve())
    assert bundle_node is not None
    assert [c.kind for c in bundle_node.children] == ["image"]

    # Hidden files excluded by default.
    names = [n.name for n in tree.iter_descendants()]
    assert ".hidden.py" not in names

    # With include_hidden=True they appear.
    tree_hidden = build_tree(tmp_path, include_hidden=True)
    names = [n.name for n in tree_hidden.iter_descendants()]
    assert ".hidden.py" in names


def test_build_tree_orders_dirs_before_files(tmp_path: Path):
    (tmp_path / "z.py").write_text("")
    (tmp_path / "a_dir").mkdir()
    (tmp_path / "a_dir" / "x.py").write_text("")
    tree = build_tree(tmp_path)
    top_names = [c.name for c in tree.children]
    assert top_names == ["a_dir", "z.py"]


# ---------------------------------------------------------------------------
# EditorDocument
# ---------------------------------------------------------------------------


def test_editor_set_text_tracks_dirty_and_undo():
    doc = EditorDocument()
    doc.set_text("hello")
    assert doc.dirty is True
    assert doc.can_undo()
    assert doc.undo() is True
    assert doc.text == ""
    assert doc.redo() is True
    assert doc.text == "hello"


def test_editor_insert_and_delete_range():
    doc = EditorDocument(text="abcdef", cursor=3)
    doc.insert("XYZ")
    assert doc.text == "abcXYZdef"
    assert doc.cursor == 6
    doc.delete_range(3, 6)
    assert doc.text == "abcdef"


def test_editor_save_and_open_roundtrip(tmp_path: Path):
    target = tmp_path / "script.py"
    doc = EditorDocument(text="print('hi')\n")
    doc.save(target)
    assert target.read_text() == "print('hi')\n"
    assert doc.dirty is False

    reopened = EditorDocument.open(target)
    assert reopened.text == "print('hi')\n"
    assert reopened.path == target.resolve()


def test_editor_pattern_references_are_deduped_and_ordered():
    doc = EditorDocument(text=(
        "Pattern('a.png')\n"
        "Pattern( \"b.png\" )\n"
        "'c.PNG'\n"
        "Pattern('a.png')  # dup\n"
    ))
    refs = doc.pattern_references()
    assert refs == ["a.png", "b.png", "c.PNG"]


def test_editor_pattern_absolute_paths_resolve_against_document(tmp_path: Path):
    target = tmp_path / "script.py"
    target.write_text("")
    doc = EditorDocument(text="Pattern('btn.png')\n", path=target)
    assert doc.pattern_absolute_paths() == [tmp_path / "btn.png"]


# ---------------------------------------------------------------------------
# Console
# ---------------------------------------------------------------------------


def test_strip_ansi_removes_sgr_and_osc():
    assert strip_ansi("\x1b[31mred\x1b[0m text") == "red text"
    assert strip_ansi("\x1b]0;title\x07rest") == "rest"


def test_console_buffer_caps_and_subscribes():
    buf = ConsoleBuffer(max_entries=3)
    seen: list[str] = []
    unsub = buf.subscribe(lambda e: seen.append(e.text))
    for i in range(5):
        buf.write("stdout", f"{i}\n")
    assert [e.text for e in buf.entries()] == ["2\n", "3\n", "4\n"]
    assert seen == ["0\n", "1\n", "2\n", "3\n", "4\n"]
    unsub()
    buf.write("stdout", "x")
    assert seen[-1] != "x"


def test_console_redirect_captures_stdout_and_stderr():
    buf = ConsoleBuffer()
    with ConsoleRedirect(buf):
        print("hello")
        print("oops", file=sys.stderr)
    entries = buf.entries()
    streams = {e.stream for e in entries}
    assert streams == {"stdout", "stderr"}
    assert "hello\n" in buf.text()
    assert "oops\n" in buf.text()
    # Streams restored.
    assert sys.stdout is not None and not isinstance(
        sys.stdout, type(ConsoleRedirect)
    )


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------


def test_capture_rect_from_corners_normalises():
    r = CaptureRect.from_corners(10, 20, 5, 8)
    assert (r.x, r.y, r.w, r.h) == (5, 8, 5, 12)
    assert not r.is_empty
    assert CaptureRect.from_corners(0, 0, 0, 0).is_empty


def test_capture_session_state_machine():
    s = CaptureSession()
    assert s.state == "idle"
    s.begin(10, 20)
    assert s.state == "selecting"
    s.update(40, 60)
    assert s.rect == CaptureRect(10, 20, 30, 40)
    rect = s.commit()
    assert rect == CaptureRect(10, 20, 30, 40)
    assert s.state == "captured"


def test_capture_session_cancel_from_empty_commit():
    s = CaptureSession()
    s.begin(5, 5)
    s.update(5, 5)
    assert s.commit() is None
    assert s.state == "cancelled"


def test_capture_session_save_requires_committed_selection(tmp_path: Path):
    s = CaptureSession()
    with pytest.raises(RuntimeError):
        s.save(tmp_path / "x.png")


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------


def test_sidebar_lists_pattern_refs_and_captures(tmp_path: Path):
    script = tmp_path / "s.py"
    script.write_text("")
    doc = EditorDocument(text="Pattern('btn.png')\n", path=script)
    model = SidebarModel(document=doc)
    captured = tmp_path / "snap.png"
    captured.write_bytes(b"data")
    model.add_captured(captured)

    items = model.items()
    names = {i.name for i in items}
    assert names == {"btn.png", "snap.png"}
    flags = {i.name: i.exists for i in items}
    assert flags["btn.png"] is False
    assert flags["snap.png"] is True


# ---------------------------------------------------------------------------
# Statusbar
# ---------------------------------------------------------------------------


def test_status_model_segments_and_render():
    m = StatusModel()
    m.set_cursor(12, 4)
    m.set_file(Path("/tmp/demo.py"), dirty=True)
    m.set_message("Running")
    segs = m.segments()
    assert any(s.startswith("SikuliPy") for s in segs)
    assert "demo.py *" in segs
    assert "Ln 12, Col 4" in segs
    assert "Running" in segs
    rendered = m.render(" | ")
    assert " | " in rendered
    assert rendered.count(" | ") == len(segs) - 1


# ---------------------------------------------------------------------------
# Toolbar
# ---------------------------------------------------------------------------


class _FakeRunner:
    def __init__(self) -> None:
        self.runs: list[Path] = []
        self.stopped = 0
        self.alive = False

    def run(self, path: Path) -> int:
        self.runs.append(path)
        self.alive = True
        return 0

    def stop(self) -> None:
        self.stopped += 1
        self.alive = False

    def is_running(self) -> bool:
        return self.alive


def test_toolbar_new_clears_document(tmp_path: Path):
    doc = EditorDocument(text="old", path=tmp_path / "x.py", dirty=True)
    tb = ToolbarActions(document=doc, runner=_FakeRunner())
    tb.new()
    assert doc.text == ""
    assert doc.path is None
    assert doc.dirty is False


def test_toolbar_open_loads_from_disk(tmp_path: Path):
    target = tmp_path / "demo.py"
    target.write_text("print(1)\n")
    doc = EditorDocument()
    tb = ToolbarActions(document=doc, runner=_FakeRunner())
    tb.open(target)
    assert doc.text == "print(1)\n"
    assert doc.path == target.resolve()


def test_toolbar_run_saves_dirty_and_launches(tmp_path: Path):
    target = tmp_path / "demo.py"
    target.write_text("")
    doc = EditorDocument.open(target)
    doc.set_text("print(2)\n")
    assert doc.dirty
    runner = _FakeRunner()
    tb = ToolbarActions(document=doc, runner=runner)
    tb.run()
    assert runner.runs == [target.resolve()]
    assert target.read_text() == "print(2)\n"
    assert doc.dirty is False


def test_toolbar_run_refuses_unsaved_buffer():
    doc = EditorDocument(text="hi")
    tb = ToolbarActions(document=doc, runner=_FakeRunner())
    with pytest.raises(RuntimeError):
        tb.run()


def test_toolbar_begin_capture_resets_session():
    doc = EditorDocument()
    tb = ToolbarActions(document=doc, runner=_FakeRunner())
    tb.capture.begin(1, 1)
    tb.capture.update(10, 10)
    tb.capture.commit()
    assert tb.capture.state == "captured"
    tb.begin_capture()
    assert tb.capture.state == "idle"


# ---------------------------------------------------------------------------
# Smoke import of the Flet entry point
# ---------------------------------------------------------------------------


def test_app_module_imports_without_flet_side_effects():
    # Ensure the module can be imported in test context (Flet's ft.app
    # is only called from main()).
    import sikulipy.ide.app as app_module

    assert callable(app_module.ide_main)
    assert callable(app_module.main)
