"""Port of ``org.sikuli.script.Offset`` — a (dx, dy) delta used by Pattern.targetOffset."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Offset:
    dx: int = 0
    dy: int = 0
