"""Phase 6 tests — script runners.

PythonRunner runs in-process, so we verify it actually executes user code
and writes to a side channel. Subprocess runners (PowerShell, AppleScript,
Bash) are exercised against a recording fake launcher so the tests work
on any platform — we assert the *command* the runner would have run.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from sikulipy.runners import (
    AppleScriptRunner,
    BashRunner,
    Options,
    PowerShellRunner,
    PythonRunner,
    RobotRunner,
    Runner,
    clear_registry,
    register,
    registered,
    run_file,
    runner_by_name,
    runner_for,
)
from sikulipy.runners._subprocess import LaunchResult, set_launcher


# ---------------------------------------------------------------------------
# Recording launcher for subprocess runners
# ---------------------------------------------------------------------------


@dataclass
class RecordingLauncher:
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    calls: list[dict] = field(default_factory=list)

    def __call__(self, argv, *, cwd, env):
        self.calls.append({"argv": list(argv), "cwd": cwd, "env": env})
        return LaunchResult(self.exit_code, self.stdout, self.stderr)


@pytest.fixture
def launcher():
    rec = RecordingLauncher()
    set_launcher(rec)
    yield rec
    set_launcher(None)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_default_runners_are_registered():
    names = [r.name for r in registered()]
    assert names == ["Python", "PowerShell", "AppleScript", "Bash", "Robot"]


def test_runner_for_dispatches_by_extension():
    assert isinstance(runner_for("/tmp/foo.py"), PythonRunner)
    assert isinstance(runner_for("/tmp/foo.ps1"), PowerShellRunner)
    assert isinstance(runner_for("/tmp/foo.sh"), BashRunner)
    assert isinstance(runner_for("/tmp/foo.robot"), RobotRunner)
    assert isinstance(runner_for("/tmp/foo.applescript"), AppleScriptRunner)


def test_runner_for_rejects_urls():
    assert runner_for("https://example.com/foo.py") is None


def test_runner_for_unknown_extension():
    assert runner_for("/tmp/foo.unknown") is None


def test_runner_by_name_case_insensitive():
    assert isinstance(runner_by_name("python"), PythonRunner)
    assert isinstance(runner_by_name("POWERSHELL"), PowerShellRunner)


def test_register_and_clear_restore():
    saved = registered()
    try:
        clear_registry()
        assert registered() == []

        class ToyRunner(Runner):
            name = "Toy"
            extensions = (".toy",)

            def run_file(self, path, options=None):  # noqa: ARG002
                return 42

        register(ToyRunner())
        assert isinstance(runner_for("/tmp/a.toy"), ToyRunner)
    finally:
        clear_registry()
        for r in saved:
            register(r)


# ---------------------------------------------------------------------------
# PythonRunner — in-process exec
# ---------------------------------------------------------------------------


def test_python_runner_executes_file(tmp_path: Path):
    marker = tmp_path / "marker.txt"
    script = tmp_path / "hello.py"
    script.write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n"
    )
    rc = PythonRunner().run_file(script)
    assert rc == 0
    assert marker.read_text() == "ran"


def test_python_runner_propagates_sys_argv(tmp_path: Path):
    out = tmp_path / "argv.txt"
    script = tmp_path / "args.py"
    script.write_text(
        f"import sys\nopen({str(out)!r}, 'w').write('|'.join(sys.argv))\n"
    )
    rc = PythonRunner().run_file(script, Options(args=["a", "b c"]))
    assert rc == 0
    # sys.argv[0] is the resolved script path; we assert the tail.
    tail = out.read_text().split("|")[1:]
    assert tail == ["a", "b c"]


def test_python_runner_system_exit_returns_code(tmp_path: Path):
    script = tmp_path / "exit.py"
    script.write_text("raise SystemExit(7)\n")
    assert PythonRunner().run_file(script) == 7


def test_python_runner_exception_propagates_unless_silent(tmp_path: Path):
    script = tmp_path / "boom.py"
    script.write_text("raise RuntimeError('nope')\n")
    with pytest.raises(RuntimeError):
        PythonRunner().run_file(script)
    assert PythonRunner().run_file(script, Options(silent=True)) == 1


def test_python_runner_registers_bundle_path(tmp_path: Path):
    try:
        from sikulipy.core.image import ImagePath
    except Exception as exc:
        pytest.skip(f"core.image unavailable on this host: {exc}")

    script = tmp_path / "probe.py"
    script.write_text(
        "from sikulipy.core.image import ImagePath\n"
        "import pathlib\n"
        "pathlib.Path(__file__).with_name('paths.txt').write_text(\n"
        "    '\\n'.join(str(p) for p in ImagePath.paths())\n"
        ")\n"
    )
    before = len(ImagePath.paths())
    PythonRunner().run_file(script)
    # Image path stack is restored after the run.
    assert len(ImagePath.paths()) == before
    recorded = (tmp_path / "paths.txt").read_text().splitlines()
    assert str(tmp_path.resolve()) in recorded


def test_python_runner_handles_sikuli_bundle(tmp_path: Path):
    bundle = tmp_path / "mybundle.sikuli"
    bundle.mkdir()
    marker = tmp_path / "bundle_ran.txt"
    (bundle / "mybundle.py").write_text(
        f"open({str(marker)!r}, 'w').write('yes')\n"
    )
    rc = PythonRunner().run_file(bundle)
    assert rc == 0
    assert marker.read_text() == "yes"


def test_python_runner_run_string_executes_snippet():
    # A trivial snippet that exits cleanly.
    assert PythonRunner().run_string("x = 1 + 1\n") == 0


def test_python_runner_run_string_system_exit():
    assert PythonRunner().run_string("raise SystemExit(3)") == 3


# ---------------------------------------------------------------------------
# PowerShellRunner
# ---------------------------------------------------------------------------


def test_powershell_runner_builds_expected_command(launcher, tmp_path, monkeypatch):
    # Force interpreter to a known value so the test works on any host.
    monkeypatch.setattr(
        PowerShellRunner, "_interpreter", lambda self: "/usr/bin/pwsh"
    )
    script = tmp_path / "foo.ps1"
    script.write_text("Write-Host hi\n")
    rc = PowerShellRunner().run_file(script, Options(args=["--flag", "v"]))
    assert rc == 0
    call = launcher.calls[0]
    assert call["argv"][0] == "/usr/bin/pwsh"
    assert "-ExecutionPolicy" in call["argv"]
    assert "Unrestricted" in call["argv"]
    assert "-File" in call["argv"]
    assert str(script.resolve()) in call["argv"]
    assert call["argv"][-2:] == ["--flag", "v"]
    assert call["cwd"] == str(tmp_path.resolve())


def test_powershell_runner_unsupported_without_interpreter(monkeypatch):
    monkeypatch.setattr(PowerShellRunner, "_interpreter", lambda self: None)
    assert PowerShellRunner().is_supported() is False
    with pytest.raises(RuntimeError):
        PowerShellRunner().run_file("/tmp/foo.ps1")


# ---------------------------------------------------------------------------
# AppleScriptRunner
# ---------------------------------------------------------------------------


def test_applescript_runner_builds_osascript_command(launcher, tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(
        AppleScriptRunner, "_interpreter", lambda self: "/usr/bin/osascript"
    )
    script = tmp_path / "greet.applescript"
    script.write_text('display dialog "hi"\n')
    rc = AppleScriptRunner().run_file(script, Options(args=["extra"]))
    assert rc == 0
    call = launcher.calls[0]
    assert call["argv"] == [
        "/usr/bin/osascript",
        str(script.resolve()),
        "extra",
    ]


def test_applescript_runner_refuses_non_macos(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    runner = AppleScriptRunner()
    assert runner.is_supported() is False
    with pytest.raises(RuntimeError):
        runner.run_file("/tmp/foo.applescript")


# ---------------------------------------------------------------------------
# BashRunner
# ---------------------------------------------------------------------------


def test_bash_runner_builds_shell_command(launcher, tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(BashRunner, "_interpreter", lambda self: "/bin/bash")
    script = tmp_path / "run.sh"
    script.write_text("echo hi\n")
    rc = BashRunner().run_file(script, Options(args=["x"]))
    assert rc == 0
    call = launcher.calls[0]
    assert call["argv"] == ["/bin/bash", str(script.resolve()), "x"]


def test_bash_runner_unsupported_on_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assert BashRunner().is_supported() is False


# ---------------------------------------------------------------------------
# RobotRunner
# ---------------------------------------------------------------------------


def test_robot_runner_is_supported_reflects_import():
    runner = RobotRunner()
    try:
        import robot  # noqa: F401

        assert runner.is_supported() is True
    except ImportError:
        assert runner.is_supported() is False


def test_robot_runner_uses_run_cli_when_available(tmp_path, monkeypatch):
    fake_robot = type(sys)("robot")
    calls: list[tuple[list[str], bool]] = []

    def run_cli(argv, exit=True):  # noqa: ARG001 - kw parity with robot.run_cli
        calls.append((list(argv), exit))
        return 0

    fake_robot.run_cli = run_cli
    monkeypatch.setitem(sys.modules, "robot", fake_robot)

    script = tmp_path / "t.robot"
    script.write_text("*** Test Cases ***\nOK\n    Log    hi\n")
    assert RobotRunner().run_file(script, Options(args=["--dryrun"])) == 0
    argv, no_exit = calls[0]
    assert "--dryrun" in argv
    assert argv[-1] == str(script.resolve())
    assert no_exit is False


def test_robot_runner_reports_unsupported_when_missing(monkeypatch):
    # Hide any installed ``robot`` module so is_supported() reports False.
    monkeypatch.setitem(sys.modules, "robot", None)
    # In addition, shadow the import machinery so ``import robot`` fails.
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "robot":
            raise ImportError("robot not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert RobotRunner().is_supported() is False


# ---------------------------------------------------------------------------
# run_file dispatch
# ---------------------------------------------------------------------------


def test_run_file_dispatches_to_python_runner(tmp_path: Path):
    out = tmp_path / "rf.txt"
    (tmp_path / "s.py").write_text(f"open({str(out)!r}, 'w').write('ok')\n")
    assert run_file(tmp_path / "s.py") == 0
    assert out.read_text() == "ok"


def test_run_file_unknown_extension_raises():
    with pytest.raises(RuntimeError):
        run_file("/tmp/no_such.unknown")
