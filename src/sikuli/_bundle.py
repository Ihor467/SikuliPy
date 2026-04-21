"""Bundle-path + image-path helpers.

Port of SikuliX's free functions ``getBundlePath`` / ``setBundlePath`` /
``addImagePath``. In SikuliX the bundle path is the ``.sikuli`` folder
the script runs from; images referenced by bare filename are resolved
against it. The Python runner (:func:`sikulipy.runners.python_runner._bundle_path_pushed`)
already pushes the script's parent onto :class:`sikulipy.core.image.ImagePath`
before the script runs, so by the time these functions are called from
user code, the bundle path is the first entry in ``ImagePath.paths()``.
"""

from __future__ import annotations

import time
from pathlib import Path

from sikuli._settings import Settings


def _image_path():
    # Lazy import — :mod:`sikulipy.core.image` pulls in cv2/numpy, which
    # isn't available on every host. Keeping this out of the top of the
    # module means ``import sikuli`` still works (for Settings, popup,
    # sleep) even where cv2 is broken.
    from sikulipy.core.image import ImagePath

    return ImagePath


def getBundlePath() -> str | None:  # noqa: N802 - SikuliX parity
    """Return the current bundle path (first registered image path) or None."""
    if Settings.BundlePath:
        return Settings.BundlePath
    paths = _image_path().paths()
    return str(paths[0]) if paths else None


def setBundlePath(path: str | Path) -> None:  # noqa: N802 - SikuliX parity
    """Set the bundle path and prepend it to :class:`ImagePath`."""
    resolved = str(Path(path).resolve())
    Settings.BundlePath = resolved
    ImagePath = _image_path()
    # Drop any previous bundle-path slot and re-add at the head so the
    # bundle is searched first.
    current = [p for p in ImagePath.paths() if str(p) != resolved]
    ImagePath._paths = [Path(resolved), *current]


def addImagePath(path: str | Path) -> None:  # noqa: N802 - SikuliX parity
    """Register an additional directory for image lookups."""
    _image_path().add(path)


def removeImagePath(path: str | Path) -> None:  # noqa: N802 - SikuliX parity
    """Remove a previously registered image-path entry (no-op if absent)."""
    ImagePath = _image_path()
    target = Path(path).resolve()
    ImagePath._paths = [p for p in ImagePath.paths() if p != target]


def getImagePath() -> list[str]:  # noqa: N802 - SikuliX parity
    """Return the registered image-path stack as strings."""
    return [str(p) for p in _image_path().paths()]


def sleep(seconds: float) -> None:
    """SikuliX's module-level ``sleep`` — just :func:`time.sleep`."""
    time.sleep(float(seconds))


__all__ = [
    "addImagePath",
    "getBundlePath",
    "getImagePath",
    "removeImagePath",
    "setBundlePath",
    "sleep",
]
