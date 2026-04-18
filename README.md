# SikuliPy

Python port of [OculiX](../Oculix/) (itself a fork of SikuliX1). Visual
automation — if a human can see it on screen, SikuliPy can automate it.
UI shipped as a [Flet](https://flet.dev) application instead of Swing.

> **Status: scaffold.** The package layout, dependency set, and porting
> roadmap are in place. The actual Java → Python port is phased — see
> [`ROADMAP.md`](ROADMAP.md).

## Quick start

```bash
# 1. Create the uv virtual environment (Python 3.14)
uv venv --python 3.14

# 2. Install the project in editable mode
uv pip install -e ".[dev]"

# 3. Run the tests (scaffold smoke tests only so far)
uv run pytest

# 4. Launch the Flet IDE skeleton
uv run sikulipy-ide
```

## Layout

```
src/sikulipy/
├── core/       # Screen, Region, Pattern, Match, Location, Finder, Mouse, Key
├── script/     # exceptions, events, options
├── ocr/        # Tesseract + PaddleOCR
├── android/    # ADB client / device / screen
├── vnc/        # VNC remote screen + SSH tunnel
├── hotkey/     # global hotkey manager (pynput)
├── guide/      # on-screen overlays (SxArrow, SxCallout, ...)
├── runners/    # Python / Robot / PowerShell / AppleScript runners
├── recorder/   # capture user actions → generated script
├── natives/    # platform-specific helpers (pywin32, pyobjc, Xlib)
├── util/       # misc (Highlight, file helpers)
├── ide/        # Flet IDE (editor, explorer, sidebar, toolbar, console)
└── cli.py      # `sikulipy` CLI
```

## License

MIT — same as OculiX / SikuliX.
