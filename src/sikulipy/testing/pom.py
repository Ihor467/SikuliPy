"""Page Object Model base class for image-driven Web Auto tests.

The catalogue on each subclass is a list of :class:`ImageLocator`
attributes. Each locator carries:

* ``asset`` — basename of the cropped PNG, looked up under
  ``<project>/assets/web/<host>/`` to drive clicks and under
  ``<project>/baselines/web/<host>/`` for visual assertions.
* ``selector`` — optional CSS selector used as the *fallback* path
  when the image-based match dips below ``min_similarity`` (a real
  page redesign that moves *and* repaints the element). The
  generated test still passes; the runner emits a "locator drifted"
  warning so the user knows to re-run with ``--update-baselines``.
* ``min_similarity`` / ``mode`` — comparison knobs for
  :func:`sikulipy.testing.compare.compare_images`. ``mode`` defaults
  to ``"exact"`` so the test suite has no extra dependency; opt into
  ``"ssim"`` once ``scikit-image`` is installed for robustness against
  font hinting / anti-aliasing drift.
* ``text`` — optional expected label, fed to
  :func:`sikulipy.testing.ocr_assert.compare_text` in
  ``expect_text``.

The base class :class:`WebPageObject` wraps a :class:`WebScreen`, the
asset folder, and a :class:`BaselineStore`. Generated subclasses stay
thin — they declare locators and expose action / assertion methods
that compose the base primitives.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, ClassVar

from sikulipy.testing.baseline import BaselineStore
from sikulipy.testing.compare import ImageDiff, Mode, compare_images
from sikulipy.testing.ocr_assert import TextDiff, compare_text

if TYPE_CHECKING:  # pragma: no cover
    import numpy as np


@dataclass(frozen=True)
class ImageLocator:
    """One entry in a Page Object's catalogue."""

    asset: str
    selector: str | None = None
    min_similarity: float = 0.85
    mode: Mode = "exact"
    text: str | None = None
    text_threshold: float = 0.85


@dataclass
class LocatorWarning:
    """Emitted when an image locator drifts and we fall back."""

    locator: ImageLocator
    reason: str


class LocatorDriftError(RuntimeError):
    """Raised when the image match fails *and* no selector fallback exists."""


# ---------------------------------------------------------------------------
# Page Object base
# ---------------------------------------------------------------------------


class WebPageObject:
    """Base class for generated Page Objects.

    Subclasses set :pyattr:`URL` and declare :class:`ImageLocator`
    attributes. The :meth:`start` factory builds a default screen +
    asset/baseline binding; tests that need a fake screen can call the
    constructor directly.
    """

    URL: ClassVar[str] = ""

    def __init__(
        self,
        screen: Any,
        *,
        project_dir: Path,
        host: str | None = None,
        baseline_store: BaselineStore | None = None,
        asset_dir: Path | None = None,
        on_warning: Callable[[LocatorWarning], None] | None = None,
    ) -> None:
        self.screen = screen
        self.project_dir = Path(project_dir)
        self.host = host or _host_from_url(self.URL)
        self.baselines = baseline_store or BaselineStore(project_dir, self.host)
        self.assets = asset_dir or (
            self.project_dir / "assets" / "web" / self.host
        )
        self._warnings: list[LocatorWarning] = []
        self._on_warning = on_warning or self._warnings.append

    # ---- Factory -----------------------------------------------------
    @classmethod
    def start(
        cls,
        screen: Any,
        *,
        project_dir: Path,
        **kwargs: Any,
    ) -> "WebPageObject":
        return cls(screen=screen, project_dir=project_dir, **kwargs)

    # ---- Accessors ---------------------------------------------------
    @property
    def warnings(self) -> list[LocatorWarning]:
        """Locator drift warnings collected so far this session."""
        return list(self._warnings)

    def asset_path(self, locator: ImageLocator) -> Path:
        return self.assets / locator.asset

    # ---- Actions -----------------------------------------------------
    def click(self, locator: ImageLocator) -> None:
        target = self._resolve_target(locator)
        self.screen.click(target)

    def double_click(self, locator: ImageLocator) -> None:
        target = self._resolve_target(locator)
        self.screen.double_click(target)

    def hover(self, locator: ImageLocator) -> None:
        target = self._resolve_target(locator)
        self.screen.hover(target)

    def type(self, locator: ImageLocator, text: str) -> None:
        self.click(locator)
        self.screen.type(text)

    # ---- Assertions --------------------------------------------------
    def expect_visual(
        self,
        locator: ImageLocator,
        *,
        threshold: float | None = None,
    ) -> ImageDiff:
        """Compare the locator's region against its baseline image.

        Raises ``AssertionError`` on failure with the comparison
        message — pytest renders that nicely in the test report.
        """
        baseline = self.baselines.load(locator.asset)
        actual = self._capture_region(locator, baseline_shape=baseline.shape[:2])
        diff = compare_images(
            actual, baseline, mode=locator.mode, threshold=threshold
        )
        if not diff.passed:
            raise AssertionError(
                f"visual diff failed for {locator.asset}: {diff.message}"
            )
        return diff

    def expect_text(
        self,
        locator: ImageLocator,
        expected: str | None = None,
        *,
        ratio_threshold: float | None = None,
    ) -> TextDiff:
        """Run OCR over the locator's region and assert the text."""
        target = expected if expected is not None else locator.text
        if target is None:
            raise ValueError(
                f"locator {locator.asset!r} has no text and none was passed"
            )
        threshold = (
            ratio_threshold
            if ratio_threshold is not None
            else locator.text_threshold
        )
        baseline = self.baselines.load(locator.asset)
        actual = self._capture_region(locator, baseline_shape=baseline.shape[:2])
        diff = compare_text(actual, target, ratio_threshold=threshold)
        if not diff.passed:
            raise AssertionError(
                f"text diff failed for {locator.asset}: {diff.message}"
            )
        return diff

    # ---- Internals ---------------------------------------------------
    def _resolve_target(self, locator: ImageLocator) -> Any:
        """Hand back the value to pass to ``screen.click`` / ``hover``.

        Default: a :class:`Pattern` keyed off the locator's asset
        filename, resolved through the screen's image path. The
        selector fallback is checked at *capture* time (in
        :meth:`_capture_region`) — by the time we click, the user has
        already accepted the match.
        """
        from sikulipy.core.pattern import Pattern

        return Pattern(locator.asset).similar(locator.min_similarity)

    def _capture_region(
        self,
        locator: ImageLocator,
        *,
        baseline_shape: tuple[int, int],
    ) -> "np.ndarray":
        """Pull pixels for ``locator`` from the live screen.

        Uses the screen's ``find`` to localise the locator, then crops
        the matched bbox so visual + text comparisons run on the
        element's region rather than the whole page. Falls back to the
        CSS selector when image localisation fails and the locator has
        one — the screen exposes ``capture_selector`` for that path
        (provided by :class:`WebScreen`).
        """
        from sikulipy.core.pattern import Pattern

        try:
            match = self.screen.find(Pattern(locator.asset))
        except Exception as exc:
            if locator.selector and hasattr(self.screen, "capture_selector"):
                self._on_warning(
                    LocatorWarning(
                        locator=locator,
                        reason=f"image find failed ({exc}); using selector",
                    )
                )
                return self.screen.capture_selector(locator.selector)
            raise LocatorDriftError(
                f"locator {locator.asset!r} did not match and no selector fallback"
            ) from exc
        return self.screen.capture_match(match)


def _host_from_url(url: str) -> str:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.hostname or "unknown"
    return host
