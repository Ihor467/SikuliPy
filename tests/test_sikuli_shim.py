"""Tests for the ``sikuli`` SikuliX-compatibility shim.

The shim is implemented on top of :mod:`sikulipy`; these tests pin the
public surface (re-exports, module-level wrappers, Settings behaviour,
dialog fallbacks, camelCase aliases) so scripts written against the
original SikuliX IDE can run unchanged.

Heavy dependencies (cv2/numpy) are lazy-imported by ``sikuli/__init__.py``,
so the core import tests run on any host. A couple of tests that need
``Region`` / ``Screen`` guard with ``pytest.importorskip``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import sikuli
from sikuli import Settings


def _cv2_ok() -> bool:
    """True iff the cv2 stack actually imports on this host.

    Some hosts have cv2 installed but numpy refuses to load (``NumPy was
    built with baseline optimizations: (X86_V2) but your machine doesn't
    support: (X86_V2)``). That surfaces as a RuntimeError from inside
    numpy, not an ImportError, so :func:`pytest.importorskip` doesn't
    cover it. We probe with a plain try/except.
    """
    try:
        import cv2  # noqa: F401
        import numpy  # noqa: F401
    except Exception:
        return False
    return True


skip_without_cv2 = pytest.mark.skipif(
    not _cv2_ok(),
    reason="cv2/numpy unavailable on this host (see conftest/_cv2_ok)",
)


# ---------------------------------------------------------------------------
# Package surface
# ---------------------------------------------------------------------------


def test_all_symbols_exported():
    expected = {
        # classes
        "Env", "FindFailed", "FindFailedResponse", "Image", "ImagePath",
        "Key", "KeyModifier", "Location", "Match", "Mouse", "OculixTimeout",
        "Offset", "Options", "Pattern", "Region", "Screen", "ScreenImage",
        "ScreenOperationError", "Settings", "SikuliException", "SikuliXception",
        # bundle / misc
        "addImagePath", "getBundlePath", "getImagePath", "removeImagePath",
        "setBundlePath", "sleep",
        # dialogs
        "input", "inputText", "popask", "popup", "popupAsk", "selectRegion",
        # actions
        "click", "doubleClick", "dragDrop", "exists", "find", "findAll",
        "findAllText", "findText", "hover", "keyDown", "keyUp", "mouseDown",
        "mouseMove", "mouseUp", "paste", "rightClick", "text", "type", "wait",
        "waitVanish", "wheel",
    }
    assert expected.issubset(set(sikuli.__all__))


@skip_without_cv2
def test_star_import_matches_all():
    """``from sikuli import *`` must bind at least every name in ``__all__``.

    Star-import resolves every name in ``__all__`` eagerly, including the
    lazy ones (Region/Screen/Image/…), so it can only work on hosts
    where the numpy/cv2 stack loads.
    """
    ns: dict[str, object] = {}
    exec("from sikuli import *", ns)  # noqa: S102 - controlled test input
    missing = [name for name in sikuli.__all__ if name not in ns]
    assert missing == []


def test_lightweight_reexports_are_the_real_classes():
    from sikulipy.core.keyboard import Key as RealKey
    from sikulipy.core.location import Location as RealLocation
    from sikulipy.core.mouse import Mouse as RealMouse
    from sikulipy.script.exceptions import FindFailed as RealFindFailed

    assert sikuli.Key is RealKey
    assert sikuli.Location is RealLocation
    assert sikuli.Mouse is RealMouse
    assert sikuli.FindFailed is RealFindFailed


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def test_settings_defaults_look_like_sikulix():
    # A handful of SikuliX-documented defaults. We don't pin every field,
    # just the ones user scripts reliably depend on.
    assert Settings.OcrTextRead is False
    assert Settings.OcrTextSearch is False
    assert Settings.MinSimilarity == pytest.approx(0.7)
    assert Settings.ActionLogs is True


def test_settings_assignment_is_visible_on_next_read():
    try:
        Settings.OcrTextRead = True
        assert Settings.OcrTextRead is True
        Settings.MinSimilarity = 0.95
        assert Settings.MinSimilarity == pytest.approx(0.95)
    finally:
        Settings.OcrTextRead = False
        Settings.MinSimilarity = 0.7


def test_settings_move_mouse_delay_writes_through_to_mouse():
    from sikulipy.core.mouse import Mouse

    before = Mouse.move_mouse_delay
    try:
        Settings.MoveMouseDelay = 0.42
        assert Mouse.move_mouse_delay == pytest.approx(0.42)
    finally:
        Settings.MoveMouseDelay = before
        Mouse.move_mouse_delay = before


def test_settings_type_delay_writes_through_to_key():
    from sikulipy.core.keyboard import Key

    before = Key._type_delay
    try:
        Settings.TypeDelay = 0.05
        assert Key._type_delay == pytest.approx(0.05)
    finally:
        Settings.TypeDelay = before
        Key._type_delay = before


# ---------------------------------------------------------------------------
# Bundle path / image path
# ---------------------------------------------------------------------------


@skip_without_cv2
def test_bundle_and_image_path_helpers(tmp_path: Path):
    from sikulipy.core.image import ImagePath

    saved = list(ImagePath._paths)
    saved_bundle = Settings.BundlePath
    try:
        ImagePath._paths = []
        Settings.BundlePath = None

        assert sikuli.getBundlePath() is None
        assert sikuli.getImagePath() == []

        bundle = tmp_path / "demo.sikuli"
        bundle.mkdir()
        sikuli.setBundlePath(bundle)
        assert sikuli.getBundlePath() == str(bundle.resolve())
        assert str(bundle.resolve()) in sikuli.getImagePath()

        extra = tmp_path / "assets"
        extra.mkdir()
        sikuli.addImagePath(extra)
        assert str(extra.resolve()) in sikuli.getImagePath()

        sikuli.removeImagePath(extra)
        assert str(extra.resolve()) not in sikuli.getImagePath()
    finally:
        ImagePath._paths = saved
        Settings.BundlePath = saved_bundle


# ---------------------------------------------------------------------------
# sleep
# ---------------------------------------------------------------------------


def test_sleep_invokes_time_sleep(monkeypatch):
    calls: list[float] = []
    import sikuli._bundle as bundle_mod

    monkeypatch.setattr(bundle_mod.time, "sleep", lambda s: calls.append(s))
    sikuli.sleep(0.25)
    assert calls == [0.25]


# ---------------------------------------------------------------------------
# Module-level wrappers — delegation to primary Screen
# ---------------------------------------------------------------------------


class _FakeScreen:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    def _record(self, name: str):
        def fn(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return ("retval", name)
        return fn

    def __getattr__(self, name: str):  # pragma: no cover - generic stub
        return self._record(name)


@pytest.fixture
def fake_primary(monkeypatch) -> _FakeScreen:
    fake = _FakeScreen()
    import sikuli._wrappers as wr

    monkeypatch.setattr(wr, "_primary", lambda: fake)
    return fake


def test_click_delegates_to_primary_screen(fake_primary: _FakeScreen):
    assert sikuli.click("btn.png") == ("retval", "click")
    assert fake_primary.calls == [("click", ("btn.png",), {})]


def test_double_click_delegates(fake_primary: _FakeScreen):
    sikuli.doubleClick("x.png")
    assert fake_primary.calls[0][0] == "double_click"


def test_find_wait_exists_map_to_snake_case(fake_primary: _FakeScreen):
    sikuli.find("a.png")
    sikuli.findAll("b.png")
    sikuli.wait("c.png", timeout=1.5)
    sikuli.exists("d.png")
    sikuli.waitVanish("e.png", timeout=2.0)
    names = [c[0] for c in fake_primary.calls]
    assert names == ["find", "find_all", "wait", "exists", "wait_vanish"]
    assert fake_primary.calls[2] == ("wait", ("c.png",), {"timeout": 1.5})


def test_drag_drop_and_type_paste_delegate(fake_primary: _FakeScreen):
    sikuli.dragDrop("from.png", "to.png")
    sikuli.type("hello")
    sikuli.paste("world")
    names = [c[0] for c in fake_primary.calls]
    assert names == ["drag_drop", "type", "paste"]


# ---------------------------------------------------------------------------
# Mouse/keyboard thin wrappers (no primary screen involved)
# ---------------------------------------------------------------------------


def test_mouse_wrappers_hit_mouse_class(monkeypatch):
    from sikulipy.core import mouse as mouse_mod

    seen: list[str] = []
    monkeypatch.setattr(mouse_mod.Mouse, "move", classmethod(lambda cls, loc: seen.append(f"move:{loc}")))
    monkeypatch.setattr(mouse_mod.Mouse, "down", classmethod(lambda cls, b=1: seen.append(f"down:{b}")))
    monkeypatch.setattr(mouse_mod.Mouse, "up",   classmethod(lambda cls, b=1: seen.append(f"up:{b}")))
    monkeypatch.setattr(mouse_mod.Mouse, "wheel", classmethod(lambda cls, d, steps=1: seen.append(f"wheel:{d}:{steps}")))

    sikuli.mouseMove((10, 20))
    sikuli.mouseDown()
    sikuli.mouseUp()
    sikuli.wheel(1, steps=3)
    assert seen == ["move:(10, 20)", "down:1", "up:1", "wheel:1:3"]


def test_key_wrappers_hit_key_class(monkeypatch):
    from sikulipy.core import keyboard as kb

    pressed: list[str] = []
    released: list[str] = []
    monkeypatch.setattr(kb.Key, "press",   classmethod(lambda cls, k: pressed.append(k)))
    monkeypatch.setattr(kb.Key, "release", classmethod(lambda cls, k: released.append(k)))

    sikuli.keyDown(kb.Key.SHIFT)
    sikuli.keyUp(kb.Key.SHIFT)
    assert pressed == [kb.Key.SHIFT]
    assert released == [kb.Key.SHIFT]


# ---------------------------------------------------------------------------
# Dialogs — probe ordering
# ---------------------------------------------------------------------------


class _StubProc:
    def __init__(self, stdout: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.returncode = returncode


def test_popup_prefers_kdialog(monkeypatch):
    calls: list[list[str]] = []

    def fake_which(name: str):
        return f"/usr/bin/{name}" if name == "kdialog" else None

    def fake_run(cmd, capture_output=True, text=True):
        calls.append(cmd)
        return _StubProc()

    monkeypatch.setattr("sikuli._dialogs.shutil.which", fake_which)
    monkeypatch.setattr("sikuli._dialogs.subprocess.run", fake_run)
    sikuli.popup("hi")
    assert calls and calls[0][0] == "/usr/bin/kdialog"
    assert "--msgbox" in calls[0]


def test_popup_falls_back_to_zenity_when_no_kdialog(monkeypatch):
    calls: list[list[str]] = []

    def fake_which(name: str):
        return f"/usr/bin/{name}" if name == "zenity" else None

    def fake_run(cmd, capture_output=True, text=True):
        calls.append(cmd)
        return _StubProc()

    monkeypatch.setattr("sikuli._dialogs.shutil.which", fake_which)
    monkeypatch.setattr("sikuli._dialogs.subprocess.run", fake_run)
    sikuli.popup("hi")
    assert calls and calls[0][0] == "/usr/bin/zenity"


def test_popup_ask_returns_true_on_zero_exit(monkeypatch):
    monkeypatch.setattr("sikuli._dialogs.shutil.which",
                        lambda name: f"/usr/bin/{name}" if name == "kdialog" else None)
    monkeypatch.setattr("sikuli._dialogs.subprocess.run",
                        lambda cmd, capture_output=True, text=True: _StubProc(returncode=0))
    assert sikuli.popupAsk("sure?") is True
    assert sikuli.popask is sikuli.popupAsk


def test_popup_ask_returns_false_on_nonzero_exit(monkeypatch):
    monkeypatch.setattr("sikuli._dialogs.shutil.which",
                        lambda name: f"/usr/bin/{name}" if name == "kdialog" else None)
    monkeypatch.setattr("sikuli._dialogs.subprocess.run",
                        lambda cmd, capture_output=True, text=True: _StubProc(returncode=1))
    assert sikuli.popupAsk("sure?") is False


def test_input_returns_stdout_and_none_on_cancel(monkeypatch):
    monkeypatch.setattr("sikuli._dialogs.shutil.which",
                        lambda name: f"/usr/bin/{name}" if name == "kdialog" else None)

    responses = [_StubProc(stdout="alice\n", returncode=0),
                 _StubProc(stdout="", returncode=1)]
    call = iter(responses)
    monkeypatch.setattr("sikuli._dialogs.subprocess.run",
                        lambda *a, **k: next(call))

    assert sikuli.input("name?") == "alice"
    assert sikuli.input("name?") is None


# ---------------------------------------------------------------------------
# selectRegion
# ---------------------------------------------------------------------------


@skip_without_cv2
def test_select_region_returns_region_from_overlay(monkeypatch):
    from sikulipy.core.region import Region

    # Fake the overlay entry points so we don't need a display / mss.
    from sikulipy.ide.capture import CaptureRect
    import sikuli._select as sel

    monkeypatch.setattr(sel, "_grab_fullscreen", lambda: (object(), {"left": 0, "top": 0}))
    monkeypatch.setattr(sel, "_run_overlay",
                        lambda _bg: CaptureRect(x=10, y=20, w=30, h=40))

    r = sikuli.selectRegion("prompt")
    assert isinstance(r, Region)
    assert (r.x, r.y, r.w, r.h) == (10, 20, 30, 40)


def test_select_region_returns_none_on_cancel(monkeypatch):
    pytest.importorskip("sikulipy.core.region")
    import sikuli._select as sel

    monkeypatch.setattr(sel, "_grab_fullscreen", lambda: (object(), {"left": 0, "top": 0}))
    monkeypatch.setattr(sel, "_run_overlay", lambda _bg: None)
    assert sikuli.selectRegion("prompt") is None


# ---------------------------------------------------------------------------
# camelCase aliases on Region (installed lazily on first Region access)
# ---------------------------------------------------------------------------


@skip_without_cv2
def test_region_camel_case_aliases_map_to_snake_case():
    Region = sikuli.Region  # triggers lazy install via __getattr__  # noqa: N806

    pairs = [
        ("findAll", "find_all"),
        ("waitVanish", "wait_vanish"),
        ("doubleClick", "double_click"),
        ("rightClick", "right_click"),
        ("dragDrop", "drag_drop"),
        ("findText", "find_text"),
        ("findAllText", "find_all_text"),
        ("hasText", "has_text"),
        ("topLeft", "top_left"),
        ("bottomRight", "bottom_right"),
        ("isValid", "is_valid"),
    ]
    for camel, snake in pairs:
        assert hasattr(Region, camel), f"missing alias {camel}"
        assert getattr(Region, camel) is getattr(Region, snake)
