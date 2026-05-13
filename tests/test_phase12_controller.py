"""Phase 12 — WebAutoController.generate_tests integration."""

from __future__ import annotations

from pathlib import Path

import pytest

from sikulipy.ide.recorder.workflow import RecorderAction
from sikulipy.ide.web_panel import WebAutoController
from sikulipy.web import ElementKind, _FakeBackend
from sikulipy.web.assets import slug_for_element

np = pytest.importorskip("numpy")


_ELEMENTS = [
    {
        "tag": "input",
        "type": "text",
        "role": "",
        "name": "Username",
        "selector": "#username",
        "xpath": "//input[1]",
        "bounds": [10, 10, 200, 30],
    },
    {
        "tag": "input",
        "type": "password",
        "role": "",
        "name": "Password",
        "selector": "#password",
        "xpath": "//input[2]",
        "bounds": [10, 50, 200, 30],
    },
    {
        "tag": "button",
        "type": "submit",
        "role": "",
        "name": "Sign in",
        "selector": "button[type=submit]",
        "xpath": "//button[1]",
        "bounds": [10, 100, 80, 36],
    },
]


def _backend():
    frame = np.zeros((600, 800, 3), dtype=np.uint8)
    return _FakeBackend(
        elements_payload=_ELEMENTS,
        device_pixel_ratio=1.0,
        document_size=(800, 600),
        frame_factory=lambda: frame,
    )


def _start_with_filter(tmp_path: Path) -> WebAutoController:
    ctrl = WebAutoController(
        project_dir=tmp_path,
        backend=_backend(),
        asset_writer=lambda p, _i: (p.parent.mkdir(parents=True, exist_ok=True),
                                    p.write_bytes(b"fake-png"),
                                    p)[-1],
    )
    ctrl.start("https://example.com/login")
    for k in (ElementKind.INPUT, ElementKind.BUTTON):
        ctrl.set_filter_kind(k, True)
    ctrl.apply_filter()
    ctrl.take_screenshots()
    return ctrl


def test_generate_tests_writes_page_and_test_modules(tmp_path: Path) -> None:
    ctrl = _start_with_filter(tmp_path)
    elements = ctrl.state.filtered()
    asset_for = {el.name: f"{slug_for_element(el)}.png" for el in elements}
    records = [
        (RecorderAction.TYPE, asset_for["Username"], "alice"),
        (RecorderAction.TYPE, asset_for["Password"], "hunter2"),
        (RecorderAction.CLICK, asset_for["Sign in"], None),
    ]

    out = ctrl.generate_tests("login_happy_path", records=records)

    assert out.page_object == tmp_path / "pages" / "example_com.py"
    assert out.test_module == tmp_path / "tests" / "web" / "test_login_happy_path.py"
    assert out.page_object.is_file()
    assert out.test_module.is_file()

    page_src = out.page_object.read_text()
    assert "class ExampleCom(WebPageObject):" in page_src
    assert "URL = 'https://example.com/login'" in page_src
    # Each filtered element gets a locator.
    assert page_src.count("ImageLocator(") == 3

    test_src = out.test_module.read_text()
    assert "from pages.example_com import ExampleCom" in test_src
    assert "def test_login_happy_path(page: ExampleCom) -> None:" in test_src
    # Three recorded actions → three method calls.
    assert test_src.count("page.") >= 3


def test_generate_tests_seeds_baselines_from_assets(tmp_path: Path) -> None:
    ctrl = _start_with_filter(tmp_path)
    out = ctrl.generate_tests("smoke")
    baseline_dir = tmp_path / "baselines" / "web" / "example.com"
    assert baseline_dir.is_dir()
    seeded_names = {p.name for p in out.baselines}
    assert len(seeded_names) == 3
    for name in seeded_names:
        assert (baseline_dir / name).is_file()
    # Metadata sidecar gets written too.
    assert (baseline_dir / ".metadata.json").is_file()


def test_generate_tests_auto_captures_missing_assets(tmp_path: Path) -> None:
    # Build a controller exactly like _start_with_filter but skip the
    # take_screenshots() call — simulates the user clicking Generate
    # without first clicking Take ElScrsht.
    ctrl = WebAutoController(
        project_dir=tmp_path,
        backend=_backend(),
        asset_writer=lambda p, _i: (
            p.parent.mkdir(parents=True, exist_ok=True),
            p.write_bytes(b"fake-png"),
            p,
        )[-1],
    )
    ctrl.start("https://example.com/login")
    for k in (ElementKind.INPUT, ElementKind.BUTTON):
        ctrl.set_filter_kind(k, True)
    ctrl.apply_filter()
    # Sanity: no assets on disk yet.
    asset_dir = ctrl.state.asset_dir
    assert asset_dir is not None and not any(asset_dir.glob("*.png"))

    out = ctrl.generate_tests("smoke")

    # All three baselines should land even though Take ElScrsht was
    # never called — generate_tests auto-captured the missing PNGs.
    assert len(out.baselines) == 3
    baseline_dir = tmp_path / "baselines" / "web" / "example.com"
    for b in out.baselines:
        assert (baseline_dir / b.name).is_file()


def test_generate_tests_refuses_to_clobber(tmp_path: Path) -> None:
    ctrl = _start_with_filter(tmp_path)
    ctrl.generate_tests("smoke")
    with pytest.raises(FileExistsError, match="force=True"):
        ctrl.generate_tests("smoke")


def test_generate_tests_force_overwrites(tmp_path: Path) -> None:
    ctrl = _start_with_filter(tmp_path)
    out = ctrl.generate_tests("smoke")
    out.test_module.write_text("# stale\n", encoding="utf-8")
    out2 = ctrl.generate_tests("smoke", force=True)
    assert "# stale" not in out2.test_module.read_text()


def test_generate_tests_creates_pages_package_init(tmp_path: Path) -> None:
    ctrl = _start_with_filter(tmp_path)
    ctrl.generate_tests("smoke")
    assert (tmp_path / "pages" / "__init__.py").is_file()


def test_generate_tests_requires_active_session(tmp_path: Path) -> None:
    ctrl = WebAutoController(project_dir=tmp_path, backend=_backend())
    with pytest.raises(RuntimeError, match="not active"):
        ctrl.generate_tests("smoke")


def test_generate_tests_requires_filtered_elements(tmp_path: Path) -> None:
    ctrl = WebAutoController(project_dir=tmp_path, backend=_backend())
    ctrl.start("https://example.com/login")
    # No filter applied → filtered() is empty.
    with pytest.raises(RuntimeError, match="filter"):
        ctrl.generate_tests("smoke")


def test_generate_tests_handles_empty_records(tmp_path: Path) -> None:
    ctrl = _start_with_filter(tmp_path)
    out = ctrl.generate_tests("just_baselines")
    test_src = out.test_module.read_text()
    # No CLICK / TYPE recorded → test body falls back to ``pass``.
    # Page object still ships locators for every filtered element.
    assert "def test_just_baselines(page: ExampleCom) -> None:" in test_src
    page_src = out.page_object.read_text()
    assert page_src.count("ImageLocator(") == 3


def test_generate_tests_status_message_summarises(tmp_path: Path) -> None:
    ctrl = _start_with_filter(tmp_path)
    ctrl.generate_tests("smoke")
    assert "baselines seeded" in ctrl.state.status


def test_set_included_excludes_element_from_generated_tests(tmp_path: Path) -> None:
    ctrl = _start_with_filter(tmp_path)
    elements = ctrl.state.filtered()
    # Drop the password input from the test.
    pwd = next(e for e in elements if e.name == "Password")
    ctrl.set_included(pwd, False)
    out = ctrl.generate_tests("partial")
    page_src = out.page_object.read_text()
    # Two locators left (Username + Sign in), not three.
    assert page_src.count("ImageLocator(") == 2
    assert "PASSWORD" not in page_src.upper().replace("E_PASSWORD", "")


def test_apply_filter_auto_includes_small_sets(tmp_path: Path) -> None:
    ctrl = _start_with_filter(tmp_path)
    # Three filtered elements — well under the threshold, all opt-in.
    assert len(ctrl.state.filtered()) == 3
    assert len(ctrl.state.included()) == 3


def test_apply_filter_auto_excludes_large_sets(tmp_path: Path) -> None:
    from sikulipy.ide.web_panel import AUTO_INCLUDE_THRESHOLD
    from sikulipy.web import ElementKind, _FakeBackend

    big_payload = [
        {
            "tag": "a",
            "type": "",
            "role": "",
            "name": f"link-{i}",
            "selector": f"a#l{i}",
            "xpath": f"//a[{i}]",
            "bounds": [10, 10 + i * 30, 80, 24],
        }
        for i in range(AUTO_INCLUDE_THRESHOLD + 5)
    ]
    backend = _FakeBackend(
        elements_payload=big_payload,
        device_pixel_ratio=1.0,
        document_size=(800, 600),
        frame_factory=lambda: np.zeros((600, 800, 3), dtype=np.uint8),
    )
    ctrl = WebAutoController(project_dir=tmp_path, backend=backend)
    ctrl.start("https://example.com")
    ctrl.set_filter_kind(ElementKind.LINK, True)
    ctrl.apply_filter()
    assert len(ctrl.state.filtered()) > AUTO_INCLUDE_THRESHOLD
    # Above the threshold → nothing auto-selected.
    assert ctrl.state.included() == []


def test_apply_filter_at_threshold_includes_all(tmp_path: Path) -> None:
    from sikulipy.ide.web_panel import AUTO_INCLUDE_THRESHOLD
    from sikulipy.web import ElementKind, _FakeBackend

    payload = [
        {
            "tag": "a",
            "type": "",
            "role": "",
            "name": f"link-{i}",
            "selector": f"a#l{i}",
            "xpath": f"//a[{i}]",
            "bounds": [10, 10 + i * 30, 80, 24],
        }
        for i in range(AUTO_INCLUDE_THRESHOLD)
    ]
    backend = _FakeBackend(
        elements_payload=payload,
        device_pixel_ratio=1.0,
        document_size=(800, 600),
        frame_factory=lambda: np.zeros((600, 800, 3), dtype=np.uint8),
    )
    ctrl = WebAutoController(project_dir=tmp_path, backend=backend)
    ctrl.start("https://example.com")
    ctrl.set_filter_kind(ElementKind.LINK, True)
    ctrl.apply_filter()
    assert len(ctrl.state.included()) == AUTO_INCLUDE_THRESHOLD


def test_set_all_included_bulk_toggle(tmp_path: Path) -> None:
    ctrl = _start_with_filter(tmp_path)
    ctrl.set_all_included(False)
    assert ctrl.state.included() == []
    ctrl.set_all_included(True)
    assert len(ctrl.state.included()) == len(ctrl.state.filtered())


def test_take_screenshots_respects_inclusion(tmp_path: Path) -> None:
    ctrl = _start_with_filter(tmp_path)
    el = next(e for e in ctrl.state.filtered() if e.name == "Sign in")
    ctrl.set_included(el, False)
    saved = ctrl.take_screenshots()
    assert len(saved) == 2  # was 3 before exclusion


def test_generate_tests_seeds_conftest_once(tmp_path: Path) -> None:
    ctrl = _start_with_filter(tmp_path)
    ctrl.generate_tests("smoke")
    conftest = tmp_path / "tests" / "web" / "conftest.py"
    assert conftest.is_file()
    assert "--update-baselines" in conftest.read_text()
    # User-owned after creation: re-running with force does not clobber
    # local edits.
    conftest.write_text("# my edits\n", encoding="utf-8")
    ctrl.generate_tests("smoke", force=True)
    assert conftest.read_text() == "# my edits\n"
