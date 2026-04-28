"""Step-by-step recorder — clones OculiX's Modern Recorder.

Each user action in the recorder dialog is a button click that triggers
a region capture (via :mod:`sikulipy.ide.capture_overlay`), validates
the pattern, and appends a generated source line to a live preview.
There is no global mouse/keyboard hook — the dialog drives every step.

The Flet UI lives in :mod:`sikulipy.ide.recorder.dialog`; everything
underneath is headless and unit-testable.
"""

from sikulipy.ide.recorder.codegen import (
    CodeGenerator,
    PythonGenerator,
    default_generator,
)
from sikulipy.ide.recorder.devices import (
    DESKTOP_ENTRY_KEY,
    DeviceEntry,
    DevicePicker,
)
from sikulipy.ide.recorder.session import RecorderSession
from sikulipy.ide.recorder.surface import (
    TargetSurface,
    _AndroidSurface,
    _DesktopSurface,
    _FakeSurface,
    default_surface,
)
from sikulipy.ide.recorder.workflow import (
    RecorderAction,
    RecorderState,
    RecorderWorkflow,
)

__all__ = [
    "CodeGenerator",
    "DESKTOP_ENTRY_KEY",
    "DeviceEntry",
    "DevicePicker",
    "PythonGenerator",
    "RecorderAction",
    "RecorderSession",
    "RecorderState",
    "RecorderWorkflow",
    "TargetSurface",
    "_AndroidSurface",
    "_DesktopSurface",
    "_FakeSurface",
    "default_generator",
    "default_surface",
]
