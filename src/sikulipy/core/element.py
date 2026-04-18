"""Port of ``org.sikuli.script.Element``.

Element is the common ancestor of Region / Location / Match / Image in Java.
In Python we use a protocol plus a mixin for the shared helpers (toString,
getScreen, isValid, etc.). Phase 1.
"""

from __future__ import annotations

from typing import Protocol


class HasBounds(Protocol):
    x: int
    y: int
    w: int
    h: int


class Element:
    """Base class for screen-anchored objects. Stub."""

    def is_valid(self) -> bool:
        raise NotImplementedError

    def get_screen(self):  # -> Screen | None
        raise NotImplementedError
