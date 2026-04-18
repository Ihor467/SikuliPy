"""SikuliPy — Python port of OculiX/SikuliX.

Top-level convenience re-exports for the most commonly used classes so that
end-user automation scripts can simply do::

    from sikulipy import Screen, Region, Pattern, Match

Everything here is currently a scaffold — see ROADMAP.md for porting phases.
"""

from __future__ import annotations

__version__ = "0.0.1"

from sikulipy.core.location import Location
from sikulipy.core.match import Match
from sikulipy.core.pattern import Pattern
from sikulipy.core.region import Region
from sikulipy.script.exceptions import FindFailed, SikuliXception

__all__ = [
    "FindFailed",
    "Location",
    "Match",
    "Pattern",
    "Region",
    "Screen",
    "SikuliXception",
    "__version__",
]


def __getattr__(name: str):
    # Lazy import so environments without numpy/OpenCV can still import the
    # pure-Python primitives (Location, Region, Pattern, Match, exceptions).
    if name == "Screen":
        from sikulipy.core.screen import Screen as _Screen

        return _Screen
    raise AttributeError(f"module 'sikulipy' has no attribute {name!r}")
