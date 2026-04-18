"""Robot Framework runner. Phase 6 — requires the ``runners`` extra."""

from __future__ import annotations

from pathlib import Path

from sikulipy.runners.base import Runner


class RobotRunner(Runner):
    name = "robot"
    extensions = (".robot",)

    def run(self, path: str | Path, args: list[str] | None = None) -> int:
        raise NotImplementedError("Phase 6: call robot.run_cli")
