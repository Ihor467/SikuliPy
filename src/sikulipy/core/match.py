"""Port of ``org.sikuli.script.Match`` — the result of a successful find."""

from __future__ import annotations

from dataclasses import dataclass

from sikulipy.core.region import Region


@dataclass
class Match(Region):
    score: float = 0.0
    index: int = 0

    def target(self):  # -> Location
        return self.center()
