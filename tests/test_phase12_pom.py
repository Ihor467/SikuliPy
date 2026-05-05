"""Phase 12 — Page Object base + locator resolution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

np = pytest.importorskip("numpy")

from sikulipy.ocr import set_ocr
from sikulipy.testing.pom import (
    ImageLocator,
    LocatorDriftError,
    LocatorWarning,
    WebPageObject,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


def _solid(h: int, w: int, color: tuple[int, int, int]):
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:] = color
    return img


@dataclass
class FakeScreen:
    """Records calls so tests can assert what the POM dispatched."""

    crop: Any = None  # ndarray returned by capture_match
    selector_crop: Any = None  # ndarray returned by capture_selector
    fail_find_with: Exception | None = None
    clicks: list[Any] = field(default_factory=list)
    double_clicks: list[Any] = field(default_factory=list)
    hovers: list[Any] = field(default_factory=list)
    typed: list[str] = field(default_factory=list)
    selector_calls: list[str] = field(default_factory=list)

    def find(self, pattern):
        if self.fail_find_with is not None:
            raise self.fail_find_with
        return ("match", pattern)

    def capture_match(self, match):
        return self.crop

    def capture_selector(self, selector: str):
        self.selector_calls.append(selector)
        return self.selector_crop

    def click(self, target):
        self.clicks.append(target)

    def double_click(self, target):
        self.double_clicks.append(target)

    def hover(self, target):
        self.hovers.append(target)

    def type(self, text: str):
        self.typed.append(text)


@dataclass
class FakeOcrBackend:
    text: str

    def read(self, image) -> str:
        return self.text

    def read_words(self, image):
        return []


# ---------------------------------------------------------------------------
# Fixture: a Page Object subclass with two locators, plus written baselines.
# ---------------------------------------------------------------------------


class _LoginPage(WebPageObject):
    URL = "https://example.com"
    LOGIN_BTN = ImageLocator("login_btn.png", selector="#login")
    WELCOME = ImageLocator(
        "welcome_banner.png", text="Welcome, alice", mode="exact"
    )


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def page(project: Path):
    screen = FakeScreen(crop=_solid(20, 30, (10, 20, 30)))
    page = _LoginPage(screen=screen, project_dir=project)
    page.baselines.write("login_btn.png", _solid(20, 30, (10, 20, 30)))
    page.baselines.write("welcome_banner.png", _solid(20, 30, (10, 20, 30)))
    return page


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


def test_click_dispatches_pattern_to_screen(page) -> None:
    page.click(_LoginPage.LOGIN_BTN)
    assert len(page.screen.clicks) == 1


def test_double_click_dispatches(page) -> None:
    page.double_click(_LoginPage.LOGIN_BTN)
    assert len(page.screen.double_clicks) == 1


def test_hover_dispatches(page) -> None:
    page.hover(_LoginPage.LOGIN_BTN)
    assert len(page.screen.hovers) == 1


def test_type_clicks_first_then_types(page) -> None:
    page.type(_LoginPage.LOGIN_BTN, "alice")
    assert len(page.screen.clicks) == 1
    assert page.screen.typed == ["alice"]


# ---------------------------------------------------------------------------
# expect_visual
# ---------------------------------------------------------------------------


def test_expect_visual_passes_when_baseline_matches(page) -> None:
    diff = page.expect_visual(_LoginPage.LOGIN_BTN, threshold=0.0)
    assert diff.passed


def test_expect_visual_raises_on_mismatch(project: Path) -> None:
    screen = FakeScreen(crop=_solid(20, 30, (200, 200, 200)))
    page = _LoginPage(screen=screen, project_dir=project)
    page.baselines.write("login_btn.png", _solid(20, 30, (0, 0, 0)))
    with pytest.raises(AssertionError, match="visual diff failed"):
        page.expect_visual(_LoginPage.LOGIN_BTN, threshold=0.001)


def test_expect_visual_missing_baseline_raises(project: Path) -> None:
    screen = FakeScreen(crop=_solid(20, 30, (0, 0, 0)))
    page = _LoginPage(screen=screen, project_dir=project)
    with pytest.raises(FileNotFoundError, match="--update-baselines"):
        page.expect_visual(_LoginPage.LOGIN_BTN)


# ---------------------------------------------------------------------------
# expect_text
# ---------------------------------------------------------------------------


def test_expect_text_uses_locator_default(page) -> None:
    set_ocr(FakeOcrBackend("Welcome, alice"))
    try:
        diff = page.expect_text(_LoginPage.WELCOME)
        assert diff.passed
    finally:
        set_ocr(None)


def test_expect_text_explicit_override_wins(page) -> None:
    set_ocr(FakeOcrBackend("Goodbye, bob"))
    try:
        diff = page.expect_text(_LoginPage.WELCOME, expected="Goodbye, bob")
        assert diff.passed
    finally:
        set_ocr(None)


def test_expect_text_fails_below_threshold(page) -> None:
    set_ocr(FakeOcrBackend("totally different"))
    try:
        with pytest.raises(AssertionError, match="text diff failed"):
            page.expect_text(_LoginPage.WELCOME)
    finally:
        set_ocr(None)


def test_expect_text_locator_with_no_text_and_no_arg_raises(page) -> None:
    with pytest.raises(ValueError, match="no text"):
        page.expect_text(_LoginPage.LOGIN_BTN)


# ---------------------------------------------------------------------------
# Selector fallback
# ---------------------------------------------------------------------------


def test_image_find_failure_falls_back_to_selector(project: Path) -> None:
    screen = FakeScreen(
        fail_find_with=RuntimeError("image not found"),
        selector_crop=_solid(20, 30, (10, 20, 30)),
    )
    page = _LoginPage(screen=screen, project_dir=project)
    page.baselines.write("login_btn.png", _solid(20, 30, (10, 20, 30)))
    diff = page.expect_visual(_LoginPage.LOGIN_BTN, threshold=0.0)
    assert diff.passed
    assert screen.selector_calls == ["#login"]
    assert any(
        isinstance(w, LocatorWarning) and "image find failed" in w.reason
        for w in page.warnings
    )


def test_image_find_failure_without_selector_raises(project: Path) -> None:
    no_selector = ImageLocator("welcome_banner.png", selector=None)

    class _Page(WebPageObject):
        URL = "https://example.com"
        WELCOME = no_selector

    screen = FakeScreen(fail_find_with=RuntimeError("nope"))
    page = _Page(screen=screen, project_dir=project)
    page.baselines.write("welcome_banner.png", _solid(10, 10, (0, 0, 0)))
    with pytest.raises(LocatorDriftError):
        page.expect_visual(no_selector)


def test_host_inferred_from_url() -> None:
    class _Page(WebPageObject):
        URL = "https://shop.example.com/path?x=1"

    page = _Page(screen=object(), project_dir=Path("/tmp/x"))
    assert page.host == "shop.example.com"
