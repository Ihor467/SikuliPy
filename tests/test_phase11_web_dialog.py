"""Phase 11 — URL prompt validation."""

from __future__ import annotations

from sikulipy.ide.web_dialog import WebAutoDialog


def test_accepts_full_https_url() -> None:
    d = WebAutoDialog()
    d.set_text("https://example.com/login")
    assert d.normalize() == "https://example.com/login"
    assert d.error is None


def test_upgrades_bare_host_to_https() -> None:
    d = WebAutoDialog()
    d.set_text("example.com/x")
    assert d.normalize() == "https://example.com/x"


def test_rejects_empty() -> None:
    d = WebAutoDialog()
    d.set_text("")
    assert d.normalize() is None
    assert d.error == "URL is required"


def test_rejects_unsupported_scheme() -> None:
    d = WebAutoDialog()
    d.set_text("javascript:alert(1)")
    assert d.normalize() is None
    assert "scheme" in (d.error or "")


def test_rejects_data_url() -> None:
    d = WebAutoDialog()
    d.set_text("data:text/html,<h1>hi</h1>")
    assert d.normalize() is None


def test_rejects_missing_host() -> None:
    d = WebAutoDialog()
    d.set_text("https://")
    assert d.normalize() is None
    assert "hostname" in (d.error or "")


def test_strips_whitespace() -> None:
    d = WebAutoDialog()
    d.set_text("   https://example.com   ")
    assert d.normalize() == "https://example.com"


def test_set_text_clears_prior_error() -> None:
    d = WebAutoDialog()
    d.set_text("javascript:1")
    assert d.normalize() is None
    assert d.error is not None
    d.set_text("https://example.com")
    assert d.error is None
    assert d.normalize() == "https://example.com"
