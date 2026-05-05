"""Phase 12 — POM codegen.

Validates that synthetic recorder sessions produce parseable Page
Object + test modules. We don't care about exact whitespace — only
that the rendered code imports, names the right symbols, and names
the right method calls.
"""

from __future__ import annotations

import pytest

from sikulipy.ide.recorder.pom_codegen import (
    PomLocator,
    PomScenario,
    PomStep,
    class_name,
    locators_from_assets,
    module_slug,
    render_page_object,
    render_test_module,
    steps_from_records,
    upper_snake,
    validate_python_source,
)
from sikulipy.ide.recorder.workflow import RecorderAction


# ---------------------------- Naming -----------------------------------------


@pytest.mark.parametrize(
    "asset,expected",
    [
        ("login_btn.png", "LOGIN_BTN"),
        ("login-btn.png", "LOGIN_BTN"),
        ("123-go.png", "E_123_GO"),
        ("class.png", "CLASS_"),
        ("welcome banner.png", "WELCOME_BANNER"),
    ],
)
def test_upper_snake_handles_punctuation_and_keywords(asset, expected) -> None:
    assert upper_snake(asset) == expected


def test_class_name_camelcases_host() -> None:
    assert class_name("shop.example.com") == "ShopExampleCom"
    assert class_name("example") == "Example"


def test_module_slug_is_python_safe() -> None:
    assert module_slug("shop.example.com") == "shop_example_com"
    assert module_slug("123foo") == "p_123foo"


def test_locators_from_assets_dedupes() -> None:
    locs = locators_from_assets([
        ("login.png", None, None),
        ("login.png", "#login", "Login"),
        ("submit.png", None, None),
    ])
    assert [l.name for l in locs] == ["LOGIN", "LOGIN_2", "SUBMIT"]
    assert locs[1].selector == "#login"
    assert locs[1].text == "Login"


# ---------------------------- Page Object render -----------------------------


def _scenario_with_login_flow() -> PomScenario:
    locators = locators_from_assets([
        ("username_field.png", "#username", None),
        ("password_field.png", "#password", None),
        ("login_btn.png", "button[type=submit]", None),
        ("welcome_banner.png", None, "Welcome, alice"),
    ])
    asset_to_loc = {l.asset: l.name for l in locators}
    steps = steps_from_records(
        [
            (RecorderAction.TYPE, "username_field.png", "alice"),
            (RecorderAction.TYPE, "password_field.png", "hunter2"),
            (RecorderAction.CLICK, "login_btn.png", None),
        ],
        asset_to_locator=asset_to_loc,
    )
    return PomScenario(
        host="example.com",
        url="https://example.com",
        scenario="login_happy_path",
        locators=locators,
        steps=steps,
    )


def test_page_object_imports_and_declares_locators() -> None:
    src = render_page_object(_scenario_with_login_flow())
    validate_python_source(src)
    assert "from sikulipy.testing.pom import ImageLocator, WebPageObject" in src
    assert "class ExampleCom(WebPageObject):" in src
    assert "URL = 'https://example.com'" in src
    assert (
        'USERNAME_FIELD = ImageLocator(\'username_field.png\', '
        "selector='#username')" in src
    )
    assert (
        'WELCOME_BANNER = ImageLocator(\'welcome_banner.png\', '
        "text='Welcome, alice')" in src
    )


def test_page_object_emits_action_methods_for_each_step() -> None:
    src = render_page_object(_scenario_with_login_flow())
    assert "def type_into_username_field(self) -> None:" in src
    assert "self.type(self.USERNAME_FIELD, 'alice')" in src
    assert "def click_login_btn(self) -> None:" in src
    assert "self.click(self.LOGIN_BTN)" in src


def test_page_object_with_no_steps_has_pass_body() -> None:
    src = render_page_object(
        PomScenario(host="x.com", url="https://x.com", scenario="empty")
    )
    validate_python_source(src)
    assert "    pass" in src


# ---------------------------- Test module render -----------------------------


def test_test_module_imports_page_class_and_calls_methods() -> None:
    src = render_test_module(_scenario_with_login_flow())
    validate_python_source(src)
    assert "from pages.example_com import ExampleCom" in src
    assert "def test_login_happy_path(page: ExampleCom) -> None:" in src
    assert "page.type_into_username_field()" in src
    assert "page.click_login_btn()" in src


def test_test_module_appends_visual_assertions() -> None:
    src = render_test_module(_scenario_with_login_flow())
    assert "page.expect_visual(ExampleCom.LOGIN_BTN)" in src
    assert "page.expect_visual(ExampleCom.WELCOME_BANNER)" in src
    # Locator with text gets a follow-up text assertion.
    assert "page.expect_text(ExampleCom.WELCOME_BANNER)" in src


def test_test_module_with_empty_steps_emits_pass() -> None:
    src = render_test_module(
        PomScenario(host="x.com", url="https://x.com", scenario="empty")
    )
    validate_python_source(src)
    assert "    pass\n" in src


def test_test_module_handles_navigation_steps() -> None:
    scenario = PomScenario(
        host="example.com",
        url="https://example.com",
        scenario="reload_then_back",
        locators=[],
        steps=[
            PomStep(action=RecorderAction.RELOAD),
            PomStep(action=RecorderAction.GO_BACK),
        ],
    )
    src = render_test_module(scenario)
    validate_python_source(src)
    assert "page.reload_0()" in src
    assert "page.go_back_1()" in src
