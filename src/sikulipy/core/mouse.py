"""Port of ``org.sikuli.script.Mouse`` — mouse input.

Thin facade over a swappable backend (see :mod:`sikulipy.core._input_backend`).
"""

from __future__ import annotations

import time

from sikulipy.core._input_backend import get_mouse
from sikulipy.core.location import Location
from sikulipy.util.action_log import logged_action


def _fmt_loc(_cls, *args, **_k) -> str:
    if not args or args[0] is None:
        return ""
    a = args[0]
    if isinstance(a, Location):
        return f"({a.x}, {a.y})"
    if isinstance(a, tuple) and len(a) == 2:
        return f"({a[0]}, {a[1]})"
    return repr(a)


def _fmt_drag(_cls, *args, **_k) -> str:
    if len(args) >= 2:
        return f"{_fmt_loc(_cls, args[0])} → {_fmt_loc(_cls, args[1])}"
    return ""


def _fmt_wheel(_cls, *args, **kwargs) -> str:
    direction = args[0] if args else kwargs.get("direction")
    steps = kwargs.get("steps", args[1] if len(args) > 1 else 1)
    return f"direction={direction} steps={steps}"


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
    @logged_action("mouse", "move", target=_fmt_loc)
    def move(cls, loc: Location | tuple[int, int]) -> Location:
        x, y = (loc.x, loc.y) if isinstance(loc, Location) else loc
        get_mouse().move(int(x), int(y))
        cls._settle()
        return cls.at()

    # ---- Clicks ------------------------------------------------------
    @classmethod
    @logged_action("mouse", "click", target=_fmt_loc)
    def click(cls, loc: Location | tuple[int, int] | None = None, button: int = LEFT) -> Location:
        if loc is not None:
            cls.move(loc)
        get_mouse().click(cls._NAME[button], count=1)
        cls._settle()
        return cls.at()

    @classmethod
    @logged_action("mouse", "double_click", target=_fmt_loc)
    def double_click(cls, loc: Location | tuple[int, int] | None = None, button: int = LEFT) -> Location:
        if loc is not None:
            cls.move(loc)
        get_mouse().click(cls._NAME[button], count=2)
        cls._settle()
        return cls.at()

    @classmethod
    @logged_action("mouse", "right_click", target=_fmt_loc)
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
    @logged_action("mouse", "drag_drop", target=_fmt_drag)
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
    @logged_action("mouse", "wheel", target=_fmt_wheel)
    def wheel(cls, direction: int, steps: int = 1) -> None:
        get_mouse().scroll(0, int(direction) * int(steps))

    # ---- Internals ---------------------------------------------------
    @classmethod
    def _settle(cls) -> None:
        if cls.move_mouse_delay > 0:
            time.sleep(cls.move_mouse_delay)
