"""Phase 11 — _WebSurface + codegen + workflow integration."""

from __future__ import annotations

import pytest

from sikulipy.ide.recorder.codegen import GenInput, PythonGenerator
from sikulipy.ide.recorder.surface import _WebSurface
from sikulipy.ide.recorder.workflow import RecorderAction
from sikulipy.web import _FakeBackend


def test_web_surface_header() -> None:
    surf = _WebSurface(url="https://example.com/login")
    assert surf.name == "web"
    assert "from sikulipy.web.screen import WebScreen" in surf.header_imports()
    assert surf.header_setup() == [
        'screen = WebScreen.start(url="https://example.com/login")'
    ]


def test_web_surface_escapes_quotes_in_url() -> None:
    surf = _WebSurface(url='https://x.test/?q="weird"')
    line = surf.header_setup()[0]
    # Outer double quotes survive intact and inner ones are escaped.
    assert line.startswith('screen = WebScreen.start(url="')
    assert line.endswith('")')
    assert '\\"weird\\"' in line


def test_web_surface_uses_fake_backend_bounds() -> None:
    backend = _FakeBackend(document_size=(1280, 4000))
    surf = _WebSurface(url="https://example.com", backend=backend)
    assert surf.bounds() == (0, 0, 1280, 4000)


def test_codegen_web_click() -> None:
    gen = PythonGenerator()
    src = gen.generate(
        RecorderAction.CLICK,
        GenInput(pattern="login.png", surface="web"),
    )
    assert src == 'screen.click(Pattern("login.png"))'


def test_codegen_web_navigate_and_reload() -> None:
    gen = PythonGenerator()
    nav = gen.generate(
        RecorderAction.NAVIGATE,
        GenInput(payload="https://x.test/login", surface="web"),
    )
    reload_ = gen.generate(RecorderAction.RELOAD, GenInput(surface="web"))
    back = gen.generate(RecorderAction.GO_BACK, GenInput(surface="web"))
    forward = gen.generate(RecorderAction.GO_FORWARD, GenInput(surface="web"))
    assert nav == 'screen.navigate("https://x.test/login")'
    assert reload_ == "screen.reload()"
    assert back == "screen.go_back()"
    assert forward == "screen.go_forward()"


def test_codegen_web_right_click_allowed() -> None:
    gen = PythonGenerator()
    src = gen.generate(
        RecorderAction.RCLICK,
        GenInput(pattern="menu.png", surface="web"),
    )
    assert src == 'screen.right_click(Pattern("menu.png"))'


def test_codegen_web_rejects_android_only() -> None:
    gen = PythonGenerator()
    with pytest.raises(ValueError):
        gen.generate(RecorderAction.BACK, GenInput(surface="web"))
    with pytest.raises(ValueError):
        gen.generate(RecorderAction.HOME, GenInput(surface="web"))


def test_codegen_desktop_rejects_web_only() -> None:
    gen = PythonGenerator()
    with pytest.raises(ValueError):
        gen.generate(
            RecorderAction.NAVIGATE,
            GenInput(payload="https://x.test", surface="desktop"),
        )


def test_applies_on_matrix() -> None:
    # Web-only verbs reject on desktop / android.
    for verb in (
        RecorderAction.NAVIGATE,
        RecorderAction.RELOAD,
        RecorderAction.GO_BACK,
        RecorderAction.GO_FORWARD,
    ):
        assert verb.applies_on("web")
        assert not verb.applies_on("desktop")
        assert not verb.applies_on("android")
    # Desktop-only verbs (LAUNCH_APP) reject on web too.
    assert not RecorderAction.LAUNCH_APP.applies_on("web")
    # Right-click works on desktop and web, not android.
    assert RecorderAction.RCLICK.applies_on("web")
    assert RecorderAction.RCLICK.applies_on("desktop")
    assert not RecorderAction.RCLICK.applies_on("android")
