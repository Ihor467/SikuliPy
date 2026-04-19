"""In-process Python runner.

Port of ``org.sikuli.script.runners.PythonRunner``. The Java version
shells out to a ``python`` interpreter because it runs inside a JVM; we
already *are* a Python interpreter, so we execute the script in-process
using :func:`runpy.run_path`.

Accepts both plain ``.py`` files and SikuliX ``.sikuli`` bundles (a
directory containing a ``foo.py`` sibling file). In either case the
script's parent directory is pushed onto :class:`ImagePath` so
``Pattern("btn.png")`` resolves relative to the script — the Sikuli
bundle-path semantics that every SikuliX script depends on.
"""

from __future__ import annotations

import contextlib
import runpy
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from sikulipy.runners.base import Options, Runner

if TYPE_CHECKING:
    from collections.abc import Iterator


class PythonRunner(Runner):
    name = "Python"
    extensions = (".py", ".sikuli")

    def is_supported(self) -> bool:
        return True

    def run_file(self, path: str | Path, options: Options | None = None) -> int:
        script_path = _resolve_script(Path(path))
        if script_path is None:
            raise FileNotFoundError(f"Python script not found: {path}")

        opts = options or Options()
        with _bundle_path_pushed(script_path.parent):
            with _sys_argv_patched([str(script_path), *opts.args]):
                try:
                    runpy.run_path(str(script_path), run_name="__main__")
                except SystemExit as exc:
                    code = exc.code
                    if code is None:
                        return 0
                    if isinstance(code, int):
                        return code
                    # str-argument SystemExit is conventionally an error.
                    return 1
                except BaseException:
                    if not opts.silent:
                        raise
                    return 1
                return 0

    def run_string(self, source: str, options: Options | None = None) -> int:
        """Execute a snippet in a fresh module namespace (no temp file)."""
        opts = options or Options()
        namespace: dict[str, object] = {"__name__": "__main__"}
        with _sys_argv_patched(["<string>", *opts.args]):
            try:
                exec(compile(source, "<string>", "exec"), namespace)  # noqa: S102
            except SystemExit as exc:
                code = exc.code
                if code is None:
                    return 0
                if isinstance(code, int):
                    return code
                return 1
            except BaseException:
                if not opts.silent:
                    raise
                return 1
            return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_script(path: Path) -> Path | None:
    """Resolve a ``.py`` file or ``.sikuli`` bundle to the actual script.

    A ``.sikuli`` bundle is a directory named ``foo.sikuli`` containing a
    sibling script called ``foo.py``.
    """
    if path.is_file() and path.suffix.lower() == ".py":
        return path.resolve()
    if path.is_dir() and path.suffix.lower() == ".sikuli":
        stem = path.stem  # "foo" for "foo.sikuli"
        candidate = path / f"{stem}.py"
        if candidate.is_file():
            return candidate.resolve()
        # Fall back to any .py file inside the bundle.
        for child in sorted(path.iterdir()):
            if child.is_file() and child.suffix.lower() == ".py":
                return child.resolve()
    if path.suffix.lower() == ".py" and not path.exists():
        return None
    return path.resolve() if path.exists() else None


@contextlib.contextmanager
def _bundle_path_pushed(bundle: Path) -> "Iterator[None]":
    """Push ``bundle`` onto :class:`ImagePath` and ``sys.path`` for the call.

    ``ImagePath`` lives in :mod:`sikulipy.core.image`, which pulls in
    numpy/opencv. On hosts where those are unavailable, we still want the
    runner to work — just without the bundle-path registration. The
    ``sys.path`` push always happens so plain-Python scripts can import
    sibling modules.
    """
    sys_path_added = False
    bundle_str = str(bundle)
    if bundle_str not in sys.path:
        sys.path.insert(0, bundle_str)
        sys_path_added = True

    image_path_cls = None
    before_paths: list[Path] = []
    try:
        from sikulipy.core.image import ImagePath as image_path_cls  # type: ignore[assignment]

        before_paths = list(image_path_cls.paths())
        image_path_cls.add(bundle)
    except Exception:
        # numpy/opencv absent — plain exec will still work.
        image_path_cls = None

    try:
        yield
    finally:
        if image_path_cls is not None:
            image_path_cls._paths = before_paths  # restore exact prior stack
        if sys_path_added:
            with contextlib.suppress(ValueError):
                sys.path.remove(bundle_str)


@contextlib.contextmanager
def _sys_argv_patched(argv: list[str]) -> "Iterator[None]":
    saved = sys.argv
    sys.argv = list(argv)
    try:
        yield
    finally:
        sys.argv = saved
