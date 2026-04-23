"""User-facing dialog helpers: ``popup`` / ``popupAsk`` / ``input``.

Mirrors SikuliX's module-level dialog functions. On Linux we probe
``kdialog`` first (KDE), fall back to ``zenity`` (GNOME), then to
Tkinter as a pure-Python fallback. This is the same order used by
:func:`sikulipy.ide.app._pick_directory` and
:func:`sikulipy.ide.capture_overlay._ask_overwrite`; consolidating it
here means user scripts get the same native-dialog experience the IDE
itself does.
"""

from __future__ import annotations

import shutil
import subprocess

from sikulipy.util.subprocess_env import native_dialog_env


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(cmd: list[str], *, capture: bool = True) -> subprocess.CompletedProcess[str]:
    env = native_dialog_env()
    if capture:
        return subprocess.run(cmd, stdout=subprocess.PIPE, text=True, env=env)
    return subprocess.run(cmd, env=env)


def _tk_root():
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
    except tk.TclError:
        pass
    return root


# ---------------------------------------------------------------------------
# popup — informational message
# ---------------------------------------------------------------------------


def popup(message: str, title: str = "SikuliPy") -> None:
    """Show an informational OK dialog. Blocks until dismissed."""
    if kdialog := shutil.which("kdialog"):
        _run([kdialog, "--title", title, "--msgbox", str(message)], capture=False)
        return
    if zenity := shutil.which("zenity"):
        _run([zenity, "--info", f"--title={title}", f"--text={message}"], capture=False)
        return

    from tkinter import messagebox

    root = _tk_root()
    try:
        messagebox.showinfo(title, str(message), parent=root)
    finally:
        root.destroy()


# ---------------------------------------------------------------------------
# popupAsk / popask — yes/no
# ---------------------------------------------------------------------------


def popupAsk(message: str, title: str = "SikuliPy") -> bool:  # noqa: N802 - SikuliX parity
    """Show a Yes/No dialog. Returns True for Yes, False for No/cancel."""
    if kdialog := shutil.which("kdialog"):
        r = _run([kdialog, "--title", title, "--yesno", str(message)], capture=False)
        return r.returncode == 0
    if zenity := shutil.which("zenity"):
        r = _run([zenity, "--question", f"--title={title}", f"--text={message}"])
        return r.returncode == 0

    from tkinter import messagebox

    root = _tk_root()
    try:
        return bool(messagebox.askyesno(title, str(message), parent=root))
    finally:
        root.destroy()


# SikuliX spells this both ways.
popask = popupAsk


# ---------------------------------------------------------------------------
# input / inputText — text entry
# ---------------------------------------------------------------------------


def input(  # noqa: A001 - SikuliX shadows the builtin
    message: str = "",
    title: str = "SikuliPy",
    default: str = "",
    hidden: bool = False,
) -> str | None:
    """Prompt for a line of text. Returns the string, or None on cancel."""
    if kdialog := shutil.which("kdialog"):
        flag = "--password" if hidden else "--inputbox"
        args = [kdialog, "--title", title, flag, str(message)]
        if not hidden:
            args.append(default)
        r = _run(args)
        if r.returncode != 0:
            return None
        return r.stdout.rstrip("\n")
    if zenity := shutil.which("zenity"):
        args = [
            zenity, "--entry",
            f"--title={title}",
            f"--text={message}",
            f"--entry-text={default}",
        ]
        if hidden:
            args.append("--hide-text")
        r = _run(args)
        if r.returncode != 0:
            return None
        return r.stdout.rstrip("\n")

    from tkinter import simpledialog

    root = _tk_root()
    try:
        ask = simpledialog.askstring(
            title, str(message), initialvalue=default,
            show="*" if hidden else None, parent=root,
        )
    finally:
        root.destroy()
    return ask


def inputText(  # noqa: N802 - SikuliX parity
    message: str = "",
    title: str = "SikuliPy",
    default: str = "",
    lines: int = 9,
    width: int = 20,
) -> str | None:
    """Prompt for a multi-line text block. Returns the string, or None on cancel.

    ``lines`` / ``width`` are advisory hints; native dialogs ignore them,
    Tk honours them. SikuliX accepts the same keywords.
    """
    del lines, width  # honoured only by the Tk fallback; accepted for parity
    if kdialog := shutil.which("kdialog"):
        r = _run([kdialog, "--title", title, "--textinputbox", str(message), default])
        if r.returncode != 0:
            return None
        return r.stdout.rstrip("\n")
    if zenity := shutil.which("zenity"):
        r = _run([
            zenity, "--text-info", "--editable",
            f"--title={title}",
        ], capture=True)
        if r.returncode != 0:
            return None
        return r.stdout
    return input(message=message, title=title, default=default)


__all__ = [
    "input",
    "inputText",
    "popask",
    "popup",
    "popupAsk",
]
