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
import time
from contextlib import contextmanager
from pathlib import Path

import flet as ft

from sikulipy import __version__
from sikulipy.ide.capture_overlay import (
    pick_region_and_save,
    surface_frame_provider,
)
from sikulipy.ide.console import ConsoleBuffer, ConsoleEntry
from sikulipy.ide.editor import EditorDocument
from sikulipy.ide.explorer import ScriptTreeNode, build_tree
from sikulipy.ide.lint import Diagnostic, lint_text
from sikulipy.ide.recorder import (
    DESKTOP_ENTRY_KEY,
    DevicePicker,
    RecorderAction,
    RecorderSession,
)
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
        # Installed later by app.main() once the Flet page exists, so the
        # runner-finished callback can refresh the UI from the worker thread.
        self.on_runner_finished: "Callable[[int], None] | None" = None
        runner = DefaultRunnerHost(
            console=self.console,
            on_finished=lambda code: self.on_runner_finished and self.on_runner_finished(code),
        )
        self.toolbar = ToolbarActions(
            document=self.document,
            runner=runner,
            on_status=self.status.set_message,
        )
        # Paths of directories currently expanded in the explorer tree.
        # Root is expanded by default so the top-level is immediately
        # visible.
        self.expanded_dirs: set[Path] = {root.resolve()}
        # Currently-previewed pattern in the sidebar (None == no selection).
        self.selected_pattern: Path | None = None
        # Active recorder session, or None when not recording.
        self.recorder: RecorderSession | None = None
        # Device picker bound to ``self.recorder`` while a session is
        # live; rebuilt every time the recorder is (re)opened.
        self.device_picker: "DevicePicker | None" = None
        # Last-selected tab in the recorder bar; preserved across the
        # full layout rebuilds triggered by Insert Code / refresh().
        self.recorder_tab_index: int = 0
        # Editor TextField + focus flag, populated by ``_build_editor``.
        # The page-level keyboard handler reads them to intercept Tab /
        # Shift+Tab without stealing keys from other inputs.
        self.editor_field: "ft.TextField | None" = None
        self.editor_focused: bool = False
        # X11 window IDs iconified at Run-click time so the script has
        # an unobstructed view of whatever's underneath. Restored from
        # the runner-finished callback. Empty when the IDE is up.
        self.hidden_run_window_ids: list = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_DOCS_URL = "https://sikulix-2014.readthedocs.io/en/latest/"


_HIDE_SETTLE_SECONDS = 0.35
"""Pause after hiding so the WM has actually pulled our window off
screen before mss grabs the framebuffer or the user starts interacting
with whatever's underneath. 300 ms is enough on KWin/GNOME; shorter
values caught the IDE in the screenshot intermittently."""


# Maps a "trigger" substring that recorded code might contain to the
# import line that needs to be present at the top of the file. Add new
# entries here as more recorder actions reference modules outside the
# default ``from sikulipy import *`` star-import.
_IMPORT_TRIGGERS: list[tuple[str, str]] = [
    ("App.", "from sikulipy.natives import App"),
]


def _ensure_session_header(state: "_IDEState", session: "RecorderSession") -> None:
    """Prepend the active recorder surface's imports and setup lines.

    Called once per ``_auto_insert`` so the buffer always carries the
    surface header that the recorded code is going to dispatch through.
    Each line is matched as a substring against the current buffer to
    decide if it's missing — same shape as :func:`_ensure_imports_for`,
    but driven by the surface (``_AndroidSurface.header_setup`` →
    ``screen = ADBScreen.start(serial="...")``) rather than a static
    table. Desktop surfaces emit no setup, so this is a no-op for the
    common path.
    """
    text = state.document.text
    needed_imports = [ln for ln in session.required_imports() if ln not in text]
    needed_setup = [ln for ln in session.required_setup() if ln not in text]
    if not needed_imports and not needed_setup:
        return
    parts: list[str] = []
    if needed_imports:
        parts.append("\n".join(needed_imports))
    if needed_setup:
        # Blank line separating imports from setup keeps the inserted
        # block readable when the caller's file is empty.
        parts.append("\n".join(needed_setup))
    block = "\n\n".join(parts) + "\n"
    insert_at = 0
    if text.startswith("#!"):
        nl = text.find("\n")
        insert_at = nl + 1 if nl != -1 else len(text)
    state.document.insert(block, at=insert_at)
    if state.document.cursor >= insert_at:
        state.document.cursor += len(block)


def _ensure_imports_for(state: "_IDEState", code: str) -> None:
    """Prepend any missing imports the ``code`` snippet relies on.

    Edits ``state.document`` in place. The cursor is bumped forward by
    the number of inserted characters so the subsequent insertion in
    ``_auto_insert`` lands at the original caret position rather than
    mid-import.
    """
    text = state.document.text
    needed: list[str] = []
    for trigger, import_line in _IMPORT_TRIGGERS:
        if trigger in code and import_line not in text:
            needed.append(import_line)
    if not needed:
        return
    block = "\n".join(needed) + "\n"
    # Insert imports at the very top so they're discoverable. If the
    # file already starts with a shebang, slot underneath it.
    insert_at = 0
    if text.startswith("#!"):
        nl = text.find("\n")
        insert_at = nl + 1 if nl != -1 else len(text)
    elif text and not text.startswith("\n"):
        # Make sure the existing first line stays intact below.
        block = block
    state.document.insert(block, at=insert_at)
    if state.document.cursor >= insert_at:
        state.document.cursor += len(block)


def _open_url_external(url: str) -> tuple[bool, str]:
    """Spawn the platform URL handler with cv2's Qt env vars stripped.

    Returns ``(ok, detail)``. ``detail`` is a short error string when
    we couldn't find a launcher or the spawn itself raised — used by
    callers to put something useful in the status bar.

    Why bother instead of ``webbrowser.open``: on Linux ``webbrowser``
    invokes xdg-open via subprocess but inherits the parent's env,
    including the ``QT_QPA_PLATFORM_PLUGIN_PATH`` cv2 sets on import.
    xdg-open shells out to a Qt-based handler (kde-open / Falkon / etc.),
    which then loads xcb from cv2's plugin dir, fails, and exits 0. The
    user sees nothing. Stripping those keys is the documented fix.
    """
    import sys
    from sikulipy.util.subprocess_env import native_dialog_env

    if sys.platform.startswith("linux"):
        candidates = ("xdg-open", "gio", "kde-open")
    elif sys.platform == "darwin":
        candidates = ("open",)
    elif sys.platform.startswith("win"):
        candidates = ("start",)
    else:
        candidates = ("xdg-open",)

    env = native_dialog_env()
    last_err = ""
    for cmd in candidates:
        path = shutil.which(cmd)
        if path is None:
            continue
        try:
            args = [path, "open", url] if cmd == "gio" else [path, url]
            # start=detached; stdin/stdout closed so the launcher doesn't
            # keep our pipes alive after the IDE exits.
            subprocess.Popen(  # noqa: S603 — args are trusted, hard-coded list
                args,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True, ""
        except Exception as exc:
            last_err = f"{cmd}: {exc}"
            continue
    return False, last_err or "no URL launcher found"


def _x11_iconify_by_title(title: str) -> list:
    """Iconify all top-level X11 windows whose WM_NAME contains ``title``.

    Returns the list of window IDs that were iconified, or ``[]`` if
    Xlib is unavailable or no window matched. Caller passes the same
    list back to :func:`_x11_map_by_id` to restore them.

    KWin (and other Linux WMs) frequently ignore Flet's programmatic
    minimize/visible flags for embedded apps, so we go around Flet and
    talk to X11 directly. ICCCM iconify is preferred over ``unmap_window``
    because the WM keeps the window in the task bar / overview, so the
    user can find it again if anything goes wrong.
    """
    try:
        from Xlib import X, Xatom, display
    except ImportError:
        return []
    try:
        d = display.Display()
    except Exception:
        return []
    try:
        root = d.screen().root
        wm_state = d.intern_atom("WM_CHANGE_STATE")
        ICONIC_STATE = 3  # ICCCM §4.1.4
        hidden: list = []

        def walk(win):
            try:
                name = win.get_wm_name()
            except Exception:
                name = None
            if name and title in str(name):
                try:
                    ev = (
                        X.ClientMessage, 0, win, wm_state,
                    )
                    # Use the higher-level send_event helper.
                    from Xlib.protocol import event as _xevent
                    cm = _xevent.ClientMessage(
                        window=win, client_type=wm_state, data=(32, [ICONIC_STATE, 0, 0, 0, 0]),
                    )
                    root.send_event(
                        cm,
                        event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask,
                    )
                    hidden.append(win.id)
                except Exception:
                    pass
            try:
                for child in win.query_tree().children:
                    walk(child)
            except Exception:
                pass

        walk(root)
        d.sync()
        d.close()
        return hidden
    except Exception:
        try:
            d.close()
        except Exception:
            pass
        return []


def _x11_map_by_id(window_ids: list) -> None:
    """Restore previously-iconified windows by ID. Best-effort."""
    if not window_ids:
        return
    try:
        from Xlib import X, display
    except ImportError:
        return
    try:
        d = display.Display()
    except Exception:
        return
    try:
        for wid in window_ids:
            try:
                win = d.create_resource_object("window", wid)
                win.map()  # NormalState; WM will restore from icon
            except Exception:
                continue
        d.sync()
    finally:
        try:
            d.close()
        except Exception:
            pass


@contextmanager
def _ide_hidden(page: ft.Page):
    """Hide the IDE window for the duration of the block.

    Flet's ``window.minimized`` / ``visible`` flags are routinely
    ignored by KWin (and intermittently by other Linux WMs) for
    embedded Flutter apps. The reliable path is to ask X11 directly
    via ICCCM ``WM_CHANGE_STATE`` to iconify every top-level window
    whose title is ``SikuliPy IDE …``. We also flip the Flet flags as
    a best-effort for non-X11 backends.
    """
    win = page.window
    prev_minimized = win.minimized
    prev_visible = getattr(win, "visible", True)
    win.minimized = True
    try:
        win.visible = False
    except Exception:
        pass
    page.update()
    hidden_ids = _x11_iconify_by_title("SikuliPy")
    time.sleep(_HIDE_SETTLE_SECONDS)
    try:
        yield
    finally:
        _x11_map_by_id(hidden_ids)
        try:
            win.visible = prev_visible
        except Exception:
            pass
        win.minimized = prev_minimized
        page.update()


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

    def _run_click(_e):
        # Sikuli scripts drive the *real* desktop, so the IDE has to
        # step out of the way before the script starts clicking — same
        # pattern the recorder/capture flows already use. We hide
        # *before* dispatching to the runner so the script's first
        # action has an unobstructed framebuffer; window IDs are
        # restored from on_finished. _ide_hidden's context-manager
        # form doesn't fit here because the runner returns
        # immediately on a background thread.
        try:
            if state.toolbar.document.path is None:
                state.status.set_message("Save the buffer before running")
                refresh()
                return
            # Best-effort hide. If Xlib is missing or the WM ignores
            # the iconify request, we still run the script — losing
            # the visual is annoying but not fatal.
            state.hidden_run_window_ids = _x11_iconify_by_title("SikuliPy")
            try:
                page.window.minimized = True
            except Exception:
                pass
            page.update()
            time.sleep(_HIDE_SETTLE_SECONDS)
            state.toolbar.run()
        except Exception as exc:
            # Run failed before the runner thread started — restore
            # the IDE so the user can read the error in the status bar.
            _x11_map_by_id(state.hidden_run_window_ids)
            state.hidden_run_window_ids = []
            try:
                page.window.minimized = False
            except Exception:
                pass
            state.status.set_message(f"Run failed: {exc}")
        refresh()

    def _open_folder_click(_e):
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

        saved: Path | None = None
        with _ide_hidden(page):
            try:
                saved = pick_region_and_save(state.root)
            except Exception as exc:
                state.status.set_message(f"Capture failed: {exc}")

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

    def _record_click(_e):
        if state.recorder is None:
            session = RecorderSession()
            picker = DevicePicker(session=session)
            # Best-effort initial refresh so we can decide whether a
            # target prompt is needed. Errors (no adb, no
            # pure-python-adb) are absorbed by ``DevicePicker.refresh``
            # and surfaced via last_error.
            picker.refresh()
            # Only ask the user when there's a real choice. Desktop
            # alone (no Android attached) → start silently on desktop.
            if len(picker.entries) > 1:
                with _ide_hidden(page):
                    chosen = _pick_target_native(
                        picker.entries,
                        selected_key=picker.selected_key,
                    )
                if chosen is None:
                    state.status.set_message("Recording cancelled")
                    refresh()
                    return
                try:
                    picker.select(chosen)
                except Exception as exc:
                    state.status.set_message(f"Device select failed: {exc}")
                    refresh()
                    return
            state.recorder = session
            state.device_picker = picker
            target = "desktop" if picker.selected_key == DESKTOP_ENTRY_KEY else picker.selected_key
            state.status.set_message(f"Recording on {target} — use buttons under the editor")
        else:
            state.recorder.discard()
            state.recorder = None
            state.device_picker = None
            state.status.set_message("Recording cancelled")
        refresh()

    def _docs_click(_e):
        # webbrowser.open returns True on Linux as long as it could
        # *spawn* xdg-open — even when the spawn inherits cv2's
        # QT_QPA_* env vars and xdg-open itself crashes silently. We've
        # been bitten by exactly that elsewhere (see subprocess_env.py).
        # Run xdg-open / open / start ourselves with the cleaned env so
        # the browser actually launches.
        ok, detail = _open_url_external(_DOCS_URL)
        if ok:
            state.status.set_message(f"Opened {_DOCS_URL}")
        else:
            # Last resort: hand off to Flet's launch_url. Linux desktop
            # builds usually no-op here, but it's the right call on web
            # and macOS/Windows builds where url_launcher works.
            try:
                page.launch_url(_DOCS_URL)
                state.status.set_message(f"Opened {_DOCS_URL}")
            except Exception as exc:
                state.status.set_message(f"Open docs failed: {detail or exc}")
        refresh()

    running = state.toolbar.is_running()
    run_color = ft.Colors.GREY if running else ft.Colors.GREEN
    stop_color = ft.Colors.GREEN if running else ft.Colors.GREY
    recording = state.recorder is not None
    record_color = ft.Colors.RED if recording else ft.Colors.GREY

    # Mid-session device controls. Hidden until Record is on, so the
    # toolbar stays compact for users who never touch Android.
    def _devices_switch(_e: ft.ControlEvent) -> None:
        picker = state.device_picker
        if picker is None:
            return
        picker.refresh()
        with _ide_hidden(page):
            chosen = _pick_target_native(
                picker.entries,
                selected_key=picker.selected_key,
                title="Switch recording target",
            )
        if chosen is None:
            return
        try:
            picker.select(chosen)
            target = "desktop" if chosen == DESKTOP_ENTRY_KEY else chosen
            state.status.set_message(f"Recorder target: {target}")
        except Exception as exc:
            state.status.set_message(f"Device select failed: {exc}")
        refresh()

    def _devices_pair(_e: ft.ControlEvent) -> None:
        picker = state.device_picker
        if picker is None:
            return
        # Pre-fill the input with the most recent Wi-Fi address so the
        # user can re-pair after a reboot/disconnect with one Enter.
        # Selected target wins (it's almost always what the user wants
        # back); otherwise fall back to the first non-USB serial.
        default = ""
        selected = next(
            (e for e in picker.entries if e.key == picker.selected_key),
            None,
        )
        if selected and selected.serial and ":" in selected.serial:
            default = selected.serial
        else:
            default = next(
                (e.serial for e in picker.entries if e.serial and ":" in e.serial),
                "",
            )
        with _ide_hidden(page):
            addr = _ask_native_input(
                "host[:port] of the Wi-Fi device:",
                title="Pair Wi-Fi device",
                default=default,
            )
        if not addr:
            return
        try:
            entry = picker.connect_address(addr)
            state.status.set_message(f"Connected: {entry.serial}")
        except Exception as exc:
            state.status.set_message(f"Pair failed: {exc}")
        refresh()

    devices_menu = ft.PopupMenuButton(
        icon=ft.Icons.PHONE_ANDROID,
        tooltip="Recording target / Wi-Fi pairing",
        items=[
            ft.PopupMenuItem(content="Switch target…", on_click=_devices_switch),
            ft.PopupMenuItem(content="Pair Wi-Fi device…", on_click=_devices_pair),
        ],
        visible=recording,
    )

    return ft.Row(
        controls=[
            ft.ElevatedButton(
                "Run",
                icon=ft.Icons.PLAY_ARROW,
                icon_color=run_color,
                on_click=_run_click,
            ),
            ft.ElevatedButton(
                "Stop",
                icon=ft.Icons.STOP,
                icon_color=stop_color,
                on_click=_wrap(state.toolbar.stop),
            ),
            ft.ElevatedButton("Capture", icon=ft.Icons.CROP,       on_click=_capture_click),
            ft.ElevatedButton(
                "Record",
                icon=ft.Icons.FIBER_MANUAL_RECORD,
                icon_color=record_color,
                on_click=_record_click,
            ),
            devices_menu,
            ft.ElevatedButton("New",     icon=ft.Icons.ADD,        on_click=_wrap(state.toolbar.new)),
            ft.ElevatedButton("Open",    icon=ft.Icons.FOLDER_OPEN, on_click=_open_folder_click),
            ft.ElevatedButton("Save",    icon=ft.Icons.SAVE,       on_click=_wrap(_save_handler(state))),
            ft.ElevatedButton("Docs",    icon=ft.Icons.MENU_BOOK,   on_click=_docs_click),
        ],
        spacing=8,
    )


def _ask_native_input(prompt: str, title: str = "SikuliPy", default: str = "") -> str | None:
    """Show a native input dialog (kdialog → zenity → tk). Returns ``None``
    on cancel or when no native helper is available.

    Used by recorder buttons that need a payload while the IDE is
    hidden — a Flet AlertDialog would force the IDE back on top of the
    underlying app the user is recording against.
    """
    from sikulipy.util.subprocess_env import native_dialog_env

    env = native_dialog_env()
    if kdialog := shutil.which("kdialog"):
        r = subprocess.run(
            [kdialog, "--title", title, "--inputbox", prompt, default],
            capture_output=True, text=True, env=env,
        )
        if r.returncode != 0:
            return None
        return r.stdout.strip() or None
    if zenity := shutil.which("zenity"):
        r = subprocess.run(
            [zenity, "--entry", f"--title={title}", f"--text={prompt}",
             f"--entry-text={default}"],
            capture_output=True, text=True, env=env,
        )
        if r.returncode != 0:
            return None
        return r.stdout.strip() or None
    import tkinter
    from tkinter import simpledialog
    root = tkinter.Tk()
    root.withdraw()
    try:
        try:
            root.attributes("-topmost", True)
        except tkinter.TclError:
            pass
        value = simpledialog.askstring(title, prompt, initialvalue=default, parent=root)
    finally:
        root.destroy()
    if value is None:
        return None
    return value.strip() or None


def _pick_target_native(
    entries: "list",
    *,
    selected_key: str,
    title: str = "Select recording target",
) -> str | None:
    """Show a native radiolist (kdialog → zenity → tk) of recorder targets.

    ``entries`` is a list of ``DeviceEntry``. Returns the chosen key, or
    ``None`` if the user cancels the dialog. Falls back to a plain Tk
    Combobox on hosts without kdialog/zenity. Bypassing Flet here keeps
    the dialog on top of the IDE/recording surface and avoids the
    AlertDialog API churn between Flet versions.
    """
    from sikulipy.util.subprocess_env import native_dialog_env

    env = native_dialog_env()
    if kdialog := shutil.which("kdialog"):
        args = [kdialog, "--title", title, "--radiolist", "Choose where to record:"]
        for entry in entries:
            args.extend([entry.key, entry.label, "on" if entry.key == selected_key else "off"])
        r = subprocess.run(args, capture_output=True, text=True, env=env)
        if r.returncode != 0:
            return None
        return r.stdout.strip() or None
    if zenity := shutil.which("zenity"):
        args = [
            zenity, "--list", "--radiolist", f"--title={title}",
            "--text=Choose where to record:",
            "--column=", "--column=Key", "--column=Target",
            "--hide-column=2", "--print-column=2",
        ]
        for entry in entries:
            args.extend([
                "TRUE" if entry.key == selected_key else "FALSE",
                entry.key,
                entry.label,
            ])
        r = subprocess.run(args, capture_output=True, text=True, env=env)
        if r.returncode != 0:
            return None
        return r.stdout.strip() or None
    import tkinter
    from tkinter import ttk
    root = tkinter.Tk()
    root.title(title)
    try:
        root.attributes("-topmost", True)
    except tkinter.TclError:
        pass
    label_to_key = {entry.label: entry.key for entry in entries}
    selected_label = next(
        (e.label for e in entries if e.key == selected_key),
        entries[0].label if entries else "",
    )
    var = tkinter.StringVar(value=selected_label)
    chosen: dict[str, str | None] = {"key": None}
    ttk.Label(root, text="Choose where to record:").pack(padx=12, pady=(12, 4))
    combo = ttk.Combobox(root, textvariable=var, values=list(label_to_key), state="readonly")
    combo.pack(padx=12, pady=4)
    btns = ttk.Frame(root)
    btns.pack(padx=12, pady=12)
    def _ok() -> None:
        chosen["key"] = label_to_key.get(var.get())
        root.destroy()
    def _cancel() -> None:
        chosen["key"] = None
        root.destroy()
    ttk.Button(btns, text="OK", command=_ok).pack(side="left", padx=4)
    ttk.Button(btns, text="Cancel", command=_cancel).pack(side="left", padx=4)
    root.protocol("WM_DELETE_WINDOW", _cancel)
    root.mainloop()
    return chosen["key"]


def _pick_save_file(initial_dir: str, suggested_name: str = "untitled.py") -> str | None:
    """Show a native Save-As dialog; return chosen path or None if cancelled.

    Probes kdialog, zenity, then tk.filedialog — so the IDE stays usable
    on KDE hosts where zenity isn't installed.
    """
    from sikulipy.util.subprocess_env import native_dialog_env

    env = native_dialog_env()
    initial = f"{initial_dir.rstrip('/')}/{suggested_name}"
    if kdialog := shutil.which("kdialog"):
        r = subprocess.run(
            [kdialog, "--getsavefilename", initial, "*.py|Python scripts\n*|All files"],
            capture_output=True, text=True, env=env,
        )
        return r.stdout.strip() or None if r.returncode == 0 else None
    if zenity := shutil.which("zenity"):
        r = subprocess.run(
            [zenity, "--file-selection", "--save", "--confirm-overwrite",
             f"--filename={initial}", "--file-filter=Python scripts | *.py",
             "--title=Save script as"],
            capture_output=True, text=True, env=env,
        )
        return r.stdout.strip() or None if r.returncode == 0 else None
    import tkinter
    from tkinter import filedialog
    root = tkinter.Tk()
    root.withdraw()
    try:
        path = filedialog.asksaveasfilename(
            title="Save script as",
            initialdir=initial_dir,
            initialfile=suggested_name,
            defaultextension=".py",
            filetypes=[("Python scripts", "*.py"), ("All files", "*.*")],
        )
    finally:
        root.destroy()
    return path or None


def _pick_directory(initial: str) -> str | None:
    """Show a native folder picker; return chosen path or None."""
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
            chosen = _pick_save_file(str(state.root))
            if not chosen:
                state.status.set_message("Save cancelled")
                return
            state.document.save(chosen)
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
        "file": ft.Icons.INSERT_DRIVE_FILE,
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


_EDITOR_FONT_SIZE = 14
_EDITOR_LINE_HEIGHT = 1.4  # matches Flet's default; keep gutter rows in lockstep


def _gutter_controls(text: str, diagnostics: list[Diagnostic]) -> list[ft.Control]:
    """Build right-aligned line-number rows, flagging diagnostic lines.

    The gutter is a plain ``Column`` of ``Text`` controls — no scrolling
    of its own. The TextField below grows to match its content, so the
    surrounding scroll view scrolls both panes together.
    """
    line_count = max(1, text.count("\n") + 1)
    flagged = {d.line: d.severity for d in diagnostics}
    rows: list[ft.Control] = []
    for n in range(1, line_count + 1):
        sev = flagged.get(n)
        color = (
            ft.Colors.RED_400
            if sev == "error"
            else ft.Colors.AMBER_700 if sev == "warning"
            else ft.Colors.GREY_500
        )
        weight = ft.FontWeight.BOLD if sev else ft.FontWeight.NORMAL
        rows.append(
            ft.Text(
                str(n),
                color=color,
                weight=weight,
                text_align=ft.TextAlign.RIGHT,
                style=ft.TextStyle(
                    font_family="monospace",
                    size=_EDITOR_FONT_SIZE,
                    height=_EDITOR_LINE_HEIGHT,
                ),
            )
        )
    return rows


def _push_lint_to_status(state: _IDEState, diagnostics: list[Diagnostic]) -> None:
    """Summarize ``diagnostics`` into the status model's lint segment.

    The first diagnostic (errors prioritised over warnings, both already
    line-sorted) is shown next to the counts so the user sees one
    actionable hint without having to look elsewhere.
    """
    errors = sum(1 for d in diagnostics if d.severity == "error")
    warnings = sum(1 for d in diagnostics if d.severity == "warning")
    first = ""
    for d in diagnostics:
        if d.severity == "error":
            first = f"{d.line}:{d.column} {d.message}"
            break
    if not first and diagnostics:
        d = diagnostics[0]
        first = f"{d.line}:{d.column} {d.message}"
    state.status.set_lint(errors, warnings, first)


def _build_editor(
    state: _IDEState,
    refresh: callable,
    refresh_statusbar: callable,
    refresh_sidebar: callable,
) -> ft.Container:
    # Never do a full layout rebuild in response to typing: that would
    # swap the TextField out of the tree and drop focus. The dirty
    # marker and cursor position both live in the status bar, which
    # updates fine-grained. The pattern sidebar stays stale until some
    # other action (save, open, run) triggers a full refresh — fine
    # trade-off for keeping focus on every keystroke.

    initial_diagnostics = lint_text(state.document.text)
    _push_lint_to_status(state, initial_diagnostics)

    gutter = ft.Column(
        controls=_gutter_controls(state.document.text, initial_diagnostics),
        spacing=0,
        tight=True,
        horizontal_alignment=ft.CrossAxisAlignment.END,
    )

    def _refresh_lint_views(text: str) -> None:
        diags = lint_text(text)
        gutter.controls = _gutter_controls(text, diags)
        _push_lint_to_status(state, diags)
        # Fine-grained updates only — never rebuild the editor row, or
        # the TextField loses focus mid-keystroke. The status bar is
        # repainted by the caller via refresh_statusbar().
        try:
            gutter.update()
        except (AssertionError, AttributeError):
            # Not yet attached to a page (e.g. first build during tests).
            pass

    def _update_caret(control: ft.TextField) -> None:
        sel = control.selection
        offset = sel.extent_offset if sel is not None else len(control.value or "")
        # Persist the caret offset on the document model so anything
        # outside the editor (recorder auto-insert, programmatic edits)
        # uses the user's actual cursor position rather than the stale
        # default of 0.
        state.document.cursor = max(0, min(offset, len(control.value or "")))
        line, col = _line_col(control.value or "", offset)
        state.status.set_cursor(line, col)

    def _maybe_select_pattern_under_caret(control: ft.TextField) -> bool:
        """Update ``state.selected_pattern`` from the caret position.

        Returns True iff the selection changed and the sidebar should be
        re-rendered.
        """
        sel = control.selection
        if sel is None:
            return False
        offset = sel.extent_offset
        match = state.document.pattern_at_offset(offset)
        if match is None:
            return False
        if match == state.selected_pattern:
            return False
        # Only auto-switch to a real file; leave a missing literal alone
        # so the user's manually-selected thumbnail isn't blanked out by
        # typo'd path under the caret.
        if not match.exists():
            return False
        state.selected_pattern = match
        return True

    def _on_change(e: ft.ControlEvent) -> None:
        state.document.set_text(e.control.value)
        state.status.set_file(state.document.path, dirty=state.document.dirty)
        _update_caret(e.control)
        _refresh_lint_views(e.control.value or "")
        if _maybe_select_pattern_under_caret(e.control):
            refresh_sidebar()
        refresh_statusbar()

    def _on_selection_change(e: ft.ControlEvent) -> None:
        _update_caret(e.control)
        if _maybe_select_pattern_under_caret(e.control):
            refresh_sidebar()
        refresh_statusbar()

    def _on_focus(_e: ft.ControlEvent) -> None:
        state.editor_focused = True

    def _on_blur(_e: ft.ControlEvent) -> None:
        state.editor_focused = False

    text_field = ft.TextField(
        value=state.document.text,
        on_change=_on_change,
        on_selection_change=_on_selection_change,
        on_focus=_on_focus,
        on_blur=_on_blur,
        multiline=True,
        text_style=ft.TextStyle(
            font_family="monospace",
            size=_EDITOR_FONT_SIZE,
            height=_EDITOR_LINE_HEIGHT,
        ),
        border=ft.InputBorder.NONE,
        content_padding=ft.padding.symmetric(horizontal=8, vertical=0),
        expand=True,
    )
    state.editor_field = text_field

    # The gutter Column grows with line count; without clipping the
    # numbers spill below the editor and overlap the console pane. Wrap
    # it in a scrollable Container so the column can be taller than the
    # visible area without overflowing it. Scroll sync with the
    # TextField is a separate (hard) problem — for now the gutter
    # scrolls independently if the user reaches for it.
    gutter_pane = ft.Container(
        content=ft.Column(
            controls=[gutter],
            scroll=ft.ScrollMode.HIDDEN,
            spacing=0,
            tight=True,
            expand=True,
        ),
        width=42,
        padding=ft.padding.only(top=0, right=6, left=2),
        bgcolor=ft.Colors.GREY_100,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
    )
    editor_row = ft.Row(
        controls=[
            gutter_pane,
            ft.Container(content=text_field, expand=True),
        ],
        spacing=0,
        vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        expand=True,
    )

    return ft.Container(
        content=editor_row,
        # Small vertical breathing room so line 1 isn't flush against
        # the toolbar and the last visible line isn't flush against
        # the console divider.
        padding=ft.padding.symmetric(horizontal=0, vertical=8),
        expand=True,
    )


def _build_sidebar(state: _IDEState, refresh: callable) -> ft.Container:
    items = state.sidebar.items()
    # Drop a stale selection if the previously-picked pattern is no longer
    # in the project (e.g. user opened a different folder).
    item_paths = {it.path for it in items}
    if state.selected_pattern is not None and state.selected_pattern not in item_paths:
        state.selected_pattern = None

    if not items:
        body: ft.Control = ft.Text(
            "(no patterns)", italic=True, color=ft.Colors.GREY
        )
    else:
        rows = []
        for it in items:
            colour = ft.Colors.BLACK if it.exists else ft.Colors.RED
            is_selected = state.selected_pattern == it.path
            row = ft.Row(
                controls=[
                    ft.Icon(ft.Icons.IMAGE, size=16, color=colour),
                    ft.Text(it.name, size=13, color=colour),
                ],
                spacing=6,
            )

            def _on_select(_e, path=it.path, exists=it.exists):
                state.selected_pattern = path if exists else None
                refresh()

            rows.append(
                ft.Container(
                    content=ft.GestureDetector(
                        content=row,
                        on_tap=_on_select,
                        mouse_cursor=ft.MouseCursor.CLICK,
                    ),
                    bgcolor=ft.Colors.BLUE_100 if is_selected else None,
                    padding=ft.padding.symmetric(horizontal=4, vertical=2),
                    border_radius=3,
                )
            )
        body = ft.Column(controls=rows, scroll=ft.ScrollMode.AUTO, spacing=2)

    # Thumbnail underneath: read the bytes and pass them as src_base64
    # because Flet's desktop runtime cannot resolve arbitrary filesystem
    # paths through Image.src. Always reserve the slot — even an empty
    # placeholder — so the column layout doesn't shift on selection.
    if state.selected_pattern is not None and state.selected_pattern.exists():
        try:
            data = state.selected_pattern.read_bytes()
            preview_image: ft.Control = ft.Image(
                src=data,
                fit=ft.BoxFit.CONTAIN,
            )
            preview_label = state.selected_pattern.name
        except Exception as exc:  # pragma: no cover - defensive
            preview_image = ft.Text(f"(preview failed: {exc})",
                                    size=11, color=ft.Colors.RED)
            preview_label = state.selected_pattern.name
    else:
        preview_image = ft.Text(
            "(select a pattern to preview)",
            italic=True, color=ft.Colors.GREY, size=11,
        )
        preview_label = ""

    preview_pane = ft.Column(
        controls=[
            ft.Divider(height=1, color=ft.Colors.GREY_400),
            ft.Text(preview_label or " ", size=12, italic=True),
            ft.Container(
                content=preview_image,
                bgcolor=ft.Colors.WHITE,
                border=ft.border.all(1, ft.Colors.GREY_400),
                alignment=ft.Alignment.CENTER,
                expand=True,
            ),
        ],
        spacing=4,
    )

    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Text("Patterns", weight=ft.FontWeight.BOLD),
                ft.Container(content=body, expand=True),
                preview_pane,
            ],
            spacing=6,
            expand=True,
        ),
        padding=10,
        bgcolor=ft.Colors.GREY_100,
        width=240,
        expand=False,
    )


_IMAGE_ACTIONS: list[tuple[str, RecorderAction]] = [
    ("Click", RecorderAction.CLICK),
    ("DblClick", RecorderAction.DBLCLICK),
    ("RClick", RecorderAction.RCLICK),
    ("Wait", RecorderAction.WAIT),
    ("WaitVanish", RecorderAction.WAIT_VANISH),
]
_IMAGE_TWO_PATTERN_ACTIONS: list[tuple[str, RecorderAction]] = [
    ("Drag&Drop", RecorderAction.DRAG_DROP),
    ("Swipe", RecorderAction.SWIPE),
]
_IMAGE_PAYLOAD_ACTIONS: list[tuple[str, RecorderAction, str]] = [
    ("Wheel", RecorderAction.WHEEL, "Wheel direction (up/down) and steps, e.g. 'down 3':"),
]
_APP_ACTIONS: list[tuple[str, RecorderAction, str]] = [
    # (label, action, prompt)
    ("Launch App", RecorderAction.LAUNCH_APP, "App name or path:"),
    ("Close App", RecorderAction.CLOSE_APP, "App name to close:"),
]
_TEXT_ACTIONS: list[tuple[str, RecorderAction, str]] = [
    ("Text.Click", RecorderAction.TEXT_CLICK, "Text to click:"),
    ("Text.Wait", RecorderAction.TEXT_WAIT, "Text to wait for:"),
    ("Text.Exists", RecorderAction.TEXT_EXISTS, "Text to check:"),
]
_KEYBOARD_ACTIONS: list[tuple[str, RecorderAction, str]] = [
    ("Type", RecorderAction.TYPE, "Text to type:"),
    ("Key Combo", RecorderAction.KEY_COMBO, "Key combo (e.g. Ctrl+Shift+c):"),
    ("Pause", RecorderAction.PAUSE, "Pause seconds:"),
]


def _prompt_payload(page: ft.Page, prompt: str, on_ok) -> None:
    """Ask the user for a string and call ``on_ok(value)``.

    Uses a native dialog (kdialog → zenity → tk) instead of Flet's
    AlertDialog because the Flet ``page.open(dlg)`` API isn't available
    in every Flet release we support, and the native helpers are
    already used elsewhere in the IDE for consistency.
    """
    value = _ask_native_input(prompt, title="Recorder")
    on_ok(value or "")


def _build_recorder_bar(state: _IDEState, page: ft.Page, refresh: callable) -> ft.Container | None:
    if state.recorder is None:
        return None
    session = state.recorder

    def _capture_for_session() -> Path | None:
        """Run :func:`pick_region_and_save` against whatever surface the
        session currently targets. The desktop path still hides the IDE
        so it doesn't end up in the screenshot; Android captures grab
        the device's own framebuffer over ADB and don't need that."""
        provider = None
        is_desktop = session.surface.name == "desktop"
        if not is_desktop:
            provider = surface_frame_provider(session.surface)
        if is_desktop:
            with _ide_hidden(page):
                return pick_region_and_save(state.root, frame_provider=provider)
        return pick_region_and_save(state.root, frame_provider=provider)

    def _record_pattern(action: RecorderAction):
        def handler(_e):
            try:
                session.workflow.begin(action)
            except RuntimeError as exc:
                state.status.set_message(f"Recorder busy: {exc}")
                refresh()
                return

            saved: Path | None = None
            try:
                try:
                    saved = _capture_for_session()
                except Exception as exc:
                    state.status.set_message(f"Capture failed: {exc}")
            finally:
                session.workflow.finish()

            if saved is None:
                state.status.set_message("Capture cancelled")
            else:
                session.record_pattern(action, saved)
                state.sidebar.add_captured(saved)
                msg = _auto_insert() or f"Recorded {action.value}: {saved.name}"
                state.status.set_message(msg)
            refresh()

        return handler

    def _capture_one(label: str) -> Path | None:
        saved: Path | None = None
        try:
            saved = _capture_for_session()
        except Exception as exc:
            state.status.set_message(f"Capture failed ({label}): {exc}")
        return saved

    def _record_two_patterns(action: RecorderAction):
        def handler(_e):
            try:
                session.workflow.begin(action)
            except RuntimeError as exc:
                state.status.set_message(f"Recorder busy: {exc}")
                refresh()
                return
            try:
                state.status.set_message(f"{action.value}: capture SOURCE region")
                src = _capture_one("source")
                if src is None:
                    state.status.set_message("Capture cancelled (source)")
                    return
                state.status.set_message(f"{action.value}: capture DESTINATION region")
                dst = _capture_one("destination")
                if dst is None:
                    state.status.set_message("Capture cancelled (destination)")
                    return
                session.record_two_patterns(action, src, dst)
                state.sidebar.add_captured(src)
                state.sidebar.add_captured(dst)
                msg = _auto_insert() or (
                    f"Recorded {action.value}: {src.name} → {dst.name}"
                )
                state.status.set_message(msg)
            finally:
                session.workflow.finish()
                refresh()

        return handler

    def _record_payload_hidden(action: RecorderAction, prompt: str):
        """Like ``_record_payload`` but hides the IDE while prompting,
        so the user can see/interact with the underlying window —
        used by the Image tab's payload-only buttons (e.g. Wheel)."""
        def handler(_e):
            try:
                session.workflow.begin(action)
            except RuntimeError as exc:
                state.status.set_message(f"Recorder busy: {exc}")
                refresh()
                return
            try:
                with _ide_hidden(page):
                    value = _ask_native_input(prompt, title=action.value)
                if not value:
                    state.status.set_message("Recording step skipped (empty input)")
                    return
                try:
                    session.record_payload(action, value)
                    msg = _auto_insert() or f"Recorded {action.value}"
                    state.status.set_message(msg)
                except (ValueError, Exception) as exc:
                    state.status.set_message(f"Record failed: {exc}")
            finally:
                session.workflow.finish()
                refresh()

        return handler

    def _record_payload(action: RecorderAction, prompt: str):
        def handler(_e):
            def _on_ok(value: str) -> None:
                value = value.strip()
                if not value:
                    state.status.set_message("Recording step skipped (empty input)")
                    refresh()
                    return
                try:
                    session.record_payload(action, value)
                    msg = _auto_insert() or f"Recorded {action.value}"
                    state.status.set_message(msg)
                except (ValueError, Exception) as exc:
                    state.status.set_message(f"Record failed: {exc}")
                refresh()

            _prompt_payload(page, prompt, _on_ok)

        return handler

    def _auto_insert() -> str | None:
        """Finalize the pending session lines and inject them at the
        editor caret. Returns a short status string describing what was
        inserted, or ``None`` if there was nothing to insert. Called
        right after every successful record_* so the user sees code
        appear immediately and the queue stays drained.
        """
        if not session.lines():
            return None
        if state.document.path is not None:
            target_dir = state.document.path.parent
        else:
            target_dir = state.root
        try:
            code, moved = session.finalize(target_dir)
        except Exception as exc:
            return f"Insert failed: {exc}"
        n_lines = len([ln for ln in code.splitlines() if ln])
        # Make sure any imports the recorded code needs are present at
        # the top of the file, before computing the caret position
        # (since adding the import shifts existing offsets). Surface
        # header (``screen = ADBScreen.start(...)`` etc.) goes in
        # first, then substring-keyed imports for the snippet itself.
        _ensure_session_header(state, session)
        _ensure_imports_for(state, code)
        # Insert at the editor's caret. Prepend a newline if the caret
        # is mid-line, append one if anything follows the insertion.
        existing = state.document.text
        pos = max(0, min(state.document.cursor, len(existing)))
        if pos > 0 and existing[pos - 1] != "\n":
            code = "\n" + code
        if pos < len(existing) and not code.endswith("\n"):
            code = code + "\n"
        state.document.insert(code, at=pos)
        state.status.set_file(state.document.path, dirty=state.document.dirty)
        # Drain so the next record doesn't re-insert the same lines.
        while session.remove_last() is not None:
            pass
        return f"Inserted {n_lines} line(s); {len(moved)} pattern(s) → {target_dir}"

    def _close(_e):
        session.discard()
        state.recorder = None
        state.device_picker = None
        state.status.set_message("Recorder closed")
        refresh()

    def _payload_row(specs: list[tuple[str, RecorderAction, str]]) -> ft.Row:
        return ft.Row(
            controls=[
                ft.ElevatedButton(label, on_click=_record_payload(action, prompt))
                for label, action, prompt in specs
            ],
            spacing=6,
            wrap=True,
        )

    image_tab = ft.Row(
        controls=[
            *(
                ft.ElevatedButton(label, on_click=_record_pattern(action))
                for label, action in _IMAGE_ACTIONS
            ),
            *(
                ft.ElevatedButton(label, on_click=_record_two_patterns(action))
                for label, action in _IMAGE_TWO_PATTERN_ACTIONS
            ),
            *(
                ft.ElevatedButton(label, on_click=_record_payload_hidden(action, prompt))
                for label, action, prompt in _IMAGE_PAYLOAD_ACTIONS
            ),
        ],
        spacing=6,
        wrap=True,
    )
    app_tab = _payload_row(_APP_ACTIONS)
    text_tab = _payload_row(_TEXT_ACTIONS)
    keyboard_tab = _payload_row(_KEYBOARD_ACTIONS)

    def _pad(content: ft.Control) -> ft.Container:
        return ft.Container(content=content, padding=ft.padding.symmetric(vertical=8))

    tab_labels = [
        ft.Tab(label="Application"),
        ft.Tab(label="Image"),
        ft.Tab(label="Text"),
        ft.Tab(label="Keyboard"),
    ]
    tab_panes = [
        _pad(app_tab),
        _pad(image_tab),
        _pad(text_tab),
        _pad(keyboard_tab),
    ]
    def _on_tab_change(e: ft.ControlEvent) -> None:
        try:
            state.recorder_tab_index = int(e.control.selected_index)
        except (TypeError, ValueError):
            pass

    initial_tab = max(0, min(state.recorder_tab_index, len(tab_labels) - 1))
    tabs = ft.Tabs(
        length=len(tab_labels),
        selected_index=initial_tab,
        on_change=_on_tab_change,
        content=ft.Column(
            controls=[
                ft.TabBar(tabs=tab_labels),
                ft.Container(
                    content=ft.TabBarView(controls=tab_panes),
                    expand=True,
                ),
            ],
            spacing=0,
            expand=True,
        ),
        expand=True,
    )

    footer = ft.Row(
        controls=[
            ft.Container(expand=True),
            ft.ElevatedButton(
                "Close",
                icon=ft.Icons.CLOSE,
                icon_color=ft.Colors.RED,
                on_click=_close,
            ),
        ],
        spacing=6,
    )

    return ft.Container(
        content=ft.Column(
            controls=[tabs, footer],
            spacing=4,
            expand=True,
        ),
        padding=10,
        bgcolor=ft.Colors.AMBER_50,
        border=ft.border.all(1, ft.Colors.AMBER_300),
        left=0,
        right=0,
        top=0,
        bottom=0,
    )


def _build_console(
    state: _IDEState, refresh_statusbar: "Callable[[], None] | None" = None
) -> ft.Container:
    text = state.console.text() or f"SikuliPy {__version__} — ready."

    def _set_status(msg: str) -> None:
        state.status.set_message(msg)
        if refresh_statusbar is not None:
            try:
                refresh_statusbar()
            except (AssertionError, AttributeError):
                pass

    def _copy_console(e: ft.ControlEvent) -> None:
        # Always copy the live buffer, not the snapshot baked into the
        # rendered Text — the buffer keeps growing while this view is up.
        # Flet 0.84's Page.set_clipboard is gone (Clipboard().set is now
        # async); pyperclip is the project's established sync route
        # (also used by Region.paste) and works without spinning up
        # Flet's service plumbing.
        from sikulipy.core.env import Env

        payload = state.console.text()
        if not payload:
            _set_status("Console is empty")
            return
        try:
            Env.set_clipboard(payload)
        except Exception as exc:
            _set_status(f"Copy failed: {exc}")
            return
        _set_status(f"Copied {len(payload)} chars from Console")

    header = ft.Row(
        controls=[
            ft.Text("Console", weight=ft.FontWeight.BOLD),
            ft.IconButton(
                icon=ft.Icons.CONTENT_COPY,
                tooltip="Copy console output to clipboard",
                icon_size=16,
                on_click=_copy_console,
            ),
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    return ft.Container(
        content=ft.Column(
            controls=[
                header,
                ft.Text(text, selectable=True, font_family="monospace", size=12),
            ],
            scroll=ft.ScrollMode.AUTO,
        ),
        padding=10,
        bgcolor=ft.Colors.BLACK12,
        height=160,
    )


def _statusbar_row(state: _IDEState) -> ft.Row:
    left = ft.Row(
        controls=[ft.Text(seg, size=12) for seg in state.status.segments()],
        spacing=10,
        tight=True,
    )
    # Color the lint segment based on counts so a glance at the right
    # edge is enough to see the file's health.
    if state.status.lint_errors:
        lint_color = ft.Colors.RED_700
    elif state.status.lint_warnings:
        lint_color = ft.Colors.AMBER_800
    else:
        lint_color = ft.Colors.GREEN_700
    right = ft.Row(
        controls=[
            ft.Text(seg, size=12, color=lint_color)
            for seg in state.status.right_segments()
        ],
        spacing=10,
        tight=True,
    )
    return ft.Row(
        controls=[left, right],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        expand=True,
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

    def _on_keyboard(e: ft.KeyboardEvent) -> None:
        # Swallow Tab / Shift+Tab while the editor's TextField holds
        # focus and translate them into indent / dedent edits. Without
        # this Flet's default focus-traversal moves keyboard focus to
        # the next/previous control on every Tab.
        if e.key != "Tab":
            return
        if not state.editor_focused or state.editor_field is None:
            return
        if e.ctrl or e.alt or e.meta:
            return
        field = state.editor_field
        sel = field.selection
        text = field.value or ""
        if sel is None:
            offset = len(text)
            start = end = offset
        else:
            start = min(sel.base_offset, sel.extent_offset)
            end = max(sel.base_offset, sel.extent_offset)
        # Sync the document with whatever's currently in the widget;
        # otherwise undo history loses an entry on quick Tab presses.
        state.document.set_text(text)
        if e.shift:
            new_start, new_end = state.document.dedent_selection(start, end)
        else:
            new_start, new_end = state.document.indent_selection(start, end)
        field.value = state.document.text
        # Restore the (now-shifted) selection so the user can keep
        # pressing Tab to indent further.
        field.selection = ft.TextSelection(
            base_offset=new_start, extent_offset=new_end
        )
        state.document.cursor = new_end
        state.status.set_file(state.document.path, dirty=state.document.dirty)
        line, col = _line_col(state.document.text, new_end)
        state.status.set_cursor(line, col)
        try:
            field.focus()
            field.update()
        except (AssertionError, AttributeError):
            pass
        refresh_statusbar()

    page.on_keyboard_event = _on_keyboard

    # The whole layout is rebuilt on refresh — fine for this skeleton;
    # later phases can switch to fine-grained updates. The status bar is
    # already fine-grained (see ``refresh_statusbar``) so the editor can
    # update caret position without dropping focus.
    container = ft.Column(expand=True, spacing=0)
    statusbar = _build_statusbar(state)
    # Stable wrapper so we can swap only the sidebar's content when the
    # caret moves over an image literal — no full layout rebuild, no
    # focus loss in the editor.
    sidebar_wrapper = ft.Container()

    def refresh_statusbar() -> None:
        statusbar.content = _statusbar_row(state)
        statusbar.update()

    def refresh_sidebar() -> None:
        sidebar_wrapper.content = _build_sidebar(state, refresh)
        sidebar_wrapper.update()

    def refresh() -> None:
        # Layout: toolbar on top, then [Explorer | Editor] in a row that
        # expands to fill the available height, then a full-width Console
        # below them. Explorer's bottom therefore aligns with editor's
        # bottom (both end where the console starts).
        # The recorder bar — when active — is a Stack overlay anchored to
        # the right portion of the console so it spans only the editor's
        # width while the console behind it still starts at the IDE's
        # left edge.
        explorer_pane = _build_explorer(state, refresh)
        editor_pane = _build_editor(
            state, refresh, refresh_statusbar, refresh_sidebar
        )
        editor_row = ft.Row(
            controls=[explorer_pane, editor_pane],
            expand=True,
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        )

        console_pane = _build_console(state, refresh_statusbar)
        recorder_bar = _build_recorder_bar(state, page, refresh)
        if recorder_bar is None:
            bottom_pane: ft.Control = console_pane
        else:
            # Stack: console fills the full bottom; recorder bar sits on
            # top, indented from the left by the explorer's width so it
            # only covers the area beneath the editor.
            recorder_bar.left = 240
            recorder_bar.right = 0
            recorder_bar.top = 0
            recorder_bar.bottom = 0
            bottom_pane = ft.Stack(
                controls=[console_pane, recorder_bar],
                height=160,
            )

        left_column = ft.Column(
            controls=[
                ft.Container(_build_toolbar(state, page, refresh), padding=10, bgcolor=ft.Colors.GREY_200),
                editor_row,
                bottom_pane,
            ],
            expand=True,
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )

        sidebar_wrapper.content = _build_sidebar(state, refresh)
        container.controls = [
            ft.Row(
                controls=[
                    ft.Container(content=left_column, expand=True),
                    sidebar_wrapper,
                ],
                expand=True,
                spacing=0,
                vertical_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            statusbar,
        ]
        statusbar.content = _statusbar_row(state)
        page.update()

    # Pipe console writes back into the UI.
    state.console.subscribe(lambda _entry: refresh())

    def _on_finished(code: int) -> None:
        name = state.document.path.name if state.document.path else "script"
        if code == 0:
            state.status.set_message(f"Finished {name} (exit 0)")
        else:
            state.status.set_message(f"Finished {name} with errors (exit {code})")
        # Restore any windows we iconified for the run. on_finished is
        # called from the runner thread; X11 calls inside _x11_map_by_id
        # are fine off the main thread, but Flet's window.minimized must
        # be touched only after page.update — we let refresh() handle it.
        if state.hidden_run_window_ids:
            _x11_map_by_id(state.hidden_run_window_ids)
            state.hidden_run_window_ids = []
        try:
            page.window.minimized = False
        except Exception:
            pass
        refresh()

    state.on_runner_finished = _on_finished

    page.add(container)
    refresh()


def main() -> None:
    """Entry point registered as ``sikulipy-ide`` in pyproject.toml."""
    ft.app(target=ide_main)


if __name__ == "__main__":
    main()
