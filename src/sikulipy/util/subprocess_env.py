"""Subprocess environment helpers.

When the process has imported ``cv2`` (directly or via sikulipy's capture/
finder code), OpenCV sets ``QT_QPA_PLATFORM_PLUGIN_PATH`` and
``QT_QPA_FONTDIR`` in the current environment so *its own* bundled Qt can
find *its own* plugins. Those variables are inherited by every child
process we spawn via :mod:`subprocess`. For Qt-based native helpers
(``kdialog`` on KDE, anything linking the system's Qt), that causes the
helper to load xcb from cv2's plugin dir instead of the system one, fail
silently (or with a warning buried in stderr), and exit with return code
0 *without rendering the dialog*. The user sees nothing.

Call :func:`native_dialog_env` when launching native helper binaries
(kdialog, zenity, file pickers, notification tools) to get an environment
with those fingerprints removed.
"""

from __future__ import annotations

import os

_CV2_QT_ENV_KEYS = ("QT_QPA_PLATFORM_PLUGIN_PATH", "QT_QPA_FONTDIR")


def native_dialog_env() -> dict[str, str]:
    """Return ``os.environ`` minus cv2's Qt plugin-path fingerprints."""
    env = os.environ.copy()
    for key in _CV2_QT_ENV_KEYS:
        env.pop(key, None)
    return env


__all__ = ["native_dialog_env"]
