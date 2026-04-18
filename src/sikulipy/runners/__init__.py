"""Script runners — port of ``org.sikuli.script.runners``.

Java supports Jython, JRuby, Python, PowerShell, AppleScript, Robot Framework,
plus a network/server runner. Python port will support:

* Native Python  (just ``exec`` / subprocess)
* PowerShell     (subprocess)
* AppleScript    (``osascript`` on macOS)
* Bash           (subprocess)
* Robot Framework (via the ``robot`` package, optional extra)

Phase 6.
"""

from sikulipy.runners.base import Runner

__all__ = ["Runner"]
