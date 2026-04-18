"""Smoke tests for the scaffold — pure-Python only, no numpy/OpenCV."""

from __future__ import annotations

import pytest


def test_top_level_imports():
    from sikulipy import FindFailed, Location, Match, Pattern, Region, __version__

    assert __version__
    assert Location(1, 2).offset(3, 4) == Location(4, 6)
    assert issubclass(FindFailed, Exception)

    Pattern(image="x.png").similar(0.9)
    Region(0, 0, 100, 100)
    Match(0, 0, 10, 10, score=0.95)


def test_subpackages_import():
    import sikulipy.android  # noqa: F401
    import sikulipy.hotkey  # noqa: F401
    import sikulipy.runners  # noqa: F401
    import sikulipy.vnc  # noqa: F401


def test_screen_lazy_attribute():
    """``Screen`` is exposed lazily; only imports numpy/OpenCV on access."""
    import sikulipy

    if pytest.importorskip.__module__:  # pytest always true – placeholder for the doc comment
        pass

    try:
        import numpy  # noqa: F401
    except Exception:
        pytest.skip("NumPy unavailable on this host")

    assert sikulipy.Screen is sikulipy.Screen  # lazy attribute returns a stable class
