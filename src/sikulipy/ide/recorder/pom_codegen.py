"""POM-style codegen for Web Auto sessions (Phase 12).

Where :mod:`sikulipy.ide.recorder.codegen` emits one Python statement
per recorded action (an inline script the user pastes into the
editor), this module takes the *whole* session and emits two
hand-edit-safe artefacts:

* a Page Object module — one class per host, with locators for every
  element the user kept in the filtered list, plus action methods
  generated from the recorder's CLICK / TYPE / NAVIGATE timeline;
* a pytest module — one ``test_<scenario>`` per session, calling the
  Page Object's actions in the recorded order with no inline patterns.

Both modules round-trip through :func:`ast.parse` so we know they at
least import cleanly. Caller (the IDE controller) handles the file
I/O and refusing to clobber existing tests.
"""

from __future__ import annotations

import keyword
import re
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from sikulipy.ide.recorder.workflow import RecorderAction


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PomLocator:
    """One catalogue entry for the generated Page Object."""

    name: str  # Python identifier in UPPER_SNAKE_CASE
    asset: str
    selector: str | None = None
    text: str | None = None


@dataclass(frozen=True)
class PomStep:
    """One line in the generated test body.

    ``locator_name`` references a :class:`PomLocator` already in the
    catalogue (action methods only — text/wait/navigate steps that
    don't need a locator carry it as ``None``).
    """

    action: RecorderAction
    locator_name: str | None = None
    payload: str | None = None


@dataclass
class PomScenario:
    """Everything the generator needs to produce one test module."""

    host: str
    url: str
    scenario: str            # human label, e.g. ``"login_happy_path"``
    locators: list[PomLocator] = field(default_factory=list)
    steps: list[PomStep] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Naming helpers
# ---------------------------------------------------------------------------


_NON_IDENT = re.compile(r"[^0-9a-zA-Z_]+")


def upper_snake(name: str) -> str:
    """``login-btn.png`` → ``LOGIN_BTN``; collisions with keywords get a
    trailing underscore."""
    base = name.rsplit(".", 1)[0]
    cleaned = _NON_IDENT.sub("_", base).strip("_").upper()
    if not cleaned:
        cleaned = "ELEMENT"
    if cleaned[0].isdigit():
        cleaned = f"E_{cleaned}"
    if keyword.iskeyword(cleaned.lower()):
        cleaned = f"{cleaned}_"
    return cleaned


def class_name(host: str) -> str:
    """``shop.example.com`` → ``ShopExampleCom``."""
    parts = [p for p in re.split(r"[^0-9a-zA-Z]+", host) if p]
    if not parts:
        return "Page"
    return "".join(p[:1].upper() + p[1:].lower() for p in parts)


def module_slug(name: str) -> str:
    """``shop.example.com`` → ``shop_example_com``."""
    cleaned = _NON_IDENT.sub("_", name).strip("_").lower()
    if not cleaned:
        cleaned = "page"
    if cleaned[0].isdigit():
        cleaned = f"p_{cleaned}"
    return cleaned


# ---------------------------------------------------------------------------
# Code emitters
# ---------------------------------------------------------------------------


_PAGE_HEADER = """\
\"\"\"Auto-generated Page Object for {host}.

Edit by hand if you like — the generator skips locators that already
exist (matched by ``asset``) on the next regeneration. Action methods
named ``do_*`` are appended only when missing.
\"\"\"

from __future__ import annotations

from sikulipy.testing.pom import ImageLocator, WebPageObject


class {cls}(WebPageObject):
    URL = {url!r}

"""


_TEST_HEADER = """\
\"\"\"Auto-generated pytest scenario: {scenario}.\"\"\"

from __future__ import annotations

import pytest

from pages.{page_module} import {cls}


@pytest.fixture
def page(web_screen, project_dir):
    return {cls}(screen=web_screen, project_dir=project_dir)


"""


def render_page_object(scenario: PomScenario) -> str:
    """Emit the Page Object source as one string."""
    cls = class_name(scenario.host)
    out = [_PAGE_HEADER.format(host=scenario.host, cls=cls, url=scenario.url)]

    # Catalogue
    for loc in scenario.locators:
        kwargs = [f"{loc.asset!r}"]
        if loc.selector:
            kwargs.append(f"selector={loc.selector!r}")
        if loc.text:
            kwargs.append(f"text={loc.text!r}")
        out.append(f"    {loc.name} = ImageLocator({', '.join(kwargs)})\n")

    # Action methods — one per recorded step that maps cleanly. Tests
    # call these by name so the generated test module stays readable
    # even when the catalogue grows.
    seen_methods: set[str] = set()
    for i, step in enumerate(scenario.steps):
        method = _method_name_for(step, i)
        if method in seen_methods:
            continue
        seen_methods.add(method)
        body = _method_body(step)
        if body is None:
            continue
        out.append("\n")
        out.append(f"    def {method}(self) -> None:\n")
        for line in body:
            out.append(f"        {line}\n")

    if not scenario.locators and not scenario.steps:
        out.append("    pass\n")

    return "".join(out)


def render_test_module(scenario: PomScenario) -> str:
    cls = class_name(scenario.host)
    page_module = module_slug(scenario.host)
    out = [_TEST_HEADER.format(
        scenario=scenario.scenario,
        page_module=page_module,
        cls=cls,
    )]
    test_name = _safe_test_name(scenario.scenario)
    out.append(f"def {test_name}(page: {cls}) -> None:\n")
    if not scenario.steps:
        out.append("    pass\n")
        return "".join(out)
    seen_methods: set[str] = set()
    for i, step in enumerate(scenario.steps):
        method = _method_name_for(step, i)
        if method in seen_methods:
            # Repeated step (e.g. two clicks on the same button). Emit
            # the call again — methods on the page object are
            # idempotent by design.
            pass
        else:
            seen_methods.add(method)
        out.append(f"    page.{method}()\n")
    # Verify the visible state at the end so the test fails on a UI
    # regression even if every action succeeded.
    visual_locators = [
        loc for loc in scenario.locators if loc.text or _is_visible_only(loc)
    ]
    if visual_locators:
        out.append("    # Visual + (optional) text assertions\n")
        for loc in visual_locators:
            out.append(f"    page.expect_visual({class_name(scenario.host)}.{loc.name})\n")
            if loc.text:
                out.append(
                    f"    page.expect_text({class_name(scenario.host)}.{loc.name})\n"
                )
    return "".join(out)


# ---------------------------------------------------------------------------
# Per-step helpers
# ---------------------------------------------------------------------------


def _method_body(step: PomStep) -> list[str] | None:
    if step.action is RecorderAction.CLICK and step.locator_name:
        return [f"self.click(self.{step.locator_name})"]
    if step.action is RecorderAction.DBLCLICK and step.locator_name:
        return [f"self.double_click(self.{step.locator_name})"]
    if step.action is RecorderAction.TYPE:
        if step.locator_name:
            return [f"self.type(self.{step.locator_name}, {step.payload!r})"]
        return [f"self.screen.type({step.payload!r})"]
    if step.action is RecorderAction.NAVIGATE and step.payload:
        return [f"self.screen.navigate({step.payload!r})"]
    if step.action is RecorderAction.RELOAD:
        return ["self.screen.reload()"]
    if step.action is RecorderAction.GO_BACK:
        return ["self.screen.go_back()"]
    if step.action is RecorderAction.GO_FORWARD:
        return ["self.screen.go_forward()"]
    if step.action is RecorderAction.PAUSE and step.payload:
        return ["import time", f"time.sleep({float(step.payload):g})"]
    return None


def _method_name_for(step: PomStep, idx: int) -> str:
    """Stable, readable identifier for the auto-generated method."""
    verb = {
        RecorderAction.CLICK: "click",
        RecorderAction.DBLCLICK: "double_click",
        RecorderAction.TYPE: "type_into",
        RecorderAction.NAVIGATE: "navigate",
        RecorderAction.RELOAD: "reload",
        RecorderAction.GO_BACK: "go_back",
        RecorderAction.GO_FORWARD: "go_forward",
        RecorderAction.PAUSE: "pause",
    }.get(step.action, "step")
    if step.locator_name:
        return f"{verb}_{step.locator_name.lower()}"
    if step.payload:
        slug = _NON_IDENT.sub("_", step.payload).strip("_").lower()[:24]
        return f"{verb}_{slug}" if slug else f"{verb}_{idx}"
    return f"{verb}_{idx}"


def _safe_test_name(scenario: str) -> str:
    cleaned = _NON_IDENT.sub("_", scenario).strip("_").lower()
    if not cleaned:
        cleaned = "scenario"
    if cleaned[0].isdigit():
        cleaned = f"s_{cleaned}"
    return f"test_{cleaned}"


def _is_visible_only(loc: PomLocator) -> bool:
    """Whether the locator should get a default ``expect_visual`` line.

    Today every catalogued locator gets one — image diff is the
    cheapest assertion and the user can prune by hand. Kept as a hook
    so future heuristics (skip non-stable elements, etc.) can plug in.
    """
    return True


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_python_source(source: str) -> None:
    """Round-trip through ``ast.parse``; raises :class:`SyntaxError`."""
    import ast

    ast.parse(source)


def locators_from_assets(
    assets: Iterable[tuple[str, str | None, str | None]],
) -> list[PomLocator]:
    """Helper: ``(asset, selector, text)`` triples → unique
    :class:`PomLocator` list (collision-aware naming)."""
    out: list[PomLocator] = []
    used: set[str] = set()
    for asset, selector, text in assets:
        name = upper_snake(asset)
        candidate = name
        i = 2
        while candidate in used:
            candidate = f"{name}_{i}"
            i += 1
        used.add(candidate)
        out.append(
            PomLocator(name=candidate, asset=asset, selector=selector, text=text)
        )
    return out


def steps_from_records(
    records: Sequence[tuple[RecorderAction, str | None, str | None]],
    *,
    asset_to_locator: dict[str, str],
) -> list[PomStep]:
    """``(action, asset, payload)`` triples → :class:`PomStep` list.

    ``asset_to_locator`` maps an asset filename to its catalogue
    locator name so steps cite locators by identifier rather than
    embedding the filename literal.
    """
    out: list[PomStep] = []
    for action, asset, payload in records:
        loc_name = asset_to_locator.get(asset) if asset else None
        out.append(PomStep(action=action, locator_name=loc_name, payload=payload))
    return out
