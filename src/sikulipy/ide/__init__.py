"""Flet-based IDE — replaces the Swing IDE from the Java project.

Ports the high-level concepts of OculiX/IDE/src/main/java/org/sikuli/ide:

* ``EditorPane``         -> :mod:`.editor` (:class:`EditorDocument`)
* ``ScriptExplorer``     -> :mod:`.explorer` (:class:`ScriptTreeNode`,
  :func:`build_tree`)
* ``SikuliIDEStatusBar`` -> :mod:`.statusbar` (:class:`StatusModel`)
* ``EditorConsolePane``  -> :mod:`.console` (:class:`ConsoleBuffer`,
  :class:`ConsoleRedirect`)
* ``ButtonCapture``      -> :mod:`.capture` (:class:`CaptureSession`)
* ``ButtonOnToolbar``    -> :mod:`.toolbar` (:class:`ToolbarActions`)
* ``OculixSidebar``      -> :mod:`.sidebar` (:class:`SidebarModel`)

Models are headless and individually unit-tested. The Flet view in
:mod:`.app` binds to them.
"""

from sikulipy.ide.capture import CaptureRect, CaptureSession
from sikulipy.ide.console import ConsoleBuffer, ConsoleEntry, ConsoleRedirect
from sikulipy.ide.editor import EditorDocument
from sikulipy.ide.explorer import ScriptTreeNode, build_tree, classify
from sikulipy.ide.sidebar import SidebarItem, SidebarModel
from sikulipy.ide.statusbar import StatusModel
from sikulipy.ide.toolbar import RunnerHost, ToolbarActions

__all__ = [
    "CaptureRect",
    "CaptureSession",
    "ConsoleBuffer",
    "ConsoleEntry",
    "ConsoleRedirect",
    "EditorDocument",
    "RunnerHost",
    "ScriptTreeNode",
    "SidebarItem",
    "SidebarModel",
    "StatusModel",
    "ToolbarActions",
    "build_tree",
    "classify",
]
