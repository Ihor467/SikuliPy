"""Port of Highlight.java — draws a coloured rectangle over a Region for debugging."""

from __future__ import annotations


class Highlight:
    def __init__(self, region, color: str = "red", duration: float = 2.0) -> None:
        self.region = region
        self.color = color
        self.duration = duration

    def show(self) -> None:
        raise NotImplementedError("Phase 7: transparent Flet overlay window")

    def close(self) -> None:
        raise NotImplementedError("Phase 7")
