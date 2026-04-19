"""Robot Framework runner — optional, requires the ``runners`` extra.

Invokes Robot Framework in-process via ``robot.run_cli(..., exit=False)``.
If the ``robot`` package isn't installed, :meth:`is_supported` reports
False and :meth:`run_file` raises a clear ``RuntimeError``.
"""

from __future__ import annotations

from pathlib import Path

from sikulipy.runners.base import Options, Runner


class RobotRunner(Runner):
    name = "Robot"
    extensions = (".robot",)

    def is_supported(self) -> bool:
        try:
            import robot  # noqa: F401
        except ImportError:
            return False
        return True

    def run_file(self, path: str | Path, options: Options | None = None) -> int:
        try:
            import robot  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - exercised via is_supported
            raise RuntimeError(
                "Robot Framework is not installed; "
                "`pip install sikulipy[runners]` to enable the Robot runner"
            ) from exc

        opts = options or Options()
        # ``robot.run_cli`` returns the RC when ``exit=False``.
        argv = [*opts.args, str(Path(path).resolve())]
        return int(robot.run_cli(argv, exit=False))
