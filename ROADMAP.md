# SikuliPy porting roadmap

A full 1:1 port of OculiX (609 Java files, ~120K LOC delta over SikuliX1)
is not realistic in one pass. This document breaks the work into phases
that each deliver something runnable. Every phase ends with passing
tests.

## Dependency choices

| Java dependency         | Python replacement                           |
|-------------------------|----------------------------------------------|
| OpenCV (Apertix)        | `opencv-python` (optionally `opencv-contrib-python`) |
| Java AWT Robot          | `pynput` + `pyautogui` fallback              |
| Swing IDE               | **Flet**                                     |
| jcraft/jsch             | `paramiko` + `sshtunnel`                     |
| TigerVNC / VNCClient    | `vncdotool` (Twisted-based, first pass)      |
| jadb (ADB client)       | `pure-python-adb` or raw socket client       |
| Tesseract (Tess4J)      | `pytesseract`                                |
| PaddleOCR (HTTP)        | `paddleocr` in-process + optional HTTP       |
| Jython / JRuby runners  | dropped — not relevant in a Python host      |
| tulskiy/keymaster       | `pynput.keyboard.GlobalHotKeys`              |
| Native WinUtil.dll      | `pywin32` / `ctypes`                         |
| MacUtil.m               | `pyobjc` / Quartz                            |
| LinuxSupport            | `python-xlib` / `ewmh` / `pywayland`         |

## Phases

### Phase 0 — Scaffold ✅
* uv venv on Python 3.14
* `pyproject.toml` with base + optional extras
* Package tree under `src/sikulipy/` with stubbed modules
* Flet IDE skeleton (`uv run sikulipy-ide`)
* Smoke tests

### Phase 1 — Core visual engine ✅ *(implemented, tests gated on CPU ≥ x86-64-v2)*
Goal reached: `Screen.get_primary().find(pattern)` returns a real `Match`.

| Java source                                        | Python target                             |
|----------------------------------------------------|-------------------------------------------|
| `org/sikuli/script/Location.java`                  | `sikulipy/core/location.py` ✅             |
| `org/sikuli/script/Offset.java`                    | `sikulipy/core/offset.py` ✅               |
| `org/sikuli/script/Region.java` (~3000 LOC)        | `sikulipy/core/region.py` ✅ (find family) |
| `org/sikuli/script/Screen.java`                    | `sikulipy/core/screen.py` ✅ (mss)         |
| `org/sikuli/script/Image.java` + `ImagePath.java`  | `sikulipy/core/image.py` ✅                |
| `org/sikuli/script/Pattern.java`                   | `sikulipy/core/pattern.py` ✅              |
| `org/sikuli/script/Match.java` + `Matches.java`    | `sikulipy/core/match.py` ✅                |
| `org/sikuli/script/Finder.java`                    | `sikulipy/core/finder.py` ✅ (matchTemplate + greedy NMS) |
| `org/sikuli/script/Element.java`                   | `sikulipy/core/element.py` ✅              |
| `org/sikuli/script/ScreenImage.java`               | `sikulipy/core/image.py` ✅                |

**Known host caveat.** NumPy 2.x wheels require a CPU that implements the
x86-64-v2 baseline (SSE4.2 + POPCNT). On older hardware (e.g. pre-2009
Xeons), `import numpy` raises a `RuntimeError`. The test suite detects
this and skips numpy-dependent tests; the scaffold + pure-Python tests
still run. Use a newer machine, Python 3.12 + NumPy 1.26, or build NumPy
from source to exercise Phase 1.

**Risks:** multi-monitor DPI scaling on Windows & Wayland capture
permissions. `mss` handles both but Wayland may need `pipewire` fallback.

### Phase 2 — Input + hotkeys ✅
* `core/_input_backend.py` — swappable backend protocol (pynput implementation + test fake)
* `core/mouse.py` — `Mouse.at/move/click/double_click/right_click/middle_click/down/up/drag_drop/wheel`
* `core/keyboard.py` — full SikuliX-compatible `Key.*` constants (arrows, F1-F15, modifiers, printscreen, ...) + `KeyModifier` bitmask + `Key.type/press/release/hotkey` with literal/special tokeniser
* `core/region.py` — `click`, `double_click`, `right_click`, `hover`, `drag_drop`, `type`, `paste` all wired; Pattern target resolution honours `target_offset` and `wait_after`
* `core/env.py` — clipboard via `pyperclip`
* `hotkey/manager.py` — `HotkeyManager.register/unregister/clear/stop` on `pynput.keyboard.GlobalHotKeys`; `translate()` converts SikuliPy key + modifier bitmask to pynput hotkey strings (`<ctrl>+<shift>+a`)
* Tests: 18 tests in `tests/test_phase2_input.py` using fake backends — all green on any host (no CPU dependency).

### Phase 3 — OCR ✅
* `ocr/types.py` — shared `Word` dataclass (bbox + confidence + line/block)
* `ocr/_backend.py` — swappable `OcrBackend` protocol + `get_ocr()` / `set_ocr()`
* `ocr/tesseract.py` — `TesseractBackend` via `pytesseract.image_to_data`, normalises confidence to 0..1
* `ocr/paddle.py` — `PaddleOCR` with two modes: in-process `paddleocr` and HTTP (OculiX-compatible endpoint). Parity helpers (`recognize`, `parse_texts`, `parse_text_with_confidence`, `find_text_coordinates`) mirror the Java `PaddleOCRClient` API.
* `ocr/engine.py` — `OCR` facade: `read`, `read_words`, `read_lines`, `find_text`, `find_all_text`, `find_word(ignore_case=...)`
* `core/region.py` — `text()`, `words()`, `find_text()`, `find_all_text()`, `has_text()` with region-offset → absolute screen coordinates
* Tests: 15 tests in `tests/test_phase3_ocr.py`, all using a fake backend — no Tesseract binary or NumPy needed.

### Phase 4 — Android via ADB ✅
* `android/_backend.py` — swappable `AdbClientBackend`/`AdbDeviceBackend` Protocol (pure-python-adb default + test fake)
* `android/client.py` — `ADBClient` (`devices`/`device`/`connect`) + `ADBDevice` (`tap`/`swipe`/`long_press`/`input_text`/`key_event`/`screencap`/`size`)
* `android/screen.py` — `ADBScreen` as a `Region` subclass; `_capture_bgr` uses `screencap`, `click`/`double_click`/`right_click`/`drag_drop`/`type`/`paste` dispatch via ADB; Pattern targets resolved via `find()` and `targetOffset`
* `find_text_coordinates(needle)` bridges to OCR for Java parity with `ADBScreen.findTextCoordinates`
* Tests: 18 tests in `tests/test_phase4_android.py` using a recording fake — no adb server or device needed.

### Phase 5 — VNC + SSH ✅
* `vnc/_backend.py` — swappable `VncConnector`/`VncBackend` Protocol (vncdotool default + test fake) with RFB button-mask bookkeeping
* `vnc/xkeysym.py` — full X11 keysym table (auto-extracted from `XKeySym.java`) + `keysym_name()` reverse lookup
* `vnc/screen.py` — `VNCScreen` as a `Region` subclass; `_capture_bgr` pulls framebuffer, `click`/`double_click`/`right_click`/`middle_click`/`hover`/`drag_drop`/`wheel` translate to RFB pointer events with button masks, `type`/`paste`/`key_up_all` send X11 keysyms with auto-shift on US layout; Pattern targets resolved via `find()` with `targetOffset`; `start()` reuses per-host:port singletons like the Java version
* `vnc/ssh.py` — `SSHTunnel` port of `com.sikulix.util.SSHTunnel`; swappable `TunnelOpener` (sshtunnel/paramiko default + test fake), context-manager API, password / private-key auth, `open_auto_port` for ephemeral local bind
* Tests: 24 tests in `tests/test_phase5_vnc.py` using recording fakes — no RFB server or SSH daemon needed.

### Phase 6 — Script runners ✅
* `runners/base.py` — `Runner` ABC + `Options(args, work_dir, env, silent)` + module-level registry (`register`/`runner_for`/`runner_by_name`/`run_file`/`run_string`); URLs with a `proto://` prefix are rejected just like `AbstractLocalFileScriptRunner.canHandle`
* `runners/_subprocess.py` — swappable `Launcher` Protocol (real `subprocess.run` default + test recorder) shared by the shell runners
* `runners/python_runner.py` — in-process `runpy.run_path` for `.py` and `.sikuli` bundles; handles `SystemExit`, honours `silent`; pushes the script directory onto `sys.path` **and** `ImagePath` so `Pattern("btn.png")` resolves next to the script; tolerant of hosts where the numpy/opencv import fails
* `runners/powershell_runner.py` — `powershell.exe` / `pwsh` with Sikuli's flag set (`-ExecutionPolicy Unrestricted -NonInteractive -NoLogo -NoProfile -WindowStyle Hidden -File`)
* `runners/applescript_runner.py` — `osascript` for `.applescript`/`.scpt`/`.script`; macOS-only
* `runners/bash_runner.py` — `bash`/`sh` for `.sh`/`.bash`; POSIX-only
* `runners/robot_runner.py` — Robot Framework via `robot.run_cli(..., exit=False)`; `is_supported()` reflects whether the `runners` extra is installed
* Built-ins auto-registered at import time; order: Python, PowerShell, AppleScript, Bash, Robot
* Tests: 25 tests in `tests/test_phase6_runners.py` (24 passing + 1 host-skipped). Registry dispatch, PythonRunner in-process exec (`sys.argv`, `SystemExit`, bundle), subprocess runners verified via a recording launcher — no real PowerShell / osascript / bash needed on the host.

### Phase 7 — Flet IDE features
* Tree-based `ScriptExplorer`
* Pattern capture overlay (replaces `OverlayCapturePrompt.java`)
* Inline pattern thumbnails in the editor (likely via embedded Monaco/CodeMirror in a `WebView`)
* Console pane with stdout/stderr redirection
* Recorder (`recorder/`) producing ready-to-run scripts

### Phase 8 — Native helpers + Guides
* Window management (`App.java`) per-platform
* `guide/` overlays (SxArrow, SxCallout, SxSpotlight) as transparent
  Flet windows or Tk overlays

## Out of scope (for now)

* MCP module — Java-specific, superseded by Python MCP SDKs
* Jython / JRuby — irrelevant in a Python host
* The embedded `jcraft/jsch`, `jadb`, `keymaster`, and `jxgrabkey`
  third-party forks — all replaced by Python equivalents

## Module-map quick lookup

```
org.sikuli.script.*           -> sikulipy.core + sikulipy.script
org.sikuli.hotkey.*           -> sikulipy.hotkey
org.sikuli.vnc.*              -> sikulipy.vnc
org.sikuli.android.*          -> sikulipy.android
org.sikuli.guide.*            -> sikulipy.guide
org.sikuli.util.*             -> sikulipy.util
org.sikuli.natives.*          -> sikulipy.natives
org.sikuli.support.recorder.* -> sikulipy.recorder
org.sikuli.script.runners.*   -> sikulipy.runners
org.sikuli.ide.*              -> sikulipy.ide   (Flet, not Swing)
com.sikulix.ocr.*             -> sikulipy.ocr
com.sikulix.util.SSHTunnel    -> sikulipy.vnc.ssh
com.sikulix.tigervnc.*        -> sikulipy.vnc   (wrapped by vncdotool)
```
