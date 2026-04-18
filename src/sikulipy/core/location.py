"""Port of ``org.sikuli.script.Location`` (API/src/main/java/org/sikuli/script/Location.java).

A Location is a 2D point on a screen. Offsets, arithmetic, and simple
geometry helpers live here. Phase 1 target.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Location:
    """2D screen coordinate.

    Ported signatures (stubs only):
        - above(y:int) / below(y:int) / left(x:int) / right(x:int)
        - offset(dx:int, dy:int) -> Location
        - getScreen() -> Screen
        - grow(range:int) -> Region
    """

    x: int
    y: int

    def offset(self, dx: int, dy: int) -> "Location":
        return Location(self.x + dx, self.y + dy)

    def above(self, dy: int) -> "Location":
        return Location(self.x, self.y - dy)

    def below(self, dy: int) -> "Location":
        return Location(self.x, self.y + dy)

    def left(self, dx: int) -> "Location":
        return Location(self.x - dx, self.y)

    def right(self, dx: int) -> "Location":
        return Location(self.x + dx, self.y)

    def grow(self, size: int):  # -> Region
        raise NotImplementedError("Phase 1: depends on Region")
