"""Headless controller for the Web Auto IDE pane.

Owns the state machine that the Flet view binds to:

* ``WebAutoState`` — URL, screenshot path, raw element list,
  active filter, currently-selected element, asset folder.
* ``WebAutoController`` — orchestrates the backend (launch, goto,
  discover, screenshot), applies the filter, and crops PNGs into the
  asset folder when *Take ElScrsht* fires.

No Flet imports here. The Flet pane subscribes to
:meth:`WebAutoController.subscribe` and rebuilds its widgets on every
state change. Tests substitute a :class:`_FakeBackend` and an in-memory
asset writer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterable

from sikulipy.web import (
    BrowserBackend,
    ElementFilter,
    ElementKind,
    WebElement,
    asset_root,
    crop_element,
    get_backend,
    slug_for_element,
)

if TYPE_CHECKING:
    import numpy as np


@dataclass(frozen=True)
class GeneratedTestArtefacts:
    """Files produced by :meth:`WebAutoController.generate_tests`."""

    page_object: Path
    test_module: Path
    baselines: list[Path]


Subscriber = Callable[["WebAutoState"], None]
AssetWriter = Callable[[Path, "np.ndarray"], Path]

AUTO_INCLUDE_THRESHOLD = 10
"""Filter result size at or below which every row is auto-included on
Apply. Larger result sets default to none-selected so the user opts in
explicitly without an overlay-flooded screenshot."""
"""Pluggable PNG writer — defaults to ``sikulipy.web.assets.write_png``;
tests pass a recording stub."""


@dataclass
class WebAutoState:
    """Snapshot of everything the UI needs to render in one pass.

    Mutated in place by :class:`WebAutoController`; subscribers see the
    same instance after each change. Treat as read-only outside the
    controller.
    """

    active: bool = False
    url: str | None = None
    screenshot: Path | None = None
    elements: list[WebElement] = field(default_factory=list)
    # ``filter`` tracks checkbox state as the user toggles. ``applied``
    # is the snapshot used by ``filtered()`` — overlays + the element
    # list only refresh when the user clicks Apply, so the page isn't
    # repainted on every checkbox tick.
    filter: ElementFilter = field(default_factory=ElementFilter)
    applied: ElementFilter = field(default_factory=ElementFilter)
    selected: WebElement | None = None
    device_pixel_ratio: float = 1.0
    document_size: tuple[int, int] = (0, 0)
    asset_dir: Path | None = None
    last_saved: list[Path] = field(default_factory=list)
    status: str = ""
    error: str | None = None
    # Selectors of elements the user has *opted out* of after the filter
    # was applied. Stored as exclusions (rather than inclusions) so the
    # default "all visible elements participate" stays a no-op set —
    # newly-discovered elements after a refresh are included
    # automatically.
    excluded: set[str] = field(default_factory=set)

    def filtered(self) -> list[WebElement]:
        return self.applied.apply(self.elements)

    def included(self) -> list[WebElement]:
        """Filtered elements minus the user's per-row exclusions."""
        return [el for el in self.filtered() if el.selector not in self.excluded]

    def is_included(self, element: WebElement) -> bool:
        return element.selector not in self.excluded


@dataclass
class WebAutoController:
    """Drive the Web Auto state machine.

    Public methods (start / set_filter_kind / select / take_screenshots
    / refresh / close) update :attr:`state` and notify subscribers.
    Every method tolerates being called when the mode is inactive so
    the IDE doesn't have to guard each button binding.
    """

    project_dir: Path
    backend: BrowserBackend | None = None
    asset_writer: AssetWriter | None = None
    state: WebAutoState = field(default_factory=WebAutoState)
    _subscribers: list[Subscriber] = field(default_factory=list, repr=False)
    _screenshot_dir: Path | None = field(default=None, repr=False)

    # ---- Subscription ------------------------------------------------
    def subscribe(self, fn: Subscriber) -> Callable[[], None]:
        self._subscribers.append(fn)

        def _unsub() -> None:
            if fn in self._subscribers:
                self._subscribers.remove(fn)

        return _unsub

    def _notify(self) -> None:
        for cb in list(self._subscribers):
            cb(self.state)

    # ---- Lifecycle ---------------------------------------------------
    def start(self, url: str) -> None:
        """Launch the backend, navigate, capture, and discover.

        Errors are absorbed into ``state.error`` so the IDE bar can show
        a banner without crashing the recorder.
        """
        backend = self._resolve_backend()
        self.state = WebAutoState(active=True, url=url)
        try:
            # Headless: we render the captured screenshot inside the
            # IDE; popping a separate Chromium window confuses the
            # one-window flow and steals focus from the IDE.
            backend.launch(headed=False)
            backend.goto(url)
            shot_dir = self._ensure_screenshot_dir()
            shot = backend.screenshot(shot_dir / "page.png")
            result = backend.discover()
            self.state.screenshot = shot
            self.state.elements = list(result.elements)
            self.state.device_pixel_ratio = result.device_pixel_ratio
            self.state.document_size = result.document_size
            self.state.asset_dir = asset_root(self.project_dir, url)
            self.state.status = (
                f"Loaded {url} — {len(self.state.elements)} elements"
            )
        except Exception as exc:
            self.state.error = str(exc) or exc.__class__.__name__
            self.state.status = f"Failed to load {url}"
        self._notify()

    def refresh(self) -> None:
        """Re-snapshot the current URL and re-discover elements."""
        if not self.state.active or not self.state.url:
            return
        backend = self._resolve_backend()
        try:
            shot_dir = self._ensure_screenshot_dir()
            shot = backend.screenshot(shot_dir / "page.png")
            result = backend.discover()
            self.state.screenshot = shot
            self.state.elements = list(result.elements)
            self.state.device_pixel_ratio = result.device_pixel_ratio
            self.state.document_size = result.document_size
            self.state.status = f"Re-snapshot — {len(self.state.elements)} elements"
            self.state.error = None
        except Exception as exc:
            self.state.error = str(exc) or exc.__class__.__name__
            self.state.status = "Refresh failed"
        self._notify()

    def close(self) -> None:
        """Tear the backend down and reset state."""
        if self.backend is not None:
            try:
                self.backend.close()
            except Exception:
                pass
        self.state = WebAutoState()
        self._notify()

    # ---- Filtering ---------------------------------------------------
    def set_filter_kind(self, kind: ElementKind, on: bool) -> None:
        """Mutate the pending filter only. Overlays + list don't redraw
        until :meth:`apply_filter` commits the pending set into
        ``state.applied``."""
        if not self.state.active:
            return
        self.state.filter.toggle(kind, on)

    def apply_filter(self) -> list[WebElement]:
        """Commit the pending filter and refresh overlays + list.

        Auto-selection heuristic: a small filtered set (<= 10) is most
        likely the user's target — opt every row in. A large set is a
        broad sweep the user will narrow down by hand — opt every row
        out so the screenshot isn't drowned in overlays. The threshold
        is intentionally hard-coded; tune by editing
        :data:`AUTO_INCLUDE_THRESHOLD`.
        """
        self.state.applied = ElementFilter(kinds=set(self.state.filter.kinds))
        if (
            self.state.selected is not None
            and self.state.selected not in self.state.filtered()
        ):
            self.state.selected = None
        result = self.state.filtered()
        if len(result) <= AUTO_INCLUDE_THRESHOLD:
            self.state.excluded = set()
            picked = len(result)
        else:
            self.state.excluded = {el.selector for el in result}
            picked = 0
        self.state.status = (
            f"Filter applied — {len(result)} shown, {picked} selected"
        )
        self._notify()
        return result

    def set_included(self, element: WebElement, on: bool) -> None:
        """Toggle whether ``element`` participates in capture / codegen.

        Drives the per-row checkbox in the Web Auto pane. Mutates
        ``state.excluded`` and notifies subscribers so the screenshot
        overlay stays in sync.
        """
        if not self.state.active:
            return
        if on:
            self.state.excluded.discard(element.selector)
        else:
            self.state.excluded.add(element.selector)
        self._notify()

    def set_all_included(self, on: bool) -> None:
        """Bulk toggle every filtered element."""
        if not self.state.active:
            return
        if on:
            self.state.excluded = set()
        else:
            self.state.excluded = {el.selector for el in self.state.filtered()}
        self._notify()

    def select(self, element: WebElement | None) -> None:
        if not self.state.active:
            return
        self.state.selected = element
        self._notify()

    # ---- Capture -----------------------------------------------------
    def take_screenshots(self) -> list[Path]:
        """Crop every filtered element to a PNG in the asset folder.

        Uses the live frame (``backend.frame()``) so the crop stays in
        sync with the most recent snapshot. Returns the list of files
        written; also stashes it on ``state.last_saved`` for the IDE
        status bar.
        """
        if not self.state.active or not self.state.elements:
            return []
        backend = self._resolve_backend()
        elements = self.state.included()
        if not elements:
            self.state.status = "Nothing to save — no elements selected"
            self._notify()
            return []
        try:
            frame = backend.frame()
        except Exception as exc:
            self.state.error = f"Could not read frame: {exc}"
            self._notify()
            return []
        writer = self.asset_writer or _default_writer
        asset_dir = self.state.asset_dir or asset_root(
            self.project_dir, self.state.url or "unknown"
        )
        saved: list[Path] = []
        for el in elements:
            try:
                cropped = crop_element(
                    frame,
                    el.bounds,
                    device_pixel_ratio=self.state.device_pixel_ratio,
                )
            except Exception:
                continue
            target = asset_dir / f"{slug_for_element(el)}.png"
            try:
                writer(target, cropped)
            except Exception as exc:
                self.state.error = f"Write failed for {target.name}: {exc}"
                continue
            saved.append(target)
        self.state.last_saved = saved
        self.state.status = (
            f"Saved {len(saved)} elements → "
            f"{asset_dir.relative_to(self.project_dir) if asset_dir.is_relative_to(self.project_dir) else asset_dir}"
        )
        self._notify()
        return saved

    # ---- Codegen -----------------------------------------------------
    def generate_tests(
        self,
        scenario: str,
        *,
        records: Iterable[tuple[Any, str | None, str | None]] = (),
        force: bool = False,
    ) -> GeneratedTestArtefacts:
        """Render Page Object + pytest module for the current session.

        ``scenario`` is the human label that becomes the test function
        name (``test_<scenario>``). ``records`` is a sequence of
        ``(RecorderAction, asset_filename, payload)`` triples — pass the
        recorder's session here so the generated test calls action
        methods in recording order. The method walks the filtered
        element list to build the catalogue, then writes:

        * ``<project>/pages/<host_slug>.py`` (refuses to clobber unless
          ``force=True``)
        * ``<project>/tests/web/test_<scenario>.py`` (same)
        * baseline PNGs copied from ``state.asset_dir`` into
          ``<project>/baselines/web/<host>/`` (always overwrites — the
          captured asset is the source of truth at generation time).
        """
        from sikulipy.ide.recorder.pom_codegen import (
            PomLocator,
            PomScenario,
            locators_from_assets,
            module_slug,
            render_page_object,
            render_test_module,
            steps_from_records,
            validate_python_source,
        )
        from sikulipy.testing.baseline import BaselineMetadata, BaselineStore

        if not self.state.active or not self.state.url:
            raise RuntimeError("Web Auto session is not active")
        elements = self.state.included()
        if not elements:
            raise RuntimeError(
                "No elements selected — apply a filter and tick the rows "
                "you want to keep"
            )

        host = _host_for_url(self.state.url)
        asset_dir = self.state.asset_dir or asset_root(
            self.project_dir, self.state.url
        )

        # Map filtered WebElements → (asset, selector, text-or-None)
        # triples. Locator names come from the asset filename; the
        # accessible name lands as ``text`` only when it looks like a
        # caption the test should assert (skip blank / role-only names).
        triples: list[tuple[str, str | None, str | None]] = []
        asset_to_loc: dict[str, str] = {}
        for el in elements:
            asset = f"{slug_for_element(el)}.png"
            text = el.name.strip() if el.name and el.name.strip() else None
            triples.append((asset, el.selector or None, text))
        locators: list[PomLocator] = locators_from_assets(triples)
        for el, loc in zip(elements, locators):
            asset_to_loc[f"{slug_for_element(el)}.png"] = loc.name

        steps = steps_from_records(list(records), asset_to_locator=asset_to_loc)
        pom_scenario = PomScenario(
            host=host,
            url=self.state.url,
            scenario=scenario,
            locators=locators,
            steps=steps,
        )

        page_src = render_page_object(pom_scenario)
        test_src = render_test_module(pom_scenario)
        validate_python_source(page_src)
        validate_python_source(test_src)

        host_module = module_slug(host)
        scenario_module = module_slug(scenario)
        page_path = self.project_dir / "pages" / f"{host_module}.py"
        test_path = (
            self.project_dir / "tests" / "web" / f"test_{scenario_module}.py"
        )
        if not force:
            for p in (page_path, test_path):
                if p.exists():
                    raise FileExistsError(
                        f"refusing to overwrite {p} — pass force=True to clobber"
                    )

        page_path.parent.mkdir(parents=True, exist_ok=True)
        test_path.parent.mkdir(parents=True, exist_ok=True)
        # Make pages a package so ``from pages.x import Y`` resolves.
        init_path = page_path.parent / "__init__.py"
        if not init_path.exists():
            init_path.write_text("", encoding="utf-8")
        page_path.write_text(page_src, encoding="utf-8")
        test_path.write_text(test_src, encoding="utf-8")

        # Drop a conftest.py once per project — owned by the user from
        # then on, so re-running Generate doesn't clobber edits.
        conftest_path = self.project_dir / "tests" / "web" / "conftest.py"
        if not conftest_path.exists():
            from sikulipy.testing.conftest_template import CONFTEST_SOURCE

            conftest_path.write_text(CONFTEST_SOURCE, encoding="utf-8")

        # Seed baselines from the captured PNGs. Asset_dir is the
        # cropped-element folder; copy each kept locator's PNG into the
        # baseline store. Missing PNGs (filter changed since last
        # capture) are skipped silently — the test will fail loudly with
        # the --update-baselines hint when run.
        store = BaselineStore(self.project_dir, host)
        seeded: list[Path] = []
        for loc in locators:
            src = asset_dir / loc.asset
            if src.is_file():
                seeded.append(store.promote_from(loc.asset, src))
        store.write_metadata(
            BaselineMetadata(
                dpr=self.state.device_pixel_ratio,
                viewport=self.state.document_size or (1600, 900),
            )
        )

        self.state.status = (
            f"Generated {test_path.name} + {page_path.name} "
            f"({len(seeded)} baselines seeded)"
        )
        self._notify()
        return GeneratedTestArtefacts(
            page_object=page_path,
            test_module=test_path,
            baselines=seeded,
        )

    # ---- Internals ---------------------------------------------------
    def _resolve_backend(self) -> BrowserBackend:
        if self.backend is None:
            self.backend = get_backend()
        return self.backend

    def _ensure_screenshot_dir(self) -> Path:
        if self._screenshot_dir is None:
            base = self.project_dir / ".sikulipy" / "web"
            base.mkdir(parents=True, exist_ok=True)
            self._screenshot_dir = base
        return self._screenshot_dir


def _default_writer(target: Path, image: "np.ndarray") -> Path:
    from sikulipy.web.assets import write_png

    return write_png(target, image)


def _host_for_url(url: str) -> str:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.hostname or "unknown"
    return host.lower()


def all_kinds() -> Iterable[ElementKind]:
    """Stable order for the filter checkbox column."""
    return [
        ElementKind.LINK,
        ElementKind.BUTTON,
        ElementKind.INPUT,
        ElementKind.CHECKBOX_RADIO,
        ElementKind.SELECT,
        ElementKind.MENU,
        ElementKind.TAB,
        ElementKind.OTHER,
    ]
