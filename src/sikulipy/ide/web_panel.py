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


Subscriber = Callable[["WebAutoState"], None]
AssetWriter = Callable[[Path, "np.ndarray"], Path]
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

    def filtered(self) -> list[WebElement]:
        return self.applied.apply(self.elements)


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
        """Commit the pending filter and refresh overlays + list."""
        self.state.applied = ElementFilter(kinds=set(self.state.filter.kinds))
        if (
            self.state.selected is not None
            and self.state.selected not in self.state.filtered()
        ):
            self.state.selected = None
        result = self.state.filtered()
        self.state.status = f"Filter applied — {len(result)} shown"
        self._notify()
        return result

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
        elements = self.state.filtered()
        if not elements:
            self.state.status = "Nothing to save — filter is empty"
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
