"""Module-level wrappers delegating to the primary :class:`Screen`.

SikuliX scripts call ``click(btn)``, ``find(btn)``, ``type("x")`` etc.
without an explicit receiver. These are implicit method calls on the
primary screen. Each wrapper here is a one-liner around
``Screen.get_primary().<method>``.

Only include functions that actually make sense without a receiver. For
example ``find_text`` on an arbitrary region is useful, but the flat
``findText`` helper is assumed to search the whole primary screen.
"""

from __future__ import annotations

from typing import Any

from sikulipy.core.location import Location
from sikulipy.core.mouse import Mouse


def _primary():
    # Lazy import to avoid pulling mss/numpy during ``import sikuli``.
    from sikulipy.core.screen import Screen

    return Screen.get_primary()


# ---------------------------------------------------------------------------
# Find / wait / exists
# ---------------------------------------------------------------------------


def find(target: Any):
    return _primary().find(target)


def findAll(target: Any):  # noqa: N802 - SikuliX parity
    return _primary().find_all(target)


def wait(target: Any, timeout: float = 3.0):
    return _primary().wait(target, timeout=timeout)


def waitVanish(target: Any, timeout: float = 3.0) -> bool:  # noqa: N802
    return _primary().wait_vanish(target, timeout=timeout)


def exists(target: Any, timeout: float = 0.0):
    return _primary().exists(target, timeout=timeout)


# ---------------------------------------------------------------------------
# Clicks
# ---------------------------------------------------------------------------


def click(target: Any | None = None) -> int:
    return _primary().click(target)


def doubleClick(target: Any | None = None) -> int:  # noqa: N802
    return _primary().double_click(target)


def rightClick(target: Any | None = None) -> int:  # noqa: N802
    return _primary().right_click(target)


def hover(target: Any | None = None) -> int:
    return _primary().hover(target)


def dragDrop(src: Any, dst: Any) -> int:  # noqa: N802
    return _primary().drag_drop(src, dst)


# ---------------------------------------------------------------------------
# Keyboard
# ---------------------------------------------------------------------------


def type(text: str, modifiers: int = 0) -> int:  # noqa: A001 - SikuliX shadows
    return _primary().type(text, modifiers=modifiers)


def paste(text: str) -> int:
    return _primary().paste(text)


# ---------------------------------------------------------------------------
# Raw mouse / keyboard
# ---------------------------------------------------------------------------


def mouseMove(loc: Location | tuple[int, int]) -> Location:  # noqa: N802
    return Mouse.move(loc)


def mouseDown(button: int = Mouse.LEFT) -> None:  # noqa: N802
    Mouse.down(button)


def mouseUp(button: int = Mouse.LEFT) -> None:  # noqa: N802
    Mouse.up(button)


def wheel(direction: int, steps: int = 1) -> None:
    Mouse.wheel(direction, steps=steps)


def keyDown(key: str) -> None:  # noqa: N802
    from sikulipy.core.keyboard import Key

    Key.press(key)


def keyUp(key: str) -> None:  # noqa: N802
    from sikulipy.core.keyboard import Key

    Key.release(key)


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------


def text() -> str:
    return _primary().text()


def findText(needle: str):  # noqa: N802
    return _primary().find_text(needle)


def findAllText(needle: str):  # noqa: N802
    return _primary().find_all_text(needle)


__all__ = [
    "click",
    "doubleClick",
    "dragDrop",
    "exists",
    "find",
    "findAll",
    "findAllText",
    "findText",
    "hover",
    "keyDown",
    "keyUp",
    "mouseDown",
    "mouseMove",
    "mouseUp",
    "paste",
    "rightClick",
    "text",
    "type",
    "wait",
    "waitVanish",
    "wheel",
]
