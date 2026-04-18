"""Python script runner. Phase 6."""

from __future__ import annotations

from pathlib import Path

from sikulipy.runners.base import Runner


class PythonRunner(Runner):
    name = "python"
    extensions = (".py", ".sikuli")

    def run(self, path: str | Path, args: list[str] | None = None) -> int:
        raise NotImplementedError("Phase 6: exec file in namespace with sikulipy imports preloaded")
