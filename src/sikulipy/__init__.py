"""SikuliPy — Python port of OculiX/SikuliX.

Top-level convenience re-exports for the most commonly used classes so that
end-user automation scripts can simply do::

    from sikulipy import Screen, Region, Pattern, Match

The module also rebinds the most common :class:`Screen` methods
(``find``, ``exists``, ``click``, ``type`` …) as top-level functions
so SikuliX-style scripts that call ``exists(Pattern("ok.png"))``
without explicitly instantiating a Screen still work — matching the
ergonomics of the Java IDE's auto-bound globals.

Everything here is currently a scaffold — see ROADMAP.md for porting phases.
"""

from __future__ import annotations

__version__ = "0.0.1"

from sikulipy.core.location import Location
from sikulipy.core.match import Match
from sikulipy.core.pattern import Pattern
from sikulipy.core.region import Region
from sikulipy.script.exceptions import FindFailed, SikuliXception

# Methods on the primary Screen that get rebound as module-level
# functions for SikuliX-style scripts. Anything we expect a script to
# call as a bare verb goes here; introspection helpers and private
# methods stay on Region/Screen so ``from sikulipy import *`` doesn't
# pollute the user's namespace with internals.
_SCREEN_BOUND = (
    "click", "double_click", "right_click", "hover",
    "drag_drop", "type", "paste",
    "find", "find_all", "exists", "wait", "wait_vanish",
    "text", "find_text", "find_all_text",
    "capture", "highlight",
)


__all__ = [
    "FindFailed",
    "Location",
    "Match",
    "Pattern",
    "Region",
    "Screen",
    "SikuliXception",
    "__version__",
    *_SCREEN_BOUND,
]


def _primary_screen():
    """Return (and lazily cache) the primary Screen instance.

    SikuliX scripts treat ``Screen()`` as a process-wide singleton —
    instantiating one on every bare ``exists()`` call would re-probe
    the framebuffer each time. Cache the first one we build.
    """
    cached = globals().get("_PRIMARY_SCREEN")
    if cached is None:
        from sikulipy.core.screen import Screen as _Screen

        cached = _Screen()
        globals()["_PRIMARY_SCREEN"] = cached
    return cached


def _make_screen_proxy(method_name: str):
    """Build a top-level shim that forwards to the primary Screen.

    We can't write ``exists = _primary_screen().exists`` at import
    time — that would build a Screen on ``import sikulipy``, which is
    a real cost on headless hosts (and breaks the ``no numpy/cv2``
    fallback that the rest of this module preserves). The proxy
    defers Screen construction to first call.
    """

    def _proxy(*args, **kwargs):
        return getattr(_primary_screen(), method_name)(*args, **kwargs)

    _proxy.__name__ = method_name
    _proxy.__qualname__ = f"sikulipy.{method_name}"
    _proxy.__doc__ = (
        f"Shortcut for ``Screen().{method_name}(...)``. See "
        f":meth:`sikulipy.core.region.Region.{method_name}`."
    )
    return _proxy


for _name in _SCREEN_BOUND:
    globals()[_name] = _make_screen_proxy(_name)
del _name


def __getattr__(name: str):
    # Lazy import so environments without numpy/OpenCV can still import the
    # pure-Python primitives (Location, Region, Pattern, Match, exceptions).
    if name == "Screen":
        from sikulipy.core.screen import Screen as _Screen

        return _Screen
    raise AttributeError(f"module 'sikulipy' has no attribute {name!r}")
