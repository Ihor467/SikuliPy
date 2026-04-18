"""Flet IDE entry point.

This is a deliberately minimal skeleton — three panes, a toolbar, a status
bar. Real editing, script execution, capture overlay, and the pattern
sidebar are stubs for Phase 7.

Run::

    uv run sikulipy-ide
    # or
    uv run python -m sikulipy.ide.app
"""

from __future__ import annotations

import flet as ft

from sikulipy import __version__


def _build_toolbar(page: ft.Page) -> ft.Row:
    def _stub(name: str):
        def handler(_e):
            page.snack_bar = ft.SnackBar(ft.Text(f"{name}: not implemented (Phase 7)"))
            page.snack_bar.open = True
            page.update()
        return handler

    return ft.Row(
        controls=[
            ft.ElevatedButton("Run",     icon=ft.Icons.PLAY_ARROW, on_click=_stub("Run")),
            ft.ElevatedButton("Stop",    icon=ft.Icons.STOP,       on_click=_stub("Stop")),
            ft.ElevatedButton("Capture", icon=ft.Icons.CROP,       on_click=_stub("Capture")),
            ft.ElevatedButton("New",     icon=ft.Icons.ADD,        on_click=_stub("New")),
            ft.ElevatedButton("Open",    icon=ft.Icons.FOLDER_OPEN, on_click=_stub("Open")),
            ft.ElevatedButton("Save",    icon=ft.Icons.SAVE,       on_click=_stub("Save")),
        ],
        spacing=8,
    )


def _build_explorer() -> ft.Container:
    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Text("Script Explorer", weight=ft.FontWeight.BOLD),
                ft.Text("(tree view — Phase 7)", italic=True, color=ft.Colors.GREY),
            ]
        ),
        padding=10,
        bgcolor=ft.Colors.GREY_100,
        width=220,
        expand=False,
    )


def _build_editor() -> ft.Container:
    return ft.Container(
        content=ft.TextField(
            value=(
                "# SikuliPy script\n"
                "from sikulipy import Screen, Pattern\n\n"
                "s = Screen.get_primary()\n"
                "s.click(Pattern('button.png').similar(0.85))\n"
            ),
            multiline=True,
            min_lines=20,
            max_lines=40,
            text_style=ft.TextStyle(font_family="monospace", size=14),
            expand=True,
        ),
        padding=10,
        expand=True,
    )


def _build_sidebar() -> ft.Container:
    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Text("Patterns", weight=ft.FontWeight.BOLD),
                ft.Text("(captured images — Phase 7)", italic=True, color=ft.Colors.GREY),
            ]
        ),
        padding=10,
        bgcolor=ft.Colors.GREY_100,
        width=240,
        expand=False,
    )


def _build_console() -> ft.Container:
    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Text("Console", weight=ft.FontWeight.BOLD),
                ft.Text(f"SikuliPy {__version__} — ready.", selectable=True),
            ]
        ),
        padding=10,
        bgcolor=ft.Colors.BLACK12,
        height=140,
    )


def _build_statusbar() -> ft.Container:
    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Text(f"SikuliPy {__version__}", size=12),
                ft.Text(" · ", size=12),
                ft.Text("Python 3.14", size=12),
                ft.Text(" · ", size=12),
                ft.Text("Flet IDE (skeleton)", size=12, italic=True),
            ]
        ),
        padding=ft.padding.symmetric(horizontal=10, vertical=4),
        bgcolor=ft.Colors.BLUE_GREY_100,
    )


def ide_main(page: ft.Page) -> None:
    page.title = f"SikuliPy IDE {__version__}"
    page.window_width = 1280
    page.window_height = 800
    page.padding = 0

    page.add(
        ft.Column(
            controls=[
                ft.Container(_build_toolbar(page), padding=10, bgcolor=ft.Colors.GREY_200),
                ft.Row(
                    controls=[_build_explorer(), _build_editor(), _build_sidebar()],
                    expand=True,
                    spacing=0,
                ),
                _build_console(),
                _build_statusbar(),
            ],
            expand=True,
            spacing=0,
        )
    )


def main() -> None:
    """Entry point registered as ``sikulipy-ide`` in pyproject.toml."""
    ft.app(target=ide_main)


if __name__ == "__main__":
    main()
