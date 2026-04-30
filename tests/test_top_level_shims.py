"""``from sikulipy import *`` exposes Screen-method shims as bare names.

SikuliX scripts use ``exists(Pattern("ok.png"))`` / ``click(...)`` /
``wait(...)`` without explicitly instantiating a Screen. The Java IDE
auto-binds those to the primary screen; we mirror the trick by
generating top-level proxy functions in ``sikulipy/__init__.py`` that
delegate to a cached primary :class:`Screen`.

These tests don't need a real framebuffer — we substitute a fake into
the lazy slot before the proxies dereference it.
"""

from __future__ import annotations

import sikulipy


class _FakeScreen:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def exists(self, target, timeout: float = 0.0):
        self.calls.append(("exists", target, timeout))
        return None

    def click(self, target=None):
        self.calls.append(("click", target))
        return 1

    def wait(self, target, timeout: float = 3.0):
        self.calls.append(("wait", target, timeout))
        return "match"


def _install_fake() -> _FakeScreen:
    """Drop a fake into the primary-screen cache slot."""
    fake = _FakeScreen()
    # _PRIMARY_SCREEN is the module-level cache the proxy reads.
    sikulipy._PRIMARY_SCREEN = fake  # type: ignore[attr-defined]
    return fake


def _uninstall_fake() -> None:
    sikulipy.__dict__.pop("_PRIMARY_SCREEN", None)


def test_top_level_exists_delegates_to_primary_screen() -> None:
    fake = _install_fake()
    try:
        result = sikulipy.exists("needle.png")
    finally:
        _uninstall_fake()
    assert result is None
    assert fake.calls == [("exists", "needle.png", 0.0)]


def test_top_level_click_returns_screen_click_result() -> None:
    fake = _install_fake()
    try:
        rv = sikulipy.click("ok.png")
    finally:
        _uninstall_fake()
    assert rv == 1
    assert fake.calls == [("click", "ok.png")]


def test_star_import_publishes_screen_method_shims() -> None:
    """``from sikulipy import *`` brings the proxy functions in scope."""
    ns: dict = {}
    exec("from sikulipy import *", ns)  # noqa: S102 — controlled namespace
    # Spot-check the names every recorded script tends to use.
    for name in ("exists", "click", "wait", "find", "Pattern", "Region"):
        assert name in ns, f"{name} missing from star import"


def test_proxy_carries_useful_metadata() -> None:
    """Tracebacks and help() should show meaningful names."""
    assert sikulipy.exists.__name__ == "exists"
    assert sikulipy.exists.__qualname__ == "sikulipy.exists"
    assert "Screen()" in (sikulipy.exists.__doc__ or "")
