"""Phase 11 — WebAutoController state machine + subscriber fan-out."""

from __future__ import annotations

from pathlib import Path

import pytest

from sikulipy.ide.web_panel import WebAutoController
from sikulipy.web import ElementKind, _FakeBackend


np = pytest.importorskip("numpy")


_ELEMENTS = [
    {
        "tag": "a",
        "type": "",
        "role": "",
        "name": "Home",
        "selector": "a#home",
        "xpath": "//a[@id='home']",
        "bounds": [10, 10, 80, 30],
    },
    {
        "tag": "button",
        "type": "submit",
        "role": "",
        "name": "Sign in",
        "selector": "button[type='submit']",
        "xpath": "//button[1]",
        "bounds": [120, 10, 100, 36],
    },
    {
        "tag": "input",
        "type": "checkbox",
        "role": "",
        "name": "Remember me",
        "selector": "input.remember",
        "xpath": "//input[1]",
        "bounds": [10, 80, 20, 20],
    },
]


def _backend_with_frame():
    frame = np.zeros((600, 800, 3), dtype=np.uint8)
    return _FakeBackend(
        elements_payload=_ELEMENTS,
        device_pixel_ratio=1.0,
        document_size=(800, 600),
        frame_factory=lambda: frame,
    )


def test_start_loads_elements_and_notifies(tmp_path: Path) -> None:
    backend = _backend_with_frame()
    notifications: list = []
    ctrl = WebAutoController(project_dir=tmp_path, backend=backend)
    ctrl.subscribe(lambda s: notifications.append(s))

    ctrl.start("https://example.com")

    assert ctrl.state.active
    assert ctrl.state.url == "https://example.com"
    assert len(ctrl.state.elements) == 3
    assert ctrl.state.asset_dir == tmp_path / "assets" / "web" / "example.com"
    assert ctrl.state.error is None
    assert notifications, "subscriber should have fired at least once"
    # Backend was driven through the full launch → goto → screenshot → discover loop.
    names = [c[0] for c in backend.calls]
    assert names[:4] == ["launch", "goto", "screenshot", "discover"]


def test_filter_narrows_visible_list(tmp_path: Path) -> None:
    ctrl = WebAutoController(project_dir=tmp_path, backend=_backend_with_frame())
    ctrl.start("https://example.com")

    # Default filter is empty — opt the link + checkbox kinds in,
    # then commit with apply_filter.
    ctrl.set_filter_kind(ElementKind.LINK, True)
    ctrl.set_filter_kind(ElementKind.CHECKBOX_RADIO, True)
    ctrl.apply_filter()
    kinds = {e.kind for e in ctrl.state.filtered()}
    assert ElementKind.BUTTON not in kinds
    assert {ElementKind.LINK, ElementKind.CHECKBOX_RADIO} <= kinds


def test_select_clears_when_filtered_out(tmp_path: Path) -> None:
    ctrl = WebAutoController(project_dir=tmp_path, backend=_backend_with_frame())
    ctrl.start("https://example.com")
    ctrl.set_filter_kind(ElementKind.BUTTON, True)
    ctrl.apply_filter()
    button = next(e for e in ctrl.state.elements if e.kind is ElementKind.BUTTON)
    ctrl.select(button)
    assert ctrl.state.selected is button

    ctrl.set_filter_kind(ElementKind.BUTTON, False)
    ctrl.apply_filter()
    assert ctrl.state.selected is None


def test_take_screenshots_writes_one_per_filtered(tmp_path: Path) -> None:
    backend = _backend_with_frame()
    written: list[Path] = []

    def writer(path: Path, image) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake-png")
        written.append(path)
        return path

    ctrl = WebAutoController(
        project_dir=tmp_path, backend=backend, asset_writer=writer
    )
    ctrl.start("https://example.com")
    for k in ElementKind:
        ctrl.set_filter_kind(k, True)
    ctrl.apply_filter()
    saved = ctrl.take_screenshots()
    assert len(saved) == 3
    # Each filename includes the role/tag + name slug; the link's role
    # defaults to its tag (`a`) when the discovery record has no
    # explicit ARIA role.
    names = [p.name for p in saved]
    assert any("home" in n for n in names)
    assert any("button" in n or "sign-in" in n for n in names)
    assert any("remember-me" in n for n in names)
    assert ctrl.state.last_saved == written


def test_take_screenshots_respects_filter(tmp_path: Path) -> None:
    backend = _backend_with_frame()
    saved_paths: list[Path] = []
    ctrl = WebAutoController(
        project_dir=tmp_path,
        backend=backend,
        asset_writer=lambda p, _i: (p.write_bytes(b"x") or p) and saved_paths.append(p) or p,
    )
    ctrl.start("https://example.com")
    # Drop everything except buttons.
    for k in ElementKind:
        ctrl.set_filter_kind(k, k is ElementKind.BUTTON)
    ctrl.apply_filter()
    saved = ctrl.take_screenshots()
    assert len(saved) == 1


def test_close_resets_state_and_closes_backend(tmp_path: Path) -> None:
    backend = _backend_with_frame()
    ctrl = WebAutoController(project_dir=tmp_path, backend=backend)
    ctrl.start("https://example.com")
    ctrl.close()
    assert backend.closed
    assert not ctrl.state.active
    assert ctrl.state.url is None


def test_start_records_error_on_backend_failure(tmp_path: Path) -> None:
    class _Boom:
        def launch(self, *, headed=True): pass
        def goto(self, url, *, timeout_ms=30000): raise RuntimeError("nope")
        def screenshot(self, target): return target
        def frame(self): return None
        def discover(self): return None
        def close(self): pass

    ctrl = WebAutoController(project_dir=tmp_path, backend=_Boom())
    ctrl.start("https://example.com")
    assert ctrl.state.error == "nope"
    assert "Failed to load" in ctrl.state.status
