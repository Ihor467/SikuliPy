"""Web Auto recorder mode (Phase 11).

The IDE's recorder gains a third surface: a web page driven by
Playwright. Discovery, filtering, screenshot capture and asset
cropping all live behind a :class:`BrowserBackend` Protocol so the unit
tests never need to spawn Chromium.

Module overview:

* :mod:`sikulipy.web._backend` — ``BrowserBackend`` Protocol, the
  lazy ``_PlaywrightBackend``, and an in-memory ``_FakeBackend``
  for tests. ``get_backend()`` / ``set_backend()`` mirror the
  pattern used by ocr / natives / guide.
* :mod:`sikulipy.web.elements` — ``WebElement`` dataclass +
  ``ElementKind`` enum + the discovery JS payload Playwright
  evaluates inside the page.
* :mod:`sikulipy.web.filters` — ``ElementFilter`` (set of
  enabled ``ElementKind``s) with ``apply()``.
* :mod:`sikulipy.web.assets` — ``asset_root(project_dir, url)``
  carves ``<project>/assets/web/<host>/`` and ``crop_element``
  writes a tight-bbox PNG with a small padding.
* :mod:`sikulipy.web.screen` — ``WebScreen(Region)`` so recorded
  scripts can run unchanged after the recording finishes.
"""

from __future__ import annotations

from sikulipy.web._backend import (
    BrowserBackend,
    _FakeBackend,
    get_backend,
    set_backend,
)
from sikulipy.web.assets import asset_root, crop_element, slug_for_element
from sikulipy.web.elements import ElementKind, WebElement
from sikulipy.web.filters import ElementFilter

__all__ = [
    "BrowserBackend",
    "ElementFilter",
    "ElementKind",
    "WebElement",
    "asset_root",
    "crop_element",
    "get_backend",
    "set_backend",
    "slug_for_element",
    "_FakeBackend",
]
