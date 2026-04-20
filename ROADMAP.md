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

### Phase 7 — Flet IDE features ✅
Every IDE concern is modelled headlessly so it can be unit-tested without
Flet; `ide/app.py` is a thin view that binds Flet widgets to those models.

* `ide/explorer.py` — `ScriptTreeNode` + `build_tree()` (ports `ScriptExplorer`); classifies dirs / `*.sikuli` bundles / scripts / images; dirs sorted first, then files (case-insensitive); bundles exposed as leaves but can surface their image children
* `ide/editor.py` — `EditorDocument` (ports `EditorPane` state): buffer + cursor + dirty flag, 100-entry undo/redo stack, `insert`/`delete_range`/`set_text`, `open`/`save`, regex-based pattern-reference scanner (`Pattern("x.png")` calls + bare image literals), `pattern_absolute_paths()` resolving against the document folder
* `ide/console.py` — `ConsoleBuffer` ring buffer (deque-backed, configurable cap, subscriber callbacks) + `ConsoleRedirect` context manager swapping `sys.stdout`/`sys.stderr` for forwarding proxies with ANSI (`CSI`/`OSC`) stripping; optional `tee` keeps the original streams attached
* `ide/capture.py` — `CaptureSession` state machine (idle → selecting → captured / cancelled) + `CaptureRect.from_corners` normalising drag direction; `save()` crops the held BGR ndarray via `cv2.imwrite` (guarded so the model still imports on hosts without cv2)
* `ide/toolbar.py` — `ToolbarActions(document, runner, capture, on_status)` bridging buttons to models: `new`/`open`/`save`/`run`/`stop`/`begin_capture`; default `_DefaultRunnerHost` dispatches through `sikulipy.runners.run_file` on a daemon thread; swappable `RunnerHost` Protocol so tests inject a fake
* `ide/sidebar.py` — `SidebarModel` merging pattern references from the editor buffer with user-captured PNGs; `SidebarItem` carries `exists` so the Flet view can grey out broken references
* `ide/statusbar.py` — `StatusModel` with file-label / dirty-marker / cursor / runner / message segments, rendered to a single separator-joined string
* `ide/app.py` — Flet view rebuilt on refresh; toolbar, explorer tree (recursive icon-prefixed rows), editor `TextField` bound to `EditorDocument.set_text`, pattern sidebar, console pane (subscribed to `ConsoleBuffer`), status bar row
* `recorder/__init__.py` — `ActionRecorder` with swappable `InputListener` Protocol (default `_PynputListener`; tests inject a fake); collects click / double-click / right-click / typed-text / wait events (wait auto-inserted when the gap ≥ 0.5 s); optional `screenshotter` + `pattern_dir` crop a PNG around each click; `generate_script()` synthesises runnable `sikulipy` source using `screen.click(Pattern(...))` / `screen.type(...)` / `time.sleep(...)`
* Tests: 30 tests — 23 in `tests/test_phase7_ide.py` (explorer, editor, console, capture, sidebar, statusbar, toolbar with fake runner, smoke-import of `app.py`), 7 in `tests/test_phase7_recorder.py` (fake listener + injected clock, script generation, pattern capture gating). Full suite: **131 passed, 3 skipped** (skips are all host-CPU constraints, not Phase 7).

### Phase 8 — Native helpers + Guides ✅
Both subsystems follow the now-familiar Protocol + lazy-singleton +
test-fake pattern. Platform SDKs (`pywin32`, `pyobjc`, `python-xlib`,
`ewmh`) live behind a new `app` pyproject extra so the core install
stays lean and headless CI never triggers them.

* `natives/_backend.py` — `WindowManagerBackend` Protocol + `get_backend()` / `set_backend()`; auto-resolves `_Win32Backend` (Windows), `_MacOSBackend` (macOS), `_LinuxBackend` (Linux with `DISPLAY`), otherwise `_NullBackend`
* `natives/types.py` — `WindowInfo(pid, title, bounds, handle)` + `NotSupportedError`
* `natives/_win32.py` — `EnumWindows` + `SetForegroundWindow`; PID resolved via `win32process.GetWindowThreadProcessId`
* `natives/_macos.py` — `CGWindowListCopyWindowInfo` + `NSRunningApplication.activateWithOptions_`; launches via `open -a`
* `natives/_linux.py` — `ewmh.EWMH` + `_NET_CLIENT_LIST` enumeration; translates to absolute screen coords via `translate_coords`
* `natives/_null.py` — queries return empty; `close`/`focus` raise `NotSupportedError`; `open` falls back to `subprocess.Popen` so launch-only scripts still work on a headless box
* `natives/app.py` — `App(name, pid)` facade with `open`/`focused`/`find` classmethods, `focus`/`close`/`is_running` instance methods, `windows()` / `window(n)` (returns `Region` lazily to avoid forcing numpy), `all_windows()` class-level snapshot
* `guide/shapes.py` — `Rectangle`, `Arrow`, `Callout`, `Spotlight`, `Text` dataclasses implementing a `Shape` Protocol; `bounds()` + `draw(canvas)` (cv2-guarded so shape objects still import on hosts without it); named-colour table with BGR fallback to red
* `guide/_backend.py` — `GuideBackend` Protocol + `_NullGuideBackend` (records calls, sleeps for blocking `duration`) + `_FletGuideBackend` (frameless, always-on-top, transparent Flet window; composes shapes via `cv2.imencode` → base64 `ft.Image`); auto-resolves based on cv2/flet availability
* `guide/__init__.py` — fluent `Guide` builder: `arrow()`, `rectangle()`, `callout()`, `spotlight()`, `text()`, `clear()`; `show(duration=...)` and `hide()` dispatch through `get_backend()`
* `util/highlight.py` — `Highlight(region, color, duration)` delegates to `Guide.rectangle(...).show()`; context-manager API (`with Highlight(...)`)
* `core/region.py` — `Region.highlight(seconds=2.0, color="red")` convenience method
* `pyproject.toml` — new `app` extra (`pywin32` / `pyobjc-framework-{Cocoa,Quartz}` / `python-xlib` + `ewmh`, each environment-marker-gated)
* Tests: 26 tests in `tests/test_phase8_natives.py` + `tests/test_phase8_guide.py`; routing verified with `RecordingBackend` / `RecordingGuideBackend`; cv2-based pixel assertions gated on `pytest.importorskip("cv2", exc_type=ImportError)` so the suite still passes on CPUs without NumPy 2.x support.

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
