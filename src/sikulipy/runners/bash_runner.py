"""POSIX shell runner.

Not a 1:1 Java port (SikuliX had no dedicated bash runner); included here
because Unix-flavoured automation frequently needs to drop into ``sh``.
Invokes ``/bin/sh <script> <args...>``.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from sikulipy.runners._subprocess import get_launcher
from sikulipy.runners.base import Options, Runner, prepare_env, resolve_work_dir


class BashRunner(Runner):
    name = "Bash"
    extensions = (".sh", ".bash")

    def is_supported(self) -> bool:
        return not sys.platform.startswith("win") and self._interpreter() is not None

    def _interpreter(self) -> str | None:
        return shutil.which("bash") or shutil.which("sh") or "/bin/sh"

    def run_file(self, path: str | Path, options: Options | None = None) -> int:
        exe = self._interpreter()
        if exe is None:
            raise RuntimeError("no POSIX shell available")
        opts = options or Options()
        argv = [exe, str(Path(path).resolve()), *opts.args]
        result = get_launcher()(
            argv,
            cwd=resolve_work_dir(path, opts),
            env=prepare_env(opts),
        )
        return result.exit_code
