"""Swappable subprocess launcher shared by the shell-oriented runners.

Tests register a recorder via :func:`set_launcher` so they can inspect
the command, environment, and working directory without spawning real
processes. Production code uses the default :func:`_default_launch`,
which is a thin wrapper around :mod:`subprocess`.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Protocol


@dataclass
class LaunchResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""


class Launcher(Protocol):
    def __call__(
        self,
        argv: list[str],
        *,
        cwd: str | None,
        env: dict[str, str] | None,
    ) -> LaunchResult: ...


def _default_launch(
    argv: list[str],
    *,
    cwd: str | None,
    env: dict[str, str] | None,
) -> LaunchResult:
    proc = subprocess.run(  # noqa: S603 - callers are responsible for argv
        argv,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return LaunchResult(
        exit_code=proc.returncode,
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
    )


_launcher: Launcher = _default_launch


def get_launcher() -> Launcher:
    return _launcher


def set_launcher(launcher: Launcher | None) -> None:
    global _launcher
    _launcher = launcher if launcher is not None else _default_launch
