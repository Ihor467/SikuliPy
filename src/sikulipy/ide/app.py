"""Flet IDE entry point.

The Flet view is intentionally thin: it observes the headless models
defined in :mod:`sikulipy.ide.editor`, :mod:`.console`, :mod:`.toolbar`,
:mod:`.sidebar`, :mod:`.statusbar`, and :mod:`.explorer`, and renders
their state. All real logic (undo/redo, run, capture, console capture)
lives in those models so it can be unit-tested without Flet.

Run::

    uv run sikulipy-ide
    # or
    uv run python -m sikulipy.ide.app
"""

from __future__ import annotations

from pathlib import Path

import flet as ft

from sikulipy import __version__
from sikulipy.ide.console import ConsoleBuffer, ConsoleEntry
from sikulipy.ide.editor import EditorDocument
from sikulipy.ide.explorer import ScriptTreeNode, build_tree
from sikulipy.ide.sidebar import SidebarModel
from sikulipy.ide.statusbar import StatusModel
from sikulipy.ide.toolbar import ToolbarActions


# ---------------------------------------------------------------------------
# Application state container
# ---------------------------------------------------------------------------


class _IDEState:
    """Bundle of model instances shared by the Flet widgets."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.document = EditorDocument()
        self.console = ConsoleBuffer()
        self.status = StatusModel()
        self.sidebar = SidebarModel(self.document)
        self.toolbar = ToolbarActions(
            document=self.document,
            on_status=self.status.set_message,
        )


# ---------------------------------------------------------------------------
# Widget builders
# ---------------------------------------------------------------------------


def _build_toolbar(state: _IDEState, page: ft.Page, refresh: callable) -> ft.Row:
    def _wrap(action):
        def handler(_e):
            try:
                action()
            except Exception as exc:
                state.status.set_message(f"Error: {exc}")
            refresh()
        return handler

    return ft.Row(
        controls=[
            ft.ElevatedButton("Run",     icon=ft.Icons.PLAY_ARROW, on_click=_wrap(state.toolbar.run)),
            ft.ElevatedButton("Stop",    icon=ft.Icons.STOP,       on_click=_wrap(state.toolbar.stop)),
            ft.ElevatedButton("Capture", icon=ft.Icons.CROP,       on_click=_wrap(state.toolbar.begin_capture)),
            ft.ElevatedButton("New",     icon=ft.Icons.ADD,        on_click=_wrap(state.toolbar.new)),
            ft.ElevatedButton("Open",    icon=ft.Icons.FOLDER_OPEN, on_click=lambda _e: None),
            ft.ElevatedButton("Save",    icon=ft.Icons.SAVE,       on_click=_wrap(_save_handler(state))),
        ],
        spacing=8,
    )


def _save_handler(state: _IDEState):
    def _save():
        if state.document.path is None:
            target = state.root / "untitled.py"
            state.document.save(target)
        else:
            state.document.save()
        state.status.set_file(state.document.path, dirty=state.document.dirty)
    return _save


def _node_to_control(node: ScriptTreeNode, depth: int = 0) -> ft.Control:
    icon = {
        "dir": ft.Icons.FOLDER,
        "bundle": ft.Icons.INVENTORY_2,
        "script": ft.Icons.DESCRIPTION,
        "image": ft.Icons.IMAGE,
    }.get(node.kind, ft.Icons.INSERT_DRIVE_FILE)
    row = ft.Row(
        controls=[
            ft.Container(width=depth * 12),
            ft.Icon(icon, size=16),
            ft.Text(node.name, size=13),
        ],
        spacing=4,
    )
    if node.is_leaf:
        return row
    return ft.Column(
        controls=[row, *(_node_to_control(c, depth + 1) for c in node.children)],
        spacing=2,
    )


def _build_explorer(state: _IDEState) -> ft.Container:
    try:
        tree = build_tree(state.root, include_images=True)
        body = _node_to_control(tree)
    except (FileNotFoundError, NotADirectoryError) as exc:
        body = ft.Text(f"(no scripts: {exc})", italic=True, color=ft.Colors.GREY)
    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Text("Script Explorer", weight=ft.FontWeight.BOLD),
                body,
            ],
            scroll=ft.ScrollMode.AUTO,
        ),
        padding=10,
        bgcolor=ft.Colors.GREY_100,
        width=240,
        expand=False,
    )


def _build_editor(state: _IDEState, refresh: callable) -> ft.Container:
    def _on_change(e: ft.ControlEvent) -> None:
        state.document.set_text(e.control.value)
        state.status.set_file(state.document.path, dirty=state.document.dirty)
        refresh()

    return ft.Container(
        content=ft.TextField(
            value=state.document.text,
            on_change=_on_change,
            multiline=True,
            min_lines=20,
            max_lines=40,
            text_style=ft.TextStyle(font_family="monospace", size=14),
            expand=True,
        ),
        padding=10,
        expand=True,
    )


def _build_sidebar(state: _IDEState) -> ft.Container:
    items = state.sidebar.items()
    if not items:
        body: ft.Control = ft.Text(
            "(no patterns)", italic=True, color=ft.Colors.GREY
        )
    else:
        rows = []
        for it in items:
            colour = ft.Colors.BLACK if it.exists else ft.Colors.RED
            rows.append(
                ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.IMAGE, size=16, color=colour),
                        ft.Text(it.name, size=13, color=colour),
                    ],
                    spacing=6,
                )
            )
        body = ft.Column(controls=rows, scroll=ft.ScrollMode.AUTO)
    return ft.Container(
        content=ft.Column(
            controls=[ft.Text("Patterns", weight=ft.FontWeight.BOLD), body]
        ),
        padding=10,
        bgcolor=ft.Colors.GREY_100,
        width=240,
        expand=False,
    )


def _build_console(state: _IDEState) -> ft.Container:
    text = state.console.text() or f"SikuliPy {__version__} — ready."
    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Text("Console", weight=ft.FontWeight.BOLD),
                ft.Text(text, selectable=True, font_family="monospace", size=12),
            ],
            scroll=ft.ScrollMode.AUTO,
        ),
        padding=10,
        bgcolor=ft.Colors.BLACK12,
        height=160,
    )


def _build_statusbar(state: _IDEState) -> ft.Container:
    return ft.Container(
        content=ft.Row(
            controls=[ft.Text(seg, size=12) for seg in state.status.segments()],
            spacing=10,
        ),
        padding=ft.padding.symmetric(horizontal=10, vertical=4),
        bgcolor=ft.Colors.BLUE_GREY_100,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def ide_main(page: ft.Page) -> None:
    page.title = f"SikuliPy IDE {__version__}"
    page.window_width = 1280
    page.window_height = 800
    page.padding = 0

    state = _IDEState(root=Path.cwd())

    # The whole layout is rebuilt on refresh — fine for this skeleton;
    # later phases can switch to fine-grained updates.
    container = ft.Column(expand=True, spacing=0)

    def refresh() -> None:
        container.controls = [
            ft.Container(_build_toolbar(state, page, refresh), padding=10, bgcolor=ft.Colors.GREY_200),
            ft.Row(
                controls=[
                    _build_explorer(state),
                    _build_editor(state, refresh),
                    _build_sidebar(state),
                ],
                expand=True,
                spacing=0,
            ),
            _build_console(state),
            _build_statusbar(state),
        ]
        page.update()

    # Pipe console writes back into the UI.
    state.console.subscribe(lambda _entry: refresh())

    page.add(container)
    refresh()


def main() -> None:
    """Entry point registered as ``sikulipy-ide`` in pyproject.toml."""
    ft.app(target=ide_main)


if __name__ == "__main__":
    main()
