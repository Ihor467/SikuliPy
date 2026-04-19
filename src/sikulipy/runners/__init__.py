"""Script runners — port of ``org.sikuli.script.runners``.

Concrete runners shipped in Phase 6:

* :class:`PythonRunner`      — in-process ``runpy`` exec, handles ``.py`` and ``.sikuli``
* :class:`PowerShellRunner`  — ``powershell.exe`` / ``pwsh`` subprocess (Windows primary)
* :class:`AppleScriptRunner` — ``osascript`` subprocess (macOS only)
* :class:`BashRunner`        — ``/bin/sh`` subprocess (POSIX)
* :class:`RobotRunner`       — Robot Framework in-process, needs the ``runners`` extra

Call :func:`run_file(path)` to dispatch by extension, or :func:`run_string`
to evaluate a snippet with a named runner.
"""

from sikulipy.runners.applescript_runner import AppleScriptRunner
from sikulipy.runners.bash_runner import BashRunner
from sikulipy.runners.base import (
    Options,
    Runner,
    clear_registry,
    register,
    registered,
    run_file,
    run_string,
    runner_by_name,
    runner_for,
    unregister,
)
from sikulipy.runners.powershell_runner import PowerShellRunner
from sikulipy.runners.python_runner import PythonRunner
from sikulipy.runners.robot_runner import RobotRunner

# Register the built-ins in priority order (later wins when extensions overlap).
_BUILTINS: tuple[Runner, ...] = (
    PythonRunner(),
    PowerShellRunner(),
    AppleScriptRunner(),
    BashRunner(),
    RobotRunner(),
)
for _r in _BUILTINS:
    register(_r)
del _r

__all__ = [
    "AppleScriptRunner",
    "BashRunner",
    "Options",
    "PowerShellRunner",
    "PythonRunner",
    "RobotRunner",
    "Runner",
    "clear_registry",
    "register",
    "registered",
    "run_file",
    "run_string",
    "runner_by_name",
    "runner_for",
    "unregister",
]
