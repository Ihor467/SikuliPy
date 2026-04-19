"""Common runner interface + registry.

Ports the relevant parts of ``org.sikuli.support.runner.AbstractRunner``
and ``AbstractLocalFileScriptRunner`` to Python. Each runner exposes:

* ``name``                       — human label (``"Python"``, ``"PowerShell"``, ...)
* ``extensions``                 — tuple of lowercase extensions (``(".py",)``)
* ``is_supported()``             — whether this runner can run on this host
* ``run_file(path, options)``    — execute a file and return an exit code
* ``run_string(src, options)``   — optional: eval a snippet (writes to a
  temp file and calls ``run_file`` by default)

A module-level registry maps extensions to runner instances. Callers use
:func:`run_file`, :func:`run_string`, or :func:`runner_for` and never
instantiate concrete runners directly.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable


# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------


@dataclass
class Options:
    """Mirror of ``IRunner.Options`` — per-invocation knobs.

    Attributes:
        args: Extra positional arguments passed to the script (``sys.argv``
            for Python, positional args for subprocess runners).
        work_dir: Working directory for the script; defaults to the script's
            parent directory.
        env: Additional environment variables to merge over ``os.environ``.
        silent: Suppress error logging on non-zero exit (Sikuli parity).
    """

    args: list[str] = field(default_factory=list)
    work_dir: str | None = None
    env: dict[str, str] | None = None
    silent: bool = False


# ---------------------------------------------------------------------------
# Runner ABC
# ---------------------------------------------------------------------------


class Runner:
    """Abstract base. Subclasses set ``name``/``extensions`` and override
    :meth:`run_file` (and optionally :meth:`is_supported` /
    :meth:`run_string`)."""

    name: str = "base"
    extensions: tuple[str, ...] = ()

    # ---- Introspection ---------------------------------------------
    def is_supported(self) -> bool:
        """True if this runner can execute scripts on the current host."""
        return True

    def can_handle(self, path: str | Path) -> bool:
        """True if ``path`` has one of this runner's extensions.

        Mirrors ``AbstractLocalFileScriptRunner.canHandle``: URLs with a
        ``proto://`` prefix are rejected (NetworkRunner territory).
        """
        s = str(path)
        if "://" in s[:8]:
            return False
        ext = Path(s).suffix.lower()
        return ext in self.extensions

    # ---- Hooks -----------------------------------------------------
    def run_file(self, path: str | Path, options: Options | None = None) -> int:
        """Run a file on disk and return the exit code."""
        raise NotImplementedError

    def run_string(self, source: str, options: Options | None = None) -> int:
        """Run an in-memory snippet.

        Default implementation writes ``source`` to a temp file with the
        first declared extension and calls :meth:`run_file`. Runners that
        need a richer eval path (e.g. Python's in-process exec) override
        this.
        """
        if not self.extensions:
            raise RuntimeError(f"{self.name}: run_string requires a declared extension")
        ext = self.extensions[0]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=ext, delete=False, encoding="utf-8"
        ) as f:
            f.write(source)
            tmp_path = f.name
        try:
            return self.run_file(tmp_path, options)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Registry — module-level, extension-indexed
# ---------------------------------------------------------------------------

_REGISTRY: list[Runner] = []


def register(runner: Runner) -> Runner:
    """Register a runner. Later registrations win when extensions overlap.

    Returns the runner so this can be used as a decorator-style expression.
    """
    _REGISTRY.append(runner)
    return runner


def unregister(runner: Runner) -> None:
    try:
        _REGISTRY.remove(runner)
    except ValueError:
        pass


def clear_registry() -> None:
    """Remove every registered runner (mostly useful for tests)."""
    _REGISTRY.clear()


def registered() -> list[Runner]:
    return list(_REGISTRY)


def runner_for(path: str | Path) -> Runner | None:
    """Return the most-recently-registered runner that handles ``path``."""
    for runner in reversed(_REGISTRY):
        if runner.can_handle(path):
            return runner
    return None


def runner_by_name(name: str) -> Runner | None:
    for runner in reversed(_REGISTRY):
        if runner.name.lower() == name.lower():
            return runner
    return None


def run_file(path: str | Path, options: Options | None = None) -> int:
    """Dispatch to whichever registered runner handles ``path``.

    Raises ``RuntimeError`` when no runner claims the extension.
    """
    runner = runner_for(path)
    if runner is None:
        raise RuntimeError(f"no runner registered for {path!r}")
    if not runner.is_supported():
        raise RuntimeError(
            f"{runner.name} runner is not supported on this host"
        )
    return runner.run_file(path, options)


def run_string(source: str, *, name: str, options: Options | None = None) -> int:
    """Eval ``source`` using the runner with the given ``name``."""
    runner = runner_by_name(name)
    if runner is None:
        raise RuntimeError(f"no runner registered with name {name!r}")
    if not runner.is_supported():
        raise RuntimeError(
            f"{runner.name} runner is not supported on this host"
        )
    return runner.run_string(source, options)


# ---------------------------------------------------------------------------
# Helpers for subprocess runners
# ---------------------------------------------------------------------------


def prepare_env(options: Options | None) -> dict[str, str]:
    env = dict(os.environ)
    if options and options.env:
        env.update(options.env)
    return env


def resolve_work_dir(path: str | Path, options: Options | None) -> str:
    if options and options.work_dir:
        return options.work_dir
    return str(Path(path).resolve().parent)


def _extensions_from(exts: "Iterable[str]") -> tuple[str, ...]:
    """Normalise a list of extension strings to ``(".py", ".pyw")`` form."""
    out: list[str] = []
    for e in exts:
        e = e.lower()
        if not e.startswith("."):
            e = "." + e
        out.append(e)
    return tuple(out)
