"""Phase 11 — element filter."""

from __future__ import annotations

from sikulipy.web import ElementFilter, ElementKind, WebElement


def _el(kind: ElementKind, w: float = 50, h: float = 30, name: str = "x") -> WebElement:
    return WebElement(
        kind=kind,
        role=kind.value,
        name=name,
        selector=f".{kind.value}-{name}",
        xpath="/html",
        bounds=(0, 0, w, h),
        tag="div",
    )


def test_default_filter_shows_nothing() -> None:
    elements = [_el(k) for k in ElementKind]
    flt = ElementFilter()
    assert flt.apply(elements) == []


def test_filter_drops_disabled_kinds() -> None:
    elements = [_el(ElementKind.LINK), _el(ElementKind.BUTTON), _el(ElementKind.INPUT)]
    flt = ElementFilter()
    flt.enable(ElementKind.LINK)
    flt.enable(ElementKind.INPUT)
    out = flt.apply(elements)
    assert {e.kind for e in out} == {ElementKind.LINK, ElementKind.INPUT}


def test_filter_toggle_round_trip() -> None:
    flt = ElementFilter()
    flt.toggle(ElementKind.MENU, True)
    assert flt.is_enabled(ElementKind.MENU)
    flt.toggle(ElementKind.MENU, False)
    assert not flt.is_enabled(ElementKind.MENU)


def test_filter_drops_invisible_elements() -> None:
    elements = [
        _el(ElementKind.BUTTON, w=10, h=10),
        _el(ElementKind.BUTTON, w=0, h=0, name="hidden"),
    ]
    flt = ElementFilter()
    flt.enable(ElementKind.BUTTON)
    out = flt.apply(elements)
    assert len(out) == 1
    assert out[0].name == "x"


def test_filter_apply_preserves_order() -> None:
    elements = [
        _el(ElementKind.LINK, name="a"),
        _el(ElementKind.LINK, name="b"),
        _el(ElementKind.LINK, name="c"),
    ]
    flt = ElementFilter()
    flt.enable(ElementKind.LINK)
    out = flt.apply(elements)
    assert [e.name for e in out] == ["a", "b", "c"]
