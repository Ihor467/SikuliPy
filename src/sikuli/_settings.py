"""``Settings`` — live global configuration, SikuliX-compatible.

SikuliX scripts poke fields on the ``Settings`` class (not an instance)
to tweak runtime behaviour::

    Settings.MinSimilarity = 0.9
    Settings.OcrTextRead = True
    Settings.MoveMouseDelay = 0.3

Most fields are plain state — reader code inside the port checks
``Settings.X`` directly (e.g. the OCR stack honours ``OcrTextRead``).
A handful of fields are aliases for attributes already living elsewhere
in ``sikulipy``; assigning to them mirrors the write into the canonical
home so existing code picks up the new value without extra plumbing
(e.g. ``Settings.MoveMouseDelay`` writes through to
:attr:`sikulipy.core.mouse.Mouse.move_mouse_delay`).
"""

from __future__ import annotations

from typing import Any, Callable


# Hooks keyed by attribute name. Each hook is called with the new value
# when the user assigns ``Settings.<name> = ...``. Hooks use lazy imports
# so importing the sikuli package doesn't drag in the whole core stack.
def _set_move_mouse_delay(value: float) -> None:
    from sikulipy.core.mouse import Mouse

    Mouse.move_mouse_delay = float(value)


def _set_type_delay(value: float) -> None:
    from sikulipy.core.keyboard import Key

    Key._type_delay = float(value)


def _set_min_similarity(value: float) -> None:
    from sikulipy.core._defaults import set_min_similarity

    set_min_similarity(float(value))


_WRITE_HOOKS: dict[str, Callable[[Any], None]] = {
    "MoveMouseDelay": _set_move_mouse_delay,
    "TypeDelay": _set_type_delay,
    "MinSimilarity": _set_min_similarity,
}


class _SettingsMeta(type):
    """Intercept class-level assignment so hooks fire for aliased fields."""

    def __setattr__(cls, name: str, value: Any) -> None:
        hook = _WRITE_HOOKS.get(name)
        type.__setattr__(cls, name, value)
        if hook is not None:
            hook(value)


class Settings(metaclass=_SettingsMeta):
    """SikuliX-compatible global configuration flags.

    Values are plain class attributes — readers just do
    ``if Settings.OcrTextRead: ...``. The metaclass fires
    :data:`_WRITE_HOOKS` on assignment so a write to (say)
    ``Settings.MoveMouseDelay`` also updates :class:`Mouse`.
    """

    # ---- OCR -------------------------------------------------------
    # Honoured by the OCR stack in :mod:`sikulipy.ocr` when it picks up
    # text recognition requests.
    OcrTextRead: bool = False
    OcrTextSearch: bool = False
    OcrLanguage: str = "eng"

    # ---- Find / action behaviour -----------------------------------
    MinSimilarity: float = 0.7
    MoveMouseDelay: float = 0.0
    TypeDelay: float = 0.0
    DelayBeforeDrop: float = 0.1
    DelayAfterDrag: float = 0.1

    # ---- Waits -----------------------------------------------------
    AutoWaitTimeout: float = 3.0
    WaitAfterHighlight: float = 0.3
    SlowMotionDelay: float = 2.0
    ObserveScanRate: float = 3.0
    ObserveMinChangedPixels: int = 50

    # ---- Logging / UX ---------------------------------------------
    ActionLogs: bool = True
    InfoLogs: bool = True
    DebugLogs: bool = False
    ShowActions: bool = False

    # ---- Bundle path ----------------------------------------------
    BundlePath: str | None = None


__all__ = ["Settings"]
