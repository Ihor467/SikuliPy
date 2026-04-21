"""Install SikuliX-style camelCase aliases on :class:`Region`.

The port uses snake_case (``find_all``, ``double_click``, ``drag_drop``,
``wait_vanish``, ``find_text``, ``find_all_text``, ``has_text``,
``top_left``, ``top_right``, ``bottom_left``, ``bottom_right``,
``is_valid``), matching the project's style. SikuliX user scripts use
camelCase. Rather than duplicate every method, we attach thin aliases
at import time so both names resolve to the same underlying function.

Aliases are attached to the class object, not instances — they are
cheap attribute lookups, not wrappers. This also means the aliases
inherit automatically to :class:`Match` and :class:`Screen` (both
subclass :class:`Region`).
"""

from __future__ import annotations

from sikulipy.core.region import Region


_ALIASES: dict[str, str] = {
    # Finding
    "findAll": "find_all",
    "waitVanish": "wait_vanish",
    # Clicks
    "doubleClick": "double_click",
    "rightClick": "right_click",
    "dragDrop": "drag_drop",
    # OCR
    "findText": "find_text",
    "findAllText": "find_all_text",
    "hasText": "has_text",
    # Geometry
    "topLeft": "top_left",
    "topRight": "top_right",
    "bottomLeft": "bottom_left",
    "bottomRight": "bottom_right",
    "isValid": "is_valid",
    # Observation
    "onAppear": "on_appear",
    "onVanish": "on_vanish",
    "onChange": "on_change",
}


def install() -> None:
    """Attach camelCase aliases to :class:`Region` (idempotent)."""
    for camel, snake in _ALIASES.items():
        if not hasattr(Region, camel) and hasattr(Region, snake):
            setattr(Region, camel, getattr(Region, snake))


__all__ = ["install"]
