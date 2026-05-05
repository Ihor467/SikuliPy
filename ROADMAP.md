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
| Tesseract (Tess4J)      | `pytesseract` (default)                      |
| PaddleOCR (HTTP)        | `paddleocr` in-process + optional HTTP (via `ocr` extra) |
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

### Phase 1 — Core visual engine ✅
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

#### Phase 7.1 — Editor polish ✅
Iterative UX improvements layered on top of the Phase 7 IDE without
breaking the headless-models contract. Added on the `zenity` branch.

* `ide/lint.py` — new headless module: `Diagnostic` dataclass + `lint_text()` running `ast.parse` first (single, well-located `SyntaxError`) then `pyflakes.api.check` for undefined names / unused imports. Returns line/column/severity records sorted by position; gracefully degrades to syntax-only when pyflakes isn't importable.
* `ide/editor.py` — `EditorDocument.indent_selection()` / `dedent_selection()`: snapshot for undo, mutate the buffer per touched line, return the adjusted `(start, end)` so the caller can restore the selection. Dedent handles 4-space, partial-space, and tab indents; no-op when nothing strippable; selections ending exactly on a newline don't bleed into the next line.
* `ide/statusbar.py` — `StatusModel.set_lint(errors, warnings, first)` + `lint_label()` + `right_segments()`. Lint counts and the first issue render right-aligned at the status-bar edge in red / amber / green depending on severity.
* `ide/app.py`:
  * Editor pane wraps the `TextField` in a `Row` with a left line-number gutter (`Container` with `clip_behavior=HARD_EDGE` + scrollable inner `Column` so the gutter can't overflow into the console pane). Diagnostic lines are flagged in red / amber.
  * `_refresh_lint_views()` runs on every keystroke, updates the gutter via fine-grained `gutter.update()` (never rebuilds the editor row, so `TextField` focus survives), and pushes counts into `StatusModel`.
  * Page-level `on_keyboard_event` intercepts Tab / Shift+Tab when the editor's `TextField` has focus (`on_focus`/`on_blur` track focus, the field registers itself on `_IDEState.editor_field`). Handler calls `EditorDocument.indent_selection` / `dedent_selection`, restores the selection via `ft.TextSelection`, refocuses, refreshes the status bar — no more focus escaping to the toolbar.
  * Toolbar gains a **Docs** button that opens `https://sikulix-2014.readthedocs.io/en/latest/` via `webbrowser.open()` (Flet's `page.launch_url` silently no-ops on Linux desktop; kept as fallback).
  * Editor container gets 8 px vertical padding so line 1 isn't flush against the toolbar and the bottom doesn't kiss the console divider.
* Tests: 14 new tests in `tests/test_phase7_ide.py` (6 lint behaviours + 8 indent/dedent cases). Phase 7 file: **44 passed**.

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

### Phase 9 — Recorder ↔ Android integration ✅
Shipped: open the recorder, pick an attached ADB device (USB) or
connect over Wi-Fi via the host:port field, and every captured pattern
/ payload is bound to that device's framebuffer instead of the host
screen. Insert & Close prepends `from sikulipy.android.screen import
ADBScreen` and a `screen = ADBScreen.start(serial=...)` (or
`ADBScreen.connect("ip:port")`) so the saved snippet runs unchanged.

* `recorder/surface.py` — `TargetSurface` Protocol, `_DesktopSurface`, `_AndroidSurface`, `_FakeSurface`, `default_surface()`.
* `recorder/codegen.py` — surface-aware dispatch; desktop emits `wait(...).click()`, Android emits `screen.click(...)`.
* `recorder/devices.py` — headless `DevicePicker` with `refresh()` / `select()` / `connect_address()`. Errors absorbed (no `pure-python-adb`, no adb server) so the recorder still runs on plain desktops.
* `recorder/workflow.py` — `RecorderAction.{BACK,HOME,RECENTS}` android-only verbs; `applies_on(surface_name)` rejects mismatches at codegen time.
* `ide/capture_overlay.py:surface_frame_provider` bridges a surface's BGR frame to the Tk overlay; non-desktop captures skip the IDE-hide step.
* `ide/app.py` — recorder bar gains a Target/Refresh/Connect row; `_ensure_session_header` injects the surface's `header_imports()` + `header_setup()` once per script during `_auto_insert`.
* Tests: 25 codegen + 12 picker + 4 overlay + 5 finalize + 11 surface = 57 new (`tests/test_phase9_*.py`).

Below is the original step-by-step plan, kept for reference.

Goal: let the Record button drive a tablet/phone the same way it drives
the desktop today. The user picks a device once, then every "Click /
Wait / Type / Drag" action targets the device's framebuffer instead of
the host screen, and the saved snippet runs against `ADBScreen` rather
than `Screen`.

Design constraints:

* Reuse the existing recorder workflow (`RecorderAction`, `RecorderSession`, `PythonGenerator`) — no parallel UI.
* Stay headless-testable: the device is a `TargetSurface` Protocol with `_DesktopSurface` (current behaviour) and `_AndroidSurface` implementations + a `_FakeSurface` for tests. Nothing in `recorder/` touches `cv2` or `adb` directly.
* Don't load the `android` extra unless the user picks Android in the recorder. Lazy import + Protocol-resolved factory.
* Code generation switches by surface, not by per-action flags. A single recording is bound to one surface for its whole lifetime.

#### Step 1 — Target surface abstraction
* `ide/recorder/surface.py` (new) — `TargetSurface` Protocol with:
  * `screenshot() -> Path` (writes a PNG to the recorder temp dir, returns the path; the existing capture-overlay flow is built on this).
  * `bounds() -> tuple[int, int, int, int]` (x, y, w, h) so the overlay knows where to draw the picker.
  * `header_imports() -> list[str]` (extra `import` lines the generator's header should emit).
  * `name: str` (`"desktop"` / `"android"`) — recorded in `RecordedLine` and used by codegen to pick the dispatch verb.
* `ide/recorder/surface.py:_DesktopSurface` — wraps the current `mss` + capture-overlay path. No behavioural change vs today.
* `ide/recorder/surface.py:_AndroidSurface` — wraps an `ADBScreen`; `screenshot()` calls `device.screencap_png()` and writes it; `bounds()` is `(0, 0, w, h)`.
* `RecorderSession.__init__` gains `surface: TargetSurface = _DesktopSurface()`. `generator.header()` is replaced by `surface.header_imports() + generator.header()` so an Android recording starts with `from sikulipy.android.screen import ADBScreen` + `screen = ADBScreen.start()`.

#### Step 2 — Surface-aware code generation
* `recorder/codegen.py:GenInput` gains `surface: str = "desktop"`.
* `PythonGenerator.generate` routes through a surface dispatch table:
  * Desktop → emits today's `wait(Pattern(...), t).click()` / `dragDrop(...)` / `type(...)`.
  * Android → emits `screen.click(Pattern(...))` / `screen.drag_drop(...)` / `screen.type(...)` / `screen.swipe(src, dst, duration_ms=…)` (already supported by `ADBScreen`).
* Actions without an Android equivalent (`LAUNCH_APP`, `CLOSE_APP`) get rejected at record time when `surface == "android"`, with the reason surfaced in the recorder bar's status line. `KEY_COMBO` falls back to `screen.key_event(...)` for special keys; modifier combos are unsupported on Android and get the same rejection.
* New action: `BACK` / `HOME` / `RECENTS` emitted only on Android. They take no payload, expand to `screen.device.key_event("KEYCODE_BACK")` etc. Action enum gets a `surface_only: str | None` attribute (None = both, `"android"` = Android only) so the recorder bar can hide the buttons that don't apply.

#### Step 3 — Device picker UI
* New top-level toolbar control in the recorder bar: a `Dropdown` listing **Desktop** + every detected ADB device (label = `serial · model`, model fetched lazily via `getprop ro.product.model`). Default is **Desktop** so the existing flow is unchanged for users who never plug in a device.
* Refresh button next to the dropdown re-runs `ADBClient().devices()`. New devices show up without restarting the IDE.
* Selecting a device calls `RecorderSession.set_surface(_AndroidSurface(device))`. Existing recorded lines are dropped (with a confirmation in the recorder bar) because they were written against the old surface.
* If the user types an IP into the dropdown's free-form field (e.g. `192.168.1.5:5555`), the picker calls `ADBClient.connect(...)` first and adds the resulting device.
* The toolbar's existing **Capture** button stays desktop-only. Recorder-driven captures route through the surface so when Android is selected they hit `screencap_png` instead of `mss`.

#### Step 4 — Capture overlay against device frames
* `ide/capture_overlay.pick_region_and_save` currently grabs the desktop with `mss`. Refactor it to take an injected `frame_provider: Callable[[], np.ndarray]` (default = current `mss` path). When Android is selected the recorder hands it `lambda: device.screencap().bitmap`.
* Overlay window stays a desktop Flet window — there's no reason to mirror the device. The picker shows the device frame as a static backdrop and the user drags a rectangle over it. Coordinates are reported in device pixels (frame already is device-native).
* Edge case: device DPI / orientation can change mid-recording. Re-grab the frame on each new pattern, never cache.

#### Step 5 — Finalize: write a runnable script
* `RecorderSession.finalize` already moves PNGs next to the script. Extend it to:
  * Prepend `surface.header_imports()` to the joined source.
  * For Android: insert a single `screen = ADBScreen.start()` (or `.connect("…")` if the recording was bound to a Wi-Fi address) right after the imports, and rewrite every action call to use `screen` as the receiver.
  * Inject a `Settings.image_path = str(Path(__file__).parent / "patterns")` so the generated script finds the captured PNGs when run from anywhere.
* Bundle layout for Android recordings: `foo_android.sikuli/foo_android.py` + a sibling `patterns/` dir, mirroring desktop bundles.

#### Step 6 — Tests
* `tests/test_phase9_surface.py` — `_DesktopSurface` / `_AndroidSurface` + `_FakeSurface`; `header_imports`, `screenshot`, bounds; recording session honours the surface across `record_pattern` / `record_payload` / `record_two_patterns`.
* `tests/test_phase9_codegen.py` — codegen routes through the surface: same `RecorderAction.CLICK` produces `wait(...).click()` on desktop and `screen.click(Pattern(...))` on Android; Android-only actions (`BACK`/`HOME`/`RECENTS`) raise on desktop.
* `tests/test_phase9_picker.py` — `RecorderSession.set_surface` swaps the surface, clears prior lines, and is idempotent. Uses a fake `ADBClient` that returns a recording device — no real adb server needed.
* No new device-bound integration tests required; the existing fake-backend pattern from Phase 4 covers the ADB side.

#### Step 7 — Docs
* Extend `examples/tablet_demo.py` with a comment block pointing at the recorder once Phase 9 ships ("for interactive recording, pick this device in the IDE's Recorder dropdown").
* New `docs/recorder_android.md` (only if the README grows past one screen) walking through: enable USB debugging → plug in → IDE → Record → choose device → tap targets → Insert & Close → run.

#### Risks & open questions
* **Mid-recording surface switch.** Current plan is to drop prior lines. Alternative: keep them and let codegen apply the new surface during finalize, but that breaks if the recorded actions reference desktop-only verbs (`KEY_COMBO`, `LAUNCH_APP`). Drop-on-switch is simpler and matches user expectation.
* **Wireless-debug pairing.** Android 11+ pairing flow needs `adb pair` first, which the IDE doesn't drive. For now the dropdown's free-form field accepts only an `IP:PORT` that's already paired; surfacing a pair dialog is a follow-up.
* **Multi-display devices.** `ADBScreen` covers display 0 only. Foldables and connected secondary displays will need a `display_id` argument on `ADBScreen.start` before the recorder can target them.
* **Performance.** Each recorded action triggers a fresh `screencap` (~50–250 ms over USB, longer over Wi-Fi). For long sessions this is fine; if it bites we can re-introduce the Phase 1 cached-bitmap behaviour and only re-screencap when the user opens the picker.

### Phase 10 — Action logging in the IDE Console

Goal: while a script runs from the IDE, every interaction (click,
type, find, wait, drag, swipe, app launch, etc.) appears as a
human-readable line in the Console pane so the user can watch what the
script is doing and debug from the log without sprinkling `print()`
calls. Logging stays opt-in at runtime via a level knob, never affects
return values, and degrades to a no-op when the IDE isn't driving the
runner (so plain `python script.py` users don't suddenly get noisy
output).

#### Design

* **Single logger, structured records.** `sikulipy/util/action_log.py`
  — new module exposing `ActionLogger`, `ActionRecord(category, verb,
  target, result, duration_ms, surface)`, and a module-level singleton
  reachable via `get_action_logger()`. Logger has `level`
  (`off|action|verbose`) and a list of `Sink` callables. Default level
  `off` so headless callers see nothing.
* **No `logging.getLogger` indirection.** The codebase has no existing
  logging conventions — adding one logger here keeps the surface
  small. We can graduate to `logging` later if more subsystems want
  structured output.
* **Instrumentation by decorator, not edit-every-method.** New
  `@logged_action(category, verb)` decorator in
  `sikulipy/util/action_log.py` wraps a bound method, computes the
  target description from arguments (`Pattern("ok.png", 0.7)`,
  `"hello"`, etc.), times the call, and emits one record on entry
  ("→") + one on exit ("✓ in 42 ms" / "✗ FindFailed"). Applied to:
  * `core/region.py` — `find`, `find_all`, `wait`, `wait_vanish`,
    `exists`, `click`, `double_click`, `right_click`, `hover`,
    `drag_drop`, `type`, `text`, `find_text`, `find_all_text`.
  * `core/mouse.py` — `click`, `double_click`, `right_click`,
    `drag_drop`, `move`, `wheel`.
  * `android/screen.py` — same click/type family + `swipe`, `back`,
    `home`, `recents`, `find_text_coordinates`.
  * `natives/app.py` — `App.open`, `App.focus`, `App.close`.
* **Console sink.** `ide/toolbar.py:_DefaultRunnerHost.run` enables
  the logger before `run_file` and disables on finally. The sink
  formats records as `[12:34:56.789] click Pattern("ok.png") @
  Region(…) in 42 ms` and writes them via `console.write("stdout",
  …)` so they interleave with the script's own `print()` output.
* **Level toggle.** The decorator's `if level < ACTION: return fn(...)`
  short-circuit is in place, so the perf cost at OFF is one attribute
  lookup. The runner sets the level to `action` for the duration of a
  script and back to `off` on exit. A user-facing status-bar dropdown
  (off / action / verbose) is deferred to [`BACKLOG.md`](BACKLOG.md).
* **Console capacity.** `ConsoleBuffer` is a 2000-entry ring buffer
  (`ide/console.py`); a tight find-loop can saturate it. Two mitigations:
  bump the cap to 10 000 when level ≥ action, and coalesce identical
  consecutive records (`× 47` suffix) at sink time.
* **Recorded code is unaffected.** Logging is a runtime concern; the
  recorder still emits the same `screen.click(Pattern(...))` source.

#### Risks & open questions

* **Decorator vs. shim.** A class-level decorator means we touch every
  Region-family file once, and the wrapped method's docstring/typing
  is preserved via `functools.wraps`. The alternative — a single
  proxy class — collides with subclassing (`Screen extends Region`).
  Decorator is the simpler call.
* **Threading.** The runner runs on a daemon thread; `console.write`
  is already thread-safe (deque + listener fan-out under the GIL).
  Logger sink list mutations must be guarded — single `threading.Lock`
  inside `ActionLogger`.
* **Find-loop noise.** Even at `action` level a `wait(timeout=10)`
  emits one record at start and one at finish; the *internal* tight
  retry loop stays silent. `verbose` is the level that surfaces every
  `_find_once` attempt.
* **Performance budget.** Target: `off` level adds < 1 µs per
  decorated call; `action` level adds < 10 µs (one f-string + one
  deque append). Benchmark via `tests/test_phase10_perf.py` before
  declaring the phase done.

#### Tests

* `tests/test_phase10_action_log.py` — unit tests for the logger:
  level filtering, duration timing (mocked clock), record formatting,
  coalescing, sink-list thread safety.
* `tests/test_phase10_instrumentation.py` — fakes for Region's mouse
  + finder backends; assert each instrumented method emits the
  expected `(category, verb, target)` tuple.
* `tests/test_phase10_console_sink.py` — drives a fake script through
  `_DefaultRunnerHost` with the logger enabled; assert the
  `ConsoleBuffer` ends up with one entry per action, in order.

### Phase 11 — Web Auto recorder mode ✅
Shipped: a new **Web Auto** button in the recorder bar opens a popup
asking for a URL, launches a Playwright-driven Chromium, and turns the
sidebar into an element-aware capture pane (filter checkboxes per
:class:`ElementKind`, scrollable element list with role/name + selector
tooltip, bottom preview, *Apply* / *Take ElScrsht* / *Close* buttons).
The editor + explorer area is replaced by a scrollable page screenshot
with the filtered elements outlined. Recorded actions emit
``screen.click(Pattern(...))`` against a session-bound
``WebScreen.start(url=...)``.

* `web/_backend.py` — `BrowserBackend` Protocol + lazy
  `_PlaywrightBackend` + in-memory `_FakeBackend`; ``get_backend`` /
  ``set_backend`` singleton.
* `web/elements.py` — ``WebElement`` dataclass, ``ElementKind`` enum,
  the ``DISCOVERY_JS`` payload Playwright evaluates, plus a
  ``classify(tag, type, role)`` mapper.
* `web/filters.py` — ``ElementFilter`` (toggle by kind, ``apply``).
* `web/assets.py` — ``asset_root(project, url)`` carves
  ``<project>/assets/web/<host>/``; ``slug_for_element`` builds
  collision-resistant filenames; ``crop_element`` slices a tight bbox
  + 4 px padding (DPR-aware).
* `web/screen.py` — ``WebScreen(Region)`` singleton-by-URL with
  ``click`` / ``double_click`` / ``right_click`` / ``hover`` /
  ``drag_drop`` / ``type`` plus ``navigate`` / ``reload`` /
  ``go_back`` / ``go_forward``; capture pulls the latest backend
  frame.
* `ide/recorder/surface.py:_WebSurface` — third peer of
  ``_DesktopSurface`` / ``_AndroidSurface``; ``header_imports`` +
  ``header_setup`` inject ``WebScreen.start(url=...)``.
* `ide/recorder/codegen.py` — ``_gen_web`` branch (mirrors android,
  plus web-only nav verbs). ``ide/recorder/workflow.py`` adds
  ``NAVIGATE`` / ``RELOAD`` / ``GO_BACK`` / ``GO_FORWARD`` and a new
  ``_DESKTOP_AND_WEB_ACTIONS`` bucket so RCLICK is allowed on desktop
  + web but not android.
* `ide/web_dialog.py:WebAutoDialog` — URL prompt model with scheme
  validation (rejects ``javascript:``/``data:``/``file:``/etc.,
  upgrades bare hosts to ``https://``).
* `ide/web_panel.py:WebAutoController` — headless state machine:
  ``start`` → launch → goto → screenshot → discover; ``set_filter_kind``
  / ``apply_filter`` / ``select`` / ``take_screenshots`` / ``refresh``
  / ``close``. Subscriber fan-out drives the IDE refresh.
* `ide/app.py` — recorder footer gains the **Web Auto** button; while
  active, ``refresh()`` swaps the editor row for a scrollable page
  screenshot with overlay rectangles, and the sidebar for the filter
  + list + preview pane.
* `pyproject.toml` — new ``web`` extra (``playwright>=1.45``).
* Tests: 42 in ``tests/test_phase11_web_*.py`` — backend round-trip
  (5), filter (5), assets (8), surface + codegen (9), controller
  (7), dialog (8). Every test uses ``_FakeBackend``; no Chromium
  download or live network needed.

Below is the original step-by-step plan, kept for reference.

#### Original goal & design notes

Goal: a new **Web Auto** button in the recorder bar opens a popup
asking for a URL, launches a headed Playwright browser, and turns the
IDE into an element-aware capture surface for that page. The Patterns
pane lists every actionable element Playwright can discover, filtered
by user-toggled checkboxes. Selecting an element shows its cropped
image; *Take ElScrsht* batch-saves PNGs into the project's web-asset
folder. The editor pane is replaced by a scrollable screenshot of the
page with the filtered elements outlined. *Close* tears the mode down
and restores the normal IDE layout. A `WebScreen` surface (third
peer of `_DesktopSurface` / `_AndroidSurface`) lets recorded actions
target the same browser, so codegen emits `screen.click(Pattern(...))`
against a Playwright-driven page.

#### Design constraints

* **Playwright as the engine.** New `web` pyproject extra
  (`playwright`); the IDE prompts the user to run
  `playwright install chromium` on first use if the browser is
  missing. Headed mode by default so the user can authenticate or
  dismiss cookie banners; auto-snapshot when the page reaches
  `networkidle` + 1 s, with a manual *Refresh* fallback.
* **Reuses Phase 9 surface plumbing.** `WebSurface` implements
  `TargetSurface`; `screenshot()` returns the current page PNG,
  `bounds()` is the viewport in CSS pixels, `header_imports()` injects
  `from sikulipy.web.screen import WebScreen` and a `screen =
  WebScreen.start(url=...)` line. Existing `recorder/codegen.py`
  dispatch table gets a third branch.
* **Headless-testable.** The element discovery, filter, list model,
  and screenshot+overlay layout live in `web/` and `ide/web_panel.py`
  as pure-Python classes. Tests inject a fake `BrowserBackend`
  recording the calls Playwright would make. No `cv2`, no live
  browser, no network in the test path.
* **Single-window flow.** No separate browser window stays in front of
  the IDE while the user picks elements — the IDE pane shows the
  static page screenshot with overlays, and Playwright is reduced
  to a backend service. The headed browser is only visible during
  the initial navigate / login phase; the IDE iconifies it once the
  snapshot is taken.

#### Module layout

* `web/_backend.py` — `BrowserBackend` Protocol
  (`launch`, `goto`, `wait_until_idle`, `screenshot`, `discover`,
  `close`) + `_PlaywrightBackend` (lazy import) + `_FakeBackend` for
  tests. `get_backend()` / `set_backend()` mirror the OCR/Native/Guide
  patterns.
* `web/elements.py` — `WebElement(role, name, selector, xpath,
  bounds, kind)` dataclass + `ElementKind` enum (`LINK`, `BUTTON`,
  `INPUT`, `CHECKBOX_RADIO`, `SELECT`, `MENU`, `TAB`, `OTHER`).
  Discovery is one Playwright `page.evaluate(...)` call returning
  every element matched by a built-in selector union — anchors,
  buttons, every `[role]` Playwright lists, all form controls, plus a
  catch-all for `[onclick]` / `tabindex`. Visible-only filtering
  (offsetParent + clientRect non-empty + not `aria-hidden`).
* `web/filters.py` — `ElementFilter(kinds: set[ElementKind])` with
  `apply(elements) -> list[WebElement]`; default = all kinds enabled.
* `web/screen.py` — `WebScreen(Region)` subclass; `_capture_bgr` pulls
  a fresh screenshot via the backend, `click`/`type`/`drag_drop` route
  through Playwright `page.mouse` / `page.keyboard`. Pattern targets
  resolved via the standard `find()` path against the captured frame.
  Singleton-by-URL like `VNCScreen.start`.
* `web/assets.py` — `asset_root(project_dir, url) -> Path` returns
  `<project>/assets/web/<host>/`; `crop_element(frame, bounds, pad=4)`
  → BGR ndarray written via `cv2.imwrite`; filename slug from the
  element's accessible name + role + short selector hash.

#### IDE wiring

* `recorder/surface.py` — new `_WebSurface(WebScreen)` peer of
  `_DesktopSurface` / `_AndroidSurface`. `header_imports()` returns
  `["from sikulipy.web.screen import WebScreen"]`. `header_setup()`
  emits `screen = WebScreen.start(url="...")`.
* `ide/web_panel.py` — headless model:
  * `WebAutoState` (URL, last screenshot path, element list, filter,
    selected element, asset folder).
  * `WebAutoController(backend, asset_resolver, on_change)` —
    `start(url)` → `discover` → `set_filter` → `take_screenshots` →
    `close`. Pure-Python, no Flet imports.
* `ide/web_dialog.py` — popup model: URL field, OK/Cancel callbacks,
  validation (must parse as `http(s)://...`). Returns a normalised URL.
* `ide/app.py` — recorder bar gains a **Web Auto** button. While
  `WebAutoState.active`:
  * Editor + explorer area is replaced by a scrollable
    `Stack(Image(screenshot.png), overlay_canvas)`. Overlay draws one
    coloured rectangle per filtered element; hover shows a tooltip
    with role + name + selector. Click on a rectangle selects the
    element in the sidebar list.
  * Patterns pane swaps for the Web Auto pane: a `Column` with the
    filter checkboxes (Links / Buttons / Inputs / Checkbox-Radio /
    Selects / Menus & Tabs / Other), three buttons (**Apply**,
    **Take ElScrsht**, **Close**), the filtered element list (each
    row: `[role] name (W×H)` with the full selector as a tooltip),
    and a bottom preview `Image` of the selected element's crop.
  * Status bar segment: `Web Auto: example.com — 47 elements`.
* **Apply** re-runs `filter.apply()` and refreshes the overlay + list.
* **Take ElScrsht** crops every currently filtered element via
  `assets.crop_element` and writes the PNGs into
  `<project>/assets/web/<host>/`; status bar shows `Saved 47 elements
  → assets/web/example.com/`.
* **Close** tears the mode down: stops the backend, restores the
  editor / explorer / patterns pane, leaves the saved PNGs on disk.

#### Codegen

* `recorder/codegen.py` — Web branch mirrors Android:
  `RecorderAction.CLICK` → `screen.click(Pattern("login_btn.png"))`;
  `TYPE` → `screen.type("hello")`; `WAIT` → `time.sleep(...)`. Web-only
  verbs (`NAVIGATE`, `BACK`, `FORWARD`, `RELOAD`) reject on other
  surfaces. Desktop-only verbs (`KEY_COMBO` modifier chords,
  `LAUNCH_APP`) reject on Web.
* `recorder/workflow.py` — extend the surface_only attribute matrix.

#### Tests

* `tests/test_phase11_web_backend.py` — `_FakeBackend` round-trip:
  `launch` → `goto` → `discover` returns N elements → `screenshot`
  writes a PNG → `close` releases. Verify discovery payload shape
  (role, name, selector, bounds) without spawning Chromium.
* `tests/test_phase11_web_filter.py` — every checkbox combination
  filters the element list correctly; visible-only filtering rejects
  display:none / aria-hidden / offscreen elements.
* `tests/test_phase11_web_assets.py` — `asset_root` carves
  `<project>/assets/web/<host>/`; `crop_element` writes PNGs with the
  expected filename pattern; idempotent across reruns.
* `tests/test_phase11_web_surface.py` — `_WebSurface` integrates with
  `RecorderSession` like the Android peer; codegen emits the
  expected `screen.*` calls; surface-mismatched actions raise.
* `tests/test_phase11_web_panel.py` — `WebAutoController` state
  machine: `start` → discovery results land in state; `set_filter` →
  list narrows; `take_screenshots` calls the asset resolver per
  element; `close` resets state. Subscribers fire on every change.
* `tests/test_phase11_web_dialog.py` — URL validation accepts
  `https://example.com`, rejects empty / `javascript:` / non-URL
  strings. Cancel returns `None`.

#### Risks & open questions

* **Playwright install size.** Chromium download is ~150 MB. Keeping
  it behind the `web` extra is mandatory; first-run prompt should
  link to the Playwright install docs rather than running it
  silently.
* **Auth walls.** Headed browser solves the simple case (user logs in
  manually before the snapshot). SSO redirects that bounce through
  multiple domains will need a configurable navigation timeout and a
  *Snapshot now* button as escape hatch.
* **Iframe traversal.** First pass discovers the top-level document
  only. Cross-origin iframes (ads, captchas) are skipped. Same-origin
  iframes are a follow-up — the discovery JS would need to recurse
  via `page.frames()`.
* **Element stability.** A page that mutates after `networkidle`
  (lazy-loaded carousels, banners) can desync the screenshot from
  the live element list. Mitigation: re-snapshot on every Apply, and
  surface a "page changed since last snapshot" warning in the status
  bar if the next click target's bbox no longer matches the captured
  frame.
* **Coordinate mapping.** Playwright `bounding_box()` returns CSS
  pixels; the screenshot is rendered at device pixel ratio. Overlay
  layer must scale by `window.devicePixelRatio` (read once via
  `page.evaluate`) so rectangles stay aligned. Verified in unit tests
  by using a fake DPR ≠ 1.
* **Long pages.** Full-page screenshots can run to 20 000+ pixels
  tall; rendering the overlay with one Flet `Container` per element
  is fine up to ~2 000 elements but past that the Stack stutters.
  Cap the rendered overlay to elements within the visible scroll
  viewport, lazy-render the rest on scroll.
* **WebScreen vs. desktop browser.** A user might prefer recording
  against the *real* browser they already have open (so cookies,
  sessions, extensions Just Work). That's a future "Attach to
  browser via CDP" follow-up — Playwright's `connect_over_cdp` makes
  it cheap once the discovery + UI layer exists.

### Phase 12 — Image-driven test generation (POM)

Goal: turn a Web Auto capture session into a runnable, maintainable
pytest suite where elements are referenced by their cropped PNG (not
by CSS selector), assertions are made by OpenCV image comparison
against a "golden" baseline, and any text inside an element is
verified through Tesseract OCR + Levenshtein-ratio matching. The
generated code follows the Page Object Model: one `pages/<host>.py`
holds the image catalogue and action/assertion methods; the
`tests/<feature>.py` modules call those methods and stay readable
even after a UI refresh.

#### Why image-as-locator (not selector-as-locator)

* Selectors break on every framework rerender; the screenshot the
  recorder already captured *is* the contract the user signed off on.
* SikuliPy's matcher (`Finder.find` over `cv2.matchTemplate` + greedy
  NMS) is already wired to handle DPR/scale via `Pattern.similarity`.
  Reusing it keeps Web Auto symmetrical with the desktop / Android
  surfaces.
* Selector-based tests already exist (Playwright, Selenium); the
  differentiator here is "the test fails when the *visual* changes",
  which is what users record Web Auto for in the first place.

#### Page Object layout

```
project/
  assets/web/<host>/                # populated by Take ElScrsht
    login_btn.png
    username_field.png
    welcome_banner.png
  baselines/web/<host>/             # NEW — golden crops + region full-frames
    login_btn.png
    welcome_banner.png
    home_hero.png
  pages/                            # NEW — generated Page Objects
    __init__.py
    example_com.py                  # one module per host
  tests/                            # NEW — generated test modules
    web/
      conftest.py
      test_example_com_login.py
```

Each `pages/<host>.py` exposes:

```python
class ExampleCom(WebPageObject):
    URL = "https://example.com"

    # Catalogue — the image is the locator; selector is a fallback
    # only used when the image match dips below ``min_similarity``.
    LOGIN_BTN = ImageLocator("login_btn.png", selector="button[type=submit]")
    USERNAME  = ImageLocator("username_field.png", selector="#username")
    WELCOME   = ImageLocator("welcome_banner.png")

    # Action methods (stateful flows live here)
    def login(self, username: str, password: str) -> None: ...
    def open_account_menu(self) -> None: ...

    # Assertion methods (Page Object owns the *meaning* of the check;
    # tests stay declarative)
    def expect_welcome(self, name: str) -> None: ...
    def expect_logged_out(self) -> None: ...
```

The base class `WebPageObject` in `sikulipy.testing.pom` wraps a
`WebScreen`, the `assets` folder, the `baselines` folder, and the
comparison thresholds. It provides primitives (`click(locator)`,
`type(locator, text)`, `expect_visual(locator)`, `expect_text(
locator, expected)`) so generated subclasses stay thin.

#### New module: `sikulipy.testing` (under `src/sikulipy/testing/`)

* `compare.py` — `compare_images(actual, expected, *, mode,
  threshold) -> ImageDiff`. Three modes:
  * `mode="exact"` — `cv2.absdiff` + per-pixel mask; fails if any
    pixel exceeds `tolerance` (default 8/255) and total diff fraction
    exceeds `threshold` (default 0.005).
  * `mode="ssim"` — `skimage.metrics.structural_similarity` (added as
    optional dep); robust to anti-aliasing / font hinting drift.
    Fails if `score < threshold` (default 0.97).
  * `mode="template"` — `cv2.matchTemplate(TM_CCOEFF_NORMED)`; passes
    if best match `>= threshold` (default 0.92). Used when the
    actual frame is the full page and the expected is a tight crop.
  Returns `ImageDiff(passed, score, diff_image, bbox)` so the runner
  can dump artefacts on failure.
* `ocr_assert.py` — `compare_text(actual_image, expected, *,
  ratio_threshold=0.85, normalize=...)`. Pulls text via the existing
  `OCR` facade (defaults to `TesseractBackend`), normalises (lower,
  collapse whitespace, optional diacritic strip), then computes
  Levenshtein ratio (`1 - distance/max(len)`) and asserts
  `ratio >= ratio_threshold`. Returns `TextDiff(passed, ratio,
  expected_norm, actual_norm)`.
* `pom.py` — `WebPageObject` base, `ImageLocator` dataclass
  (`asset`, `selector`, `min_similarity`, `mode`, `text`), and the
  pytest hooks that record diff artefacts to `tests/.diffs/<run>/`.
* `baseline.py` — `BaselineStore`: load / write / promote.
  `--update-baselines` (pytest CLI flag added in `conftest.py`)
  rewrites the golden image with the captured frame on the next run
  and emits a one-line note per replaced file.
* `levenshtein.py` — vendored `_levenshtein(a, b) -> int` in pure
  Python (~30 lines); avoids pulling `python-Levenshtein` (C ext) or
  `rapidfuzz` for what's a hot loop only on assertion failure paths.
  If `rapidfuzz` is installed we delegate (much faster on long
  strings); detection is lazy.

#### IDE: "Generate tests" button

* `ide/web_panel.py:WebAutoController.generate_tests(scenario)` —
  given a scenario name, takes the current filtered elements +
  recorded actions and writes:
  * one Page Object module if it doesn't exist (or appends new
    locators to the existing one),
  * one test module per scenario,
  * baselines folder seeded with copies of the saved PNGs (the user
    can later re-run the suite with `--update-baselines` once the
    UI is reviewed).
* `ide/recorder/codegen.py` — new `_gen_pom_test` branch that emits
  Page-Object-style code instead of inline `screen.click(Pattern(
  ...))`. Keyed off a recorder-bar dropdown: **Inline script** (the
  existing Phase 11 output) vs **POM test** (the new generator).
  Reuses `RecorderSession.records()` so nothing changes upstream.
* `ide/app.py` — recorder footer gets a **Generate tests** button
  next to **Web Auto**; enabled only when the recorder has at least
  one record and a Web Auto controller is active. Click → name
  prompt (`_ask_native_input`) → controller emits the files →
  status bar shows `Wrote pages/example_com.py + tests/web/
  test_example_com_login.py`.

#### Codegen template (POM mode)

For one recorded login flow:

```python
# pages/example_com.py — generated, hand-edit safe
from sikulipy.testing.pom import WebPageObject, ImageLocator


class ExampleCom(WebPageObject):
    URL = "https://example.com"

    USERNAME  = ImageLocator("username_field.png", selector="#username")
    PASSWORD  = ImageLocator("password_field.png", selector="#password")
    LOGIN_BTN = ImageLocator("login_btn.png", selector="button[type=submit]")
    WELCOME   = ImageLocator("welcome_banner.png", text="Welcome,")

    def login(self, username: str, password: str) -> None:
        self.type(self.USERNAME, username)
        self.type(self.PASSWORD, password)
        self.click(self.LOGIN_BTN)

    def expect_welcome(self, name: str) -> None:
        self.expect_visual(self.WELCOME)
        self.expect_text(self.WELCOME, f"Welcome, {name}")
```

```python
# tests/web/test_example_com_login.py — generated
import pytest
from pages.example_com import ExampleCom


@pytest.fixture
def page(web_screen):
    return ExampleCom.start(web_screen)


def test_login_happy_path(page: ExampleCom) -> None:
    page.login("alice", "hunter2")
    page.expect_welcome("alice")
```

The `web_screen` fixture in `tests/web/conftest.py` launches the
Playwright backend (headless by default, `--headed` flag for
debugging), navigates to `cls.URL`, and tears down on session end.

#### Tests for the test-generator

* `tests/test_phase12_compare.py` — exact / ssim / template modes;
  diff artefact emission; tolerance edge cases.
* `tests/test_phase12_ocr_assert.py` — Levenshtein ratio thresholds;
  whitespace + case normalisation; backend swap to a fake OCR.
* `tests/test_phase12_levenshtein.py` — parity with `rapidfuzz`
  when installed, fallback path when not.
* `tests/test_phase12_baseline.py` — `--update-baselines` rewrites
  the golden, normal run leaves it alone, missing baseline emits a
  helpful "run with --update-baselines" message.
* `tests/test_phase12_pom.py` — `WebPageObject.click/type/
  expect_visual/expect_text` against a fake `WebScreen`; locator
  resolution prefers the image, falls back to selector when
  similarity dips below `min_similarity`.
* `tests/test_phase12_codegen.py` — POM generator emits a parseable
  Page Object module + test module from a synthetic recorder
  session; round-trips through `ast.parse` so we know the generated
  code at least imports.
* `tests/test_phase12_controller.py` — `generate_tests(scenario)`
  writes the expected files, refuses to clobber an existing test
  module without `force=True`, populates the baselines folder.

#### Risks & open questions

* **OCR brittleness.** Tesseract on raw screen pixels is noisy
  (memory: `project_tesseract_preprocessing.md`). We must pass the
  cropped element through the same upscale/threshold pipeline as
  the desktop OCR backend before measuring Levenshtein, otherwise
  short labels ("OK", "✕") OCR to junk and the ratio threshold
  can't compensate.
* **Anti-aliasing & subpixel font hinting.** Pixel-exact comparison
  fails between Linux/macOS/CI even on identical pages. Default
  mode should be `ssim`, not `exact`; `exact` is for icons / brand
  marks the user marked as static.
* **Baseline discipline.** Without `--update-baselines` and a clear
  diff artefact, this turns into "rerun until green". Diff PNGs
  must land at a stable path the IDE's status bar can link to.
* **Locator drift vs. baseline drift.** If the page redesign moves
  an element *and* repaints it, the image locator finds nothing
  *and* the baseline fails. The CSS-selector fallback in
  `ImageLocator.selector` is the recovery path — when the image
  match dips below `min_similarity` we re-resolve via the selector,
  capture the new crop, and surface a "locator drifted; run
  --update-baselines to refresh" warning.
* **OCR runtime cost.** Tesseract on every assertion would slow
  tests significantly; the comparator should short-circuit text
  checks when the visual diff already passed at high confidence
  (`ssim >= 0.99`) — text is a fallback signal, not a duplicate.
* **Cross-DPR captures.** A baseline captured at DPR=2 (Retina)
  won't match a CI runner at DPR=1. Baselines are stored at the
  CSS-pixel size (`crop / dpr`) so the comparison is DPR-agnostic;
  documented in `BaselineStore.write`.
* **Headless-vs-headed parity.** Headless Chromium hides scrollbars
  and renders fonts slightly differently. The `web_screen` fixture
  pins viewport + colour scheme + reduced-motion via Playwright
  `new_context` options so a test that passes locally also passes
  in CI.
* **Out of scope for Phase 12.** Multi-page flows that span
  navigations stay on the user; we provide `WebPageObject.navigate(
  url)` and `expect_url(...)` but no auto-discovery of "page B" on
  click. Visual A/B regression dashboards are also out — diffs land
  on disk, not in a viewer.

## Out of scope (for now)

* MCP module — Java-specific, superseded by Python MCP SDKs
* Jython / JRuby — irrelevant in a Python host
* The embedded `jcraft/jsch`, `jadb`, `keymaster`, and `jxgrabkey`
  third-party forks — all replaced by Python equivalents

## Web Auto asset filename convention

Each cropped element PNG written by Web Auto (`Take ElScrsht`) uses the
slug:

```
<role>-<name>-<hash>.png
```

* **role** — the element's ARIA role or HTML tag (`button`, `link`,
  `a`, `input`), lowercased.
* **name** — the accessible name (aria-label / button text / placeholder
  / alt), slugified.
* **hash** — first 6 hex digits of `sha1(element.selector)`. The
  selector is unique per element on the page, so the hash is a stable
  disambiguator: two visually identical elements (e.g. multiple "Add to
  cart" buttons) share the same role and name but get distinct
  filenames, and the same element regenerates the same hash across
  re-runs. Implemented in `sikulipy.web.assets.slug_for_element`.

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
(new)                         -> sikulipy.web   (Playwright, Phase 11)
com.sikulix.ocr.*             -> sikulipy.ocr
com.sikulix.util.SSHTunnel    -> sikulipy.vnc.ssh
com.sikulix.tigervnc.*        -> sikulipy.vnc   (wrapped by vncdotool)
```
