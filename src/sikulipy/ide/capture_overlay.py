"""Interactive capture overlay — Tk-backed drag-rectangle selector.

The headless state model lives in :mod:`sikulipy.ide.capture`. This
module glues it to a real UI so the IDE's Capture button can produce a
PNG on disk. We use Tk (not Flet) because we need a short-lived
fullscreen click-through-ish window, which Flet does not expose, and
because Tk ships with Python on every platform we target.

Flow:

    pick_region_and_save(root_dir)
        -> grabs full-screen BGR screenshot via mss
        -> shows fullscreen Tk overlay with the screenshot as background
        -> user drags a rectangle (Esc / right-click cancels)
        -> prompts for a filename via simpledialog
        -> writes {root_dir}/assets/{name}.png via PIL (no cv2 dependency)
        -> returns the saved Path, or None if the user cancelled

The IDE window is expected to be iconified/withdrawn by the caller
before invoking this, and restored afterwards, so the overlay is not
fighting the Flet window for keyboard focus.
"""

from __future__ import annotations

from pathlib import Path

from sikulipy.ide.capture import CaptureRect


def _grab_fullscreen():
    """Return (PIL.Image RGB, virtual-bounding-box dict) for all monitors."""
    import mss
    from PIL import Image

    with mss.mss() as sct:
        # monitor 0 is the virtual union of all screens.
        mon = sct.monitors[0]
        raw = sct.grab(mon)
    # mss gives BGRA; PIL expects RGB. .rgb on mss.ScreenShot is
    # already the correctly-ordered RGB bytes.
    img = Image.frombytes("RGB", raw.size, raw.rgb)
    return img, mon


def _run_overlay(bg_image) -> CaptureRect | None:
    """Show a fullscreen Tk overlay over ``bg_image`` and return the drag rect.

    Returns ``None`` if the user cancels (Esc or right-click) or the
    drag is degenerate. Coordinates are in the virtual-screen space
    matching ``bg_image`` (top-left = (0, 0)).
    """
    import tkinter as tk
    from PIL import ImageTk

    root = tk.Tk()
    root.title("SikuliPy capture")
    # Overridedirect removes window decorations; attributes -fullscreen
    # + topmost keeps it above the IDE on every WM we care about.
    try:
        root.attributes("-fullscreen", True)
    except tk.TclError:
        # Some WMs refuse fullscreen; fall back to geometry.
        root.geometry(f"{bg_image.width}x{bg_image.height}+0+0")
        root.overrideredirect(True)
    try:
        root.attributes("-topmost", True)
    except tk.TclError:
        pass
    root.configure(cursor="crosshair", bg="black")

    canvas = tk.Canvas(
        root, highlightthickness=0, bg="black",
        width=bg_image.width, height=bg_image.height,
    )
    canvas.pack(fill="both", expand=True)

    photo = ImageTk.PhotoImage(bg_image)
    canvas.create_image(0, 0, image=photo, anchor="nw")
    # A dim veil so the selection clearly pops against the frozen shot.
    canvas.create_rectangle(
        0, 0, bg_image.width, bg_image.height,
        fill="black", stipple="gray25", outline="",
    )

    state: dict = {
        "anchor": None,
        "rect_id": None,
        "result": None,
    }

    def _cancel(_e=None) -> None:
        state["result"] = None
        root.destroy()

    def _on_press(e: "tk.Event") -> None:
        state["anchor"] = (e.x_root, e.y_root)
        if state["rect_id"] is not None:
            canvas.delete(state["rect_id"])
        state["rect_id"] = canvas.create_rectangle(
            e.x, e.y, e.x, e.y, outline="#00bfff", width=2,
        )

    def _on_drag(e: "tk.Event") -> None:
        if state["anchor"] is None or state["rect_id"] is None:
            return
        ax, ay = state["anchor"]
        # Canvas coords are window-local; anchor is screen-space. Compute
        # the canvas-local anchor from winfo_rootx/y.
        off_x = root.winfo_rootx()
        off_y = root.winfo_rooty()
        canvas.coords(state["rect_id"], ax - off_x, ay - off_y, e.x, e.y)

    def _on_release(e: "tk.Event") -> None:
        if state["anchor"] is None:
            _cancel()
            return
        ax, ay = state["anchor"]
        rect = CaptureRect.from_corners(ax, ay, e.x_root, e.y_root)
        state["result"] = None if rect.is_empty else rect
        root.destroy()

    root.bind("<Escape>", _cancel)
    root.bind("<Button-3>", _cancel)
    canvas.bind("<ButtonPress-1>", _on_press)
    canvas.bind("<B1-Motion>", _on_drag)
    canvas.bind("<ButtonRelease-1>", _on_release)

    root.focus_force()
    root.mainloop()
    # Keep a reference to photo until after mainloop returns (GC-safety).
    del photo
    return state["result"]


def _ask_filename(default: str = "capture") -> str | None:
    """Prompt for a filename (no extension). Returns None on cancel."""
    import tkinter as tk
    from tkinter import simpledialog

    root = tk.Tk()
    root.withdraw()
    try:
        name = simpledialog.askstring(
            "Save pattern",
            "Filename (without extension):",
            initialvalue=default,
            parent=root,
        )
    finally:
        root.destroy()
    if name is None:
        return None
    name = name.strip()
    return name or None


def _ask_overwrite(target: Path) -> str | None:
    """Ask what to do when ``target`` already exists.

    Returns one of ``"overwrite"``, ``"rename"``, or ``None`` (cancel).
    ``"rename"`` means the caller should pick a non-colliding ``…-N.png``
    name; ``"overwrite"`` replaces the existing file.

    Probes native helpers in the same order as
    :func:`sikulipy.ide.app._pick_directory` (kdialog → zenity → tk)
    because Tk's own ``messagebox`` window tends to appear behind other
    windows on KDE when its parent is ``withdraw()``-ed, making the
    dialog effectively invisible.
    """
    import shutil
    import subprocess

    prompt = (
        f"{target.name} already exists in {target.parent}.\n\n"
        "Overwrite the existing file?\n"
        "  Yes     → overwrite\n"
        "  No      → save with a numeric suffix (e.g. -1.png)\n"
        "  Cancel  → discard the capture"
    )

    # kdialog: --warningyesnocancel gives us three buttons. Return codes
    # are 0 = Yes, 1 = No, 2 = Cancel (matches KDE convention).
    if kdialog := shutil.which("kdialog"):
        r = subprocess.run(
            [kdialog, "--title", "File exists", "--warningyesnocancel", prompt],
        )
        if r.returncode == 0:
            return "overwrite"
        if r.returncode == 1:
            return "rename"
        return None

    # zenity has no native 3-button dialog; emulate one with --question
    # and custom button labels. Return codes: 0 = Overwrite (ok-label),
    # 1 = Rename (cancel-label), 5 = timeout/closed → treat as cancel.
    # We use --extra-button to add the third option; zenity prints the
    # extra-button label on stdout when clicked.
    if zenity := shutil.which("zenity"):
        r = subprocess.run(
            [
                zenity, "--question", "--title=File exists",
                f"--text={prompt}",
                "--ok-label=Overwrite",
                "--cancel-label=Cancel",
                "--extra-button=Rename",
            ],
            capture_output=True, text=True,
        )
        if r.stdout.strip() == "Rename":
            return "rename"
        if r.returncode == 0:
            return "overwrite"
        return None

    # Tk fallback. askyesnocancel only has Yes/No/Cancel (no custom
    # labels), so the prompt above spells out the mapping.
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.withdraw()
    # Force the dialog above other windows — withdrawn-parent messageboxes
    # otherwise get hidden behind the overlay/IDE on some Linux WMs.
    try:
        root.attributes("-topmost", True)
    except tk.TclError:
        pass
    try:
        answer = messagebox.askyesnocancel(
            "File exists", prompt, parent=root,
        )
    finally:
        root.destroy()
    if answer is None:
        return None
    return "overwrite" if answer else "rename"


def _safe_stem(name: str) -> str:
    """Strip path separators and any trailing .png so we always land on disk."""
    base = Path(name).name  # drop any directory components
    if base.lower().endswith(".png"):
        base = base[:-4]
    return base or "capture"


def pick_region_and_save(project_root: Path) -> Path | None:
    """Run the full capture flow; return the saved PNG path, or None.

    Raises only for genuine environment failures (no display, mss/PIL
    missing). User cancellation at any step returns ``None``.
    """
    from PIL import Image

    bg, mon = _grab_fullscreen()
    rect = _run_overlay(bg)
    if rect is None:
        return None

    name = _ask_filename()
    if name is None:
        return None
    stem = _safe_stem(name)

    # Rect is in virtual-screen coords; convert to bg-image coords by
    # subtracting the monitor offset (usually 0,0 but not on multi-mon).
    left = rect.x - int(mon["left"])
    top = rect.y - int(mon["top"])
    right = left + rect.w
    bottom = top + rect.h
    # Clamp to image bounds just in case.
    left = max(0, min(left, bg.width))
    top = max(0, min(top, bg.height))
    right = max(left, min(right, bg.width))
    bottom = max(top, min(bottom, bg.height))
    if right - left <= 0 or bottom - top <= 0:
        return None

    crop = bg.crop((left, top, right, bottom))
    assets = Path(project_root).resolve() / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    target = assets / f"{stem}.png"
    # Collision: ask the user whether to overwrite, rename (auto-suffix),
    # or cancel. Silently writing a ``…-N.png`` would surprise users who
    # expected the name they typed; silently overwriting would destroy
    # an earlier capture.
    if target.exists():
        choice = _ask_overwrite(target)
        if choice is None:
            return None
        if choice == "rename":
            i = 1
            while target.exists():
                target = assets / f"{stem}-{i}.png"
                i += 1
    crop.save(target, format="PNG")
    return target
