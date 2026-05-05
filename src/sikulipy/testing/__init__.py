"""Phase 12 — image-driven test generation.

Public surface:

* :mod:`sikulipy.testing.levenshtein` — distance + ratio helpers.
* :mod:`sikulipy.testing.compare` — OpenCV image comparison.
* :mod:`sikulipy.testing.ocr_assert` — Tesseract + Levenshtein text
  assertion.
* :mod:`sikulipy.testing.baseline` — golden image store.
* :mod:`sikulipy.testing.pom` — :class:`WebPageObject` base +
  :class:`ImageLocator`.
"""

from __future__ import annotations
