"""Phase 11 — _FakeBackend round-trip and discovery payload mapping."""

from __future__ import annotations

from pathlib import Path

import pytest

from sikulipy.web import ElementKind, _FakeBackend, get_backend, set_backend
from sikulipy.web._backend import DiscoveryResult, reset_backend
from sikulipy.web.elements import classify, from_record


@pytest.fixture(autouse=True)
def _reset():
    reset_backend()
    yield
    reset_backend()


def test_fake_backend_round_trip(tmp_path: Path) -> None:
    backend = _FakeBackend(
        elements_payload=[
            {
                "tag": "a",
                "type": "",
                "role": "",
                "name": "Sign in",
                "selector": "a#signin",
                "xpath": "//*[@id='signin']",
                "bounds": [10, 20, 80, 30],
            },
            {
                "tag": "button",
                "type": "submit",
                "role": "",
                "name": "Submit",
                "selector": "button[type='submit']",
                "xpath": "/html/body/form/button[1]",
                "bounds": [100, 200, 90, 36],
            },
        ],
        device_pixel_ratio=2.0,
        document_size=(1280, 2400),
    )
    backend.launch()
    backend.goto("https://example.com")
    shot = backend.screenshot(tmp_path / "shot.png")
    assert shot.exists()
    result = backend.discover()
    backend.close()

    assert isinstance(result, DiscoveryResult)
    assert result.device_pixel_ratio == 2.0
    assert result.document_size == (1280, 2400)
    assert len(result.elements) == 2
    link, button = result.elements
    assert link.kind is ElementKind.LINK
    assert link.name == "Sign in"
    assert link.bounds == (10.0, 20.0, 80.0, 30.0)
    assert button.kind is ElementKind.BUTTON
    assert button.tag == "button"
    assert backend.closed
    assert backend.calls[0][0] == "launch"
    assert backend.calls[-1][0] == "close"


def test_classify_covers_every_kind() -> None:
    cases = [
        (("a", "", ""), ElementKind.LINK),
        (("a", "", "button"), ElementKind.BUTTON),
        (("button", "", ""), ElementKind.BUTTON),
        (("input", "submit", ""), ElementKind.BUTTON),
        (("input", "checkbox", ""), ElementKind.CHECKBOX_RADIO),
        (("div", "", "switch"), ElementKind.CHECKBOX_RADIO),
        (("select", "", ""), ElementKind.SELECT),
        (("div", "", "combobox"), ElementKind.SELECT),
        (("textarea", "", ""), ElementKind.INPUT),
        (("input", "text", ""), ElementKind.INPUT),
        (("input", "email", ""), ElementKind.INPUT),
        (("div", "", "tab"), ElementKind.TAB),
        (("div", "", "menuitem"), ElementKind.MENU),
        (("summary", "", ""), ElementKind.MENU),
        (("div", "", ""), ElementKind.OTHER),
    ]
    for (tag, type_attr, role), expected in cases:
        assert classify(tag, type_attr, role) is expected, (tag, type_attr, role)


def test_from_record_handles_missing_fields() -> None:
    el = from_record({"tag": "a", "name": "Home"})
    assert el.kind is ElementKind.LINK
    assert el.bounds == (0.0, 0.0, 0.0, 0.0)
    assert el.selector == ""
    # No name → display_name falls back to selector slice.
    assert from_record({"tag": "div", "selector": "div.foo"}).display_name == "div.foo"


def test_get_backend_singleton_and_set_backend() -> None:
    fake = _FakeBackend()
    set_backend(fake)
    assert get_backend() is fake
    # set_backend swaps cleanly, including back to None via reset.
    other = _FakeBackend()
    set_backend(other)
    assert get_backend() is other


def test_discover_payload_visible_filter() -> None:
    """Tests at the from_record level handle visibility off the page."""
    rec_visible = {"tag": "button", "name": "Go", "bounds": [0, 0, 50, 30]}
    rec_hidden = {"tag": "button", "name": "Hidden", "bounds": [0, 0, 0, 0]}
    assert from_record(rec_visible).visible
    assert not from_record(rec_hidden).visible
