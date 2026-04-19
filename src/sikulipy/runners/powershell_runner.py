"""PowerShell runner — port of ``org.sikuli.script.runners.PowershellRunner``.

Invokes ``powershell.exe`` (Windows) or ``pwsh`` (elsewhere, if installed)
with the same flags the Java version used: ``-ExecutionPolicy Unrestricted
-NonInteractive -NoLogo -NoProfile -WindowStyle Hidden -File <script>``.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from sikulipy.runners._subprocess import get_launcher
from sikulipy.runners.base import Options, Runner, prepare_env, resolve_work_dir


class PowerShellRunner(Runner):
    name = "PowerShell"
    extensions = (".ps1",)

    def is_supported(self) -> bool:
        return self._interpreter() is not None

    def _interpreter(self) -> str | None:
        # On Windows prefer powershell.exe for parity with SikuliX; otherwise
        # fall back to cross-platform ``pwsh``.
        if sys.platform.startswith("win"):
            for exe in ("powershell.exe", "pwsh.exe"):
                path = shutil.which(exe)
                if path:
                    return path
        return shutil.which("pwsh")

    def run_file(self, path: str | Path, options: Options | None = None) -> int:
        exe = self._interpreter()
        if exe is None:
            raise RuntimeError("PowerShell interpreter not found on PATH")
        opts = options or Options()
        script = str(Path(path).resolve())
        argv = [
            exe,
            "-ExecutionPolicy", "Unrestricted",
            "-NonInteractive", "-NoLogo", "-NoProfile",
            "-WindowStyle", "Hidden",
            "-File", script,
            *opts.args,
        ]
        result = get_launcher()(
            argv,
            cwd=resolve_work_dir(path, opts),
            env=prepare_env(opts),
        )
        return result.exit_code
