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

import shutil
import subprocess
from pathlib import Path

import flet as ft

from sikulipy import __version__
from sikulipy.ide.capture_overlay import pick_region_and_save
from sikulipy.ide.console import ConsoleBuffer, ConsoleEntry
from sikulipy.ide.editor import EditorDocument
from sikulipy.ide.explorer import ScriptTreeNode, build_tree
from sikulipy.ide.sidebar import SidebarModel
from sikulipy.ide.statusbar import StatusModel
from sikulipy.ide.toolbar import DefaultRunnerHost, ToolbarActions


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
            runner=DefaultRunnerHost(console=self.console),
            on_status=self.status.set_message,
        )
        # Paths of directories currently expanded in the explorer tree.
        # Root is expanded by default so the top-level is immediately
        # visible.
        self.expanded_dirs: set[Path] = {root.resolve()}


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

    def _open_click(_e):
        try:
            folder = _pick_directory(str(state.root))
        except Exception as exc:
            state.status.set_message(f"Picker failed: {exc!r}")
            refresh()
            return
        if not folder:
            state.status.set_message("Open cancelled")
            refresh()
            return
        new_root = Path(folder).resolve()
        state.root = new_root
        state.expanded_dirs = {new_root}
        state.status.set_message(f"Project: {new_root}")
        refresh()

    def _capture_click(_e):
        # Reset the headless session (also flips any "captured" state
        # from a previous run back to "idle") before we take the shot.
        state.toolbar.begin_capture()

        # Hide the IDE window so the overlay isn't fighting it for
        # focus and so it doesn't appear in its own screenshot. We
        # restore it no matter what happens below.
        prev_minimized = page.window.minimized
        page.window.minimized = True
        page.update()

        saved: Path | None = None
        try:
            saved = pick_region_and_save(state.root)
        except Exception as exc:
            state.status.set_message(f"Capture failed: {exc}")
        finally:
            page.window.minimized = prev_minimized
            page.update()

        if saved is None:
            state.status.set_message("Capture cancelled")
        else:
            state.sidebar.add_captured(saved)
            try:
                rel = saved.relative_to(state.root)
            except ValueError:
                rel = saved
            state.status.set_message(f"Captured {rel}")
        refresh()

    return ft.Row(
        controls=[
            ft.ElevatedButton("Run",     icon=ft.Icons.PLAY_ARROW, on_click=_wrap(state.toolbar.run)),
            ft.ElevatedButton("Stop",    icon=ft.Icons.STOP,       on_click=_wrap(state.toolbar.stop)),
            ft.ElevatedButton("Capture", icon=ft.Icons.CROP,       on_click=_capture_click),
            ft.ElevatedButton("New",     icon=ft.Icons.ADD,        on_click=_wrap(state.toolbar.new)),
            ft.ElevatedButton("Open",    icon=ft.Icons.FOLDER_OPEN, on_click=_open_click),
            ft.ElevatedButton("Save",    icon=ft.Icons.SAVE,       on_click=_wrap(_save_handler(state))),
        ],
        spacing=8,
    )


def _pick_directory(initial: str) -> str | None:
    """Show a native folder picker, returning the chosen path or None.

    Flet's built-in ``FilePicker.get_directory_path`` shells out to
    ``zenity`` on Linux; on KDE or any host without zenity installed,
    the call hangs indefinitely. We sidestep Flet entirely and probe
    for a working native helper in this order:

    1. ``kdialog --getexistingdirectory`` (KDE Plasma)
    2. ``zenity --file-selection --directory`` (GNOME / generic)
    3. ``tkinter.filedialog.askdirectory`` (cross-platform Python-only)

    The helpers below all block until the user picks or cancels.
    """
    from sikulipy.util.subprocess_env import native_dialog_env

    env = native_dialog_env()
    if kdialog := shutil.which("kdialog"):
        r = subprocess.run(
            [kdialog, "--getexistingdirectory", initial],
            capture_output=True, text=True, env=env,
        )
        return r.stdout.strip() or None if r.returncode == 0 else None
    if zenity := shutil.which("zenity"):
        r = subprocess.run(
            [zenity, "--file-selection", "--directory",
             f"--filename={initial}/", "--title=Open project folder"],
            capture_output=True, text=True, env=env,
        )
        return r.stdout.strip() or None if r.returncode == 0 else None
    # Tkinter fallback (Windows/macOS/Linux without zenity or kdialog).
    import tkinter
    from tkinter import filedialog
    root = tkinter.Tk()
    root.withdraw()
    try:
        path = filedialog.askdirectory(
            title="Open project folder", initialdir=initial
        )
    finally:
        root.destroy()
    return path or None


def _save_handler(state: _IDEState):
    def _save():
        if state.document.path is None:
            target = state.root / "untitled.py"
            state.document.save(target)
        else:
            state.document.save()
        state.status.set_file(state.document.path, dirty=state.document.dirty)
    return _save


def _node_to_control(
    node: ScriptTreeNode,
    state: _IDEState,
    refresh: callable,
    depth: int = 0,
) -> ft.Control:
    icon = {
        "dir": ft.Icons.FOLDER,
        "bundle": ft.Icons.INVENTORY_2,
        "script": ft.Icons.DESCRIPTION,
        "image": ft.Icons.IMAGE,
    }.get(node.kind, ft.Icons.INSERT_DRIVE_FILE)

    is_dir = node.kind == "dir"
    is_expanded = node.path.resolve() in state.expanded_dirs

    if is_dir:
        chevron = ft.Icon(
            ft.Icons.KEYBOARD_ARROW_DOWN if is_expanded else ft.Icons.KEYBOARD_ARROW_RIGHT,
            size=16,
        )
    else:
        # Leaf nodes get a blank spacer so file names align with dir names.
        chevron = ft.Container(width=16)

    row_content = ft.Row(
        controls=[
            ft.Container(width=depth * 12),
            chevron,
            ft.Icon(icon, size=16),
            ft.Text(node.name, size=13),
        ],
        spacing=4,
    )

    def _on_click(_e, path=node.path.resolve()):
        if path in state.expanded_dirs:
            state.expanded_dirs.discard(path)
        else:
            state.expanded_dirs.add(path)
        refresh()

    def _on_open_file(_e, path=node.path):
        try:
            state.toolbar.open(path)
            state.status.set_file(state.document.path, dirty=False)
        except Exception as exc:
            state.status.set_message(f"Open failed: {exc}")
        refresh()

    if is_dir:
        row: ft.Control = ft.GestureDetector(
            content=row_content,
            on_tap=_on_click,
            mouse_cursor=ft.MouseCursor.CLICK,
        )
    elif node.kind in ("script", "bundle"):
        row = ft.GestureDetector(
            content=row_content,
            on_tap=_on_open_file,
            mouse_cursor=ft.MouseCursor.CLICK,
        )
    else:
        row = row_content

    if not is_dir or not is_expanded:
        return row

    return ft.Column(
        controls=[
            row,
            *(
                _node_to_control(c, state, refresh, depth + 1)
                for c in node.children
            ),
        ],
        spacing=2,
    )


def _build_explorer(state: _IDEState, refresh: callable) -> ft.Container:
    try:
        tree = build_tree(state.root, include_images=True)
        body = _node_to_control(tree, state, refresh)
    except (FileNotFoundError, NotADirectoryError) as exc:
        body = ft.Text(f"(no scripts: {exc})", italic=True, color=ft.Colors.GREY)
    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Text("Script Explorer", weight=ft.FontWeight.BOLD),
                body,
            ],
            scroll=ft.ScrollMode.AUTO,
            alignment=ft.MainAxisAlignment.START,
            horizontal_alignment=ft.CrossAxisAlignment.START,
            expand=True,
        ),
        padding=10,
        bgcolor=ft.Colors.GREY_100,
        width=240,
        expand=False,
    )


def _line_col(text: str, offset: int) -> tuple[int, int]:
    """1-based (line, column) for a caret ``offset`` into ``text``."""
    if offset <= 0:
        return 1, 1
    offset = min(offset, len(text))
    prefix = text[:offset]
    line = prefix.count("\n") + 1
    last_nl = prefix.rfind("\n")
    column = offset - (last_nl + 1) + 1
    return line, column


def _build_editor(
    state: _IDEState,
    refresh: callable,
    refresh_statusbar: callable,
) -> ft.Container:
    # Never do a full layout rebuild in response to typing: that would
    # swap the TextField out of the tree and drop focus. The dirty
    # marker and cursor position both live in the status bar, which
    # updates fine-grained. The pattern sidebar stays stale until some
    # other action (save, open, run) triggers a full refresh — fine
    # trade-off for keeping focus on every keystroke.

    def _update_caret(control: ft.TextField) -> None:
        sel = control.selection
        offset = sel.extent_offset if sel is not None else len(control.value or "")
        line, col = _line_col(control.value or "", offset)
        state.status.set_cursor(line, col)

    def _on_change(e: ft.ControlEvent) -> None:
        state.document.set_text(e.control.value)
        state.status.set_file(state.document.path, dirty=state.document.dirty)
        _update_caret(e.control)
        refresh_statusbar()

    def _on_selection_change(e: ft.ControlEvent) -> None:
        _update_caret(e.control)
        refresh_statusbar()

    return ft.Container(
        content=ft.TextField(
            value=state.document.text,
            on_change=_on_change,
            on_selection_change=_on_selection_change,
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


def _statusbar_row(state: _IDEState) -> ft.Row:
    return ft.Row(
        controls=[ft.Text(seg, size=12) for seg in state.status.segments()],
        spacing=10,
    )


def _build_statusbar(state: _IDEState) -> ft.Container:
    return ft.Container(
        content=_statusbar_row(state),
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
    # later phases can switch to fine-grained updates. The status bar is
    # already fine-grained (see ``refresh_statusbar``) so the editor can
    # update caret position without dropping focus.
    container = ft.Column(expand=True, spacing=0)
    statusbar = _build_statusbar(state)

    def refresh_statusbar() -> None:
        statusbar.content = _statusbar_row(state)
        statusbar.update()

    def refresh() -> None:
        container.controls = [
            ft.Container(_build_toolbar(state, page, refresh), padding=10, bgcolor=ft.Colors.GREY_200),
            ft.Row(
                controls=[
                    _build_explorer(state, refresh),
                    _build_editor(state, refresh, refresh_statusbar),
                    _build_sidebar(state),
                ],
                expand=True,
                spacing=0,
                vertical_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            _build_console(state),
            statusbar,
        ]
        statusbar.content = _statusbar_row(state)
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
