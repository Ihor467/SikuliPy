"""AppleScript runner — port of ``AppleScriptRunner.java``.

Shells out to ``/usr/bin/osascript`` with the script path and any extra
positional arguments. Supported on macOS only.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from sikulipy.runners._subprocess import get_launcher
from sikulipy.runners.base import Options, Runner, prepare_env, resolve_work_dir


class AppleScriptRunner(Runner):
    name = "AppleScript"
    # Sikuli used ``.script``; ``.applescript`` and ``.scpt`` are the modern
    # extensions. Accept all three so scripts aren't silently skipped.
    extensions = (".applescript", ".scpt", ".script")

    def is_supported(self) -> bool:
        return sys.platform == "darwin" and self._interpreter() is not None

    def _interpreter(self) -> str | None:
        return shutil.which("osascript") or "/usr/bin/osascript"

    def run_file(self, path: str | Path, options: Options | None = None) -> int:
        if sys.platform != "darwin":
            raise RuntimeError("AppleScript runner requires macOS")
        exe = self._interpreter()
        if exe is None:
            raise RuntimeError("osascript not found")
        opts = options or Options()
        argv = [exe, str(Path(path).resolve()), *opts.args]
        result = get_launcher()(
            argv,
            cwd=resolve_work_dir(path, opts),
            env=prepare_env(opts),
        )
        return result.exit_code
