"""Port of ``org.sikuli.script.Mouse`` — mouse input.

Thin facade over a swappable backend (see :mod:`sikulipy.core._input_backend`).
"""

from __future__ import annotations

import time

from sikulipy.core._input_backend import get_mouse
from sikulipy.core.location import Location


class Mouse:
    LEFT = 1
    MIDDLE = 2
    RIGHT = 3

    _NAME = {LEFT: "left", MIDDLE: "middle", RIGHT: "right"}

    move_mouse_delay: float = 0.0  # post-action settle delay

    # ---- Queries -----------------------------------------------------
    @classmethod
    def at(cls) -> Location:
        x, y = get_mouse().position()
        return Location(x, y)

    # ---- Movement ----------------------------------------------------
    @classmethod
    def move(cls, loc: Location | tuple[int, int]) -> Location:
        x, y = (loc.x, loc.y) if isinstance(loc, Location) else loc
        get_mouse().move(int(x), int(y))
        cls._settle()
        return cls.at()

    # ---- Clicks ------------------------------------------------------
    @classmethod
    def click(cls, loc: Location | tuple[int, int] | None = None, button: int = LEFT) -> Location:
        if loc is not None:
            cls.move(loc)
        get_mouse().click(cls._NAME[button], count=1)
        cls._settle()
        return cls.at()

    @classmethod
    def double_click(cls, loc: Location | tuple[int, int] | None = None, button: int = LEFT) -> Location:
        if loc is not None:
            cls.move(loc)
        get_mouse().click(cls._NAME[button], count=2)
        cls._settle()
        return cls.at()

    @classmethod
    def right_click(cls, loc: Location | tuple[int, int] | None = None) -> Location:
        return cls.click(loc, button=cls.RIGHT)

    @classmethod
    def middle_click(cls, loc: Location | tuple[int, int] | None = None) -> Location:
        return cls.click(loc, button=cls.MIDDLE)

    # ---- Press/release ----------------------------------------------
    @classmethod
    def down(cls, button: int = LEFT) -> None:
        get_mouse().press(cls._NAME[button])

    @classmethod
    def up(cls, button: int = LEFT) -> None:
        get_mouse().release(cls._NAME[button])

    # ---- Drag --------------------------------------------------------
    @classmethod
    def drag_drop(
        cls,
        src: Location | tuple[int, int],
        dst: Location | tuple[int, int],
        button: int = LEFT,
    ) -> Location:
        cls.move(src)
        cls.down(button)
        # A short pause helps some window managers register the press.
        time.sleep(0.05)
        cls.move(dst)
        cls.up(button)
        cls._settle()
        return cls.at()

    # ---- Wheel -------------------------------------------------------
    WHEEL_UP = 1
    WHEEL_DOWN = -1

    @classmethod
    def wheel(cls, direction: int, steps: int = 1) -> None:
        get_mouse().scroll(0, int(direction) * int(steps))

    # ---- Internals ---------------------------------------------------
    @classmethod
    def _settle(cls) -> None:
        if cls.move_mouse_delay > 0:
            time.sleep(cls.move_mouse_delay)
