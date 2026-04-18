"""Common runner interface. Phase 6."""

from __future__ import annotations

from pathlib import Path


class Runner:
    name: str = "base"
    extensions: tuple[str, ...] = ()

    def can_handle(self, path: str | Path) -> bool:
        return str(path).lower().endswith(self.extensions)

    def run(self, path: str | Path, args: list[str] | None = None) -> int:
        raise NotImplementedError

    @classmethod
    def run_path(cls, path: str | Path, args: list[str] | None = None) -> int:
        raise NotImplementedError("Phase 6: dispatch to the right runner by extension")
