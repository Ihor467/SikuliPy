"""``sikuli`` — SikuliX-compatibility shim on top of :mod:`sikulipy`.

User scripts written for the original Jython-based SikuliX IDE start
with ``from sikuli import *`` and expect a flat namespace containing
classes (``Screen``, ``Region``, ``Pattern``, ``Match``, ``Location``,
``Key``, ``Mouse``, ``Env``, ``Settings``) plus module-level functions
(``click``, ``find``, ``type``, ``popup``, ``selectRegion``, ``sleep``,
``getBundlePath`` and friends).

This package is a thin re-export layer — every class and function here
is defined in :mod:`sikulipy`, with three classes of additions:

1. ``Settings`` — SikuliX's global configuration class, implemented in
   :mod:`sikuli._settings`. Assignments to ``Settings.X`` either store
   plain state or fire a hook that writes the value through to its
   canonical home in ``sikulipy.core``.
2. Module-level convenience wrappers (``click``, ``find``, ``wait``,
   ``type``, …) living in :mod:`sikuli._wrappers`. Each delegates to
   the primary :class:`Screen`.
3. User dialogs (``popup``, ``popupAsk``, ``input``, ``inputText``) and
   ``selectRegion``, living in :mod:`sikuli._dialogs` and
   :mod:`sikuli._select` respectively. Both reuse the
   kdialog→zenity→tk native-dialog probing pattern already in the IDE.

Importing this package also installs camelCase method aliases on
:class:`Region` (``findAll`` → ``find_all``, ``doubleClick`` →
``double_click``, …) via :mod:`sikuli._aliases`.
"""

from __future__ import annotations

# ---- Re-exports from sikulipy ------------------------------------------
# Lightweight primitives (no numpy/cv2) — import eagerly.
from sikulipy.core.env import Env
from sikulipy.core.keyboard import Key, KeyModifier
from sikulipy.core.location import Location
from sikulipy.core.mouse import Mouse
from sikulipy.core.offset import Offset
from sikulipy.core.pattern import Pattern
from sikulipy.script.exceptions import (
    FindFailed,
    FindFailedResponse,
    OculixTimeout,
    ScreenOperationError,
    SikuliException,
    SikuliXception,
)
from sikulipy.script.options import Options

# ---- Local additions (no heavy deps) -----------------------------------
from sikuli._bundle import (
    addImagePath,
    getBundlePath,
    getImagePath,
    removeImagePath,
    setBundlePath,
    sleep,
)
from sikuli._dialogs import (
    input,  # noqa: A004 - SikuliX shadows builtin
    inputText,
    popask,
    popup,
    popupAsk,
)
from sikuli._settings import Settings
from sikuli._wrappers import (
    click,
    doubleClick,
    dragDrop,
    exists,
    find,
    findAll,
    findAllText,
    findText,
    hover,
    keyDown,
    keyUp,
    mouseDown,
    mouseMove,
    mouseUp,
    paste,
    rightClick,
    text,
    type,  # noqa: A004 - SikuliX shadows builtin
    wait,
    waitVanish,
    wheel,
)

# ---- Lazy (numpy/cv2-bound) re-exports --------------------------------
# ``Image``, ``ImagePath``, ``ScreenImage``, ``Match``, ``Region``,
# ``Screen`` pull in ``sikulipy.core.image`` which imports ``cv2`` and
# ``numpy``. Load them on first attribute access so ``import sikuli``
# itself works in environments where the heavy stack is unavailable.
_LAZY_ATTRS: dict[str, tuple[str, str]] = {
    "Image":       ("sikulipy.core.image",  "Image"),
    "ImagePath":   ("sikulipy.core.image",  "ImagePath"),
    "ScreenImage": ("sikulipy.core.image",  "ScreenImage"),
    "Match":       ("sikulipy.core.match",  "Match"),
    "Region":      ("sikulipy.core.region", "Region"),
    "Screen":      ("sikulipy.core.screen", "Screen"),
    "selectRegion": ("sikuli._select",      "selectRegion"),
}


def __getattr__(name: str):
    """Lazily import heavy symbols; also install Region camelCase aliases."""
    spec = _LAZY_ATTRS.get(name)
    if spec is None:
        raise AttributeError(f"module 'sikuli' has no attribute {name!r}")
    import importlib

    mod = importlib.import_module(spec[0])
    value = getattr(mod, spec[1])
    # Once Region is loaded, install camelCase aliases (findAll, doubleClick, …).
    if name == "Region":
        from sikuli import _aliases

        _aliases.install()
    globals()[name] = value
    return value

__all__ = [
    # Classes
    "Env",
    "FindFailed",
    "FindFailedResponse",
    "Image",
    "ImagePath",
    "Key",
    "KeyModifier",
    "Location",
    "Match",
    "Mouse",
    "OculixTimeout",
    "Offset",
    "Options",
    "Pattern",
    "Region",
    "Screen",
    "ScreenImage",
    "ScreenOperationError",
    "Settings",
    "SikuliException",
    "SikuliXception",
    # Bundle / misc
    "addImagePath",
    "getBundlePath",
    "getImagePath",
    "removeImagePath",
    "setBundlePath",
    "sleep",
    # Dialogs
    "input",
    "inputText",
    "popask",
    "popup",
    "popupAsk",
    "selectRegion",
    # Actions
    "click",
    "doubleClick",
    "dragDrop",
    "exists",
    "find",
    "findAll",
    "findAllText",
    "findText",
    "hover",
    "keyDown",
    "keyUp",
    "mouseDown",
    "mouseMove",
    "mouseUp",
    "paste",
    "rightClick",
    "text",
    "type",
    "wait",
    "waitVanish",
    "wheel",
]
