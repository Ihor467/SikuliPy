"""Port of ``org.sikuli.script.Pattern`` — image + similarity + target offset."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sikulipy.core.offset import Offset


@dataclass
class Pattern:
    image: str | Path | None = None  # path, bytes, or Image instance later
    similarity: float = 0.7
    target_offset: Offset = field(default_factory=Offset)
    wait_after: float = 0.0

    def similar(self, score: float) -> "Pattern":
        return Pattern(self.image, score, self.target_offset, self.wait_after)

    def targetOffset(self, dx: int, dy: int) -> "Pattern":  # noqa: N802 - Java parity
        return Pattern(self.image, self.similarity, Offset(dx, dy), self.wait_after)

    def exact(self) -> "Pattern":
        return self.similar(0.99)
