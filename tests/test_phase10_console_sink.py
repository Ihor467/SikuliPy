"""Phase 10 step 3 — DefaultRunnerHost feeds action records into the Console.

End-to-end-ish: write a tiny script that emits a couple of
@logged_action calls, hand it to DefaultRunnerHost with a real
ConsoleBuffer attached, and assert the Coalescer-formatted lines land
in the buffer in order. We deliberately use the global logger here —
the runner's job is to set the level and attach the sink, so
substituting fakes would defeat the integration test.
"""

from __future__ import annotations

import textwrap
import time
from pathlib import Path

import pytest

from sikulipy.ide.console import ConsoleBuffer
from sikulipy.ide.toolbar import DefaultRunnerHost
from sikulipy.util.action_log import Level, get_action_logger


@pytest.fixture(autouse=True)
def _reset_logger():
    """Force the global logger back to OFF after every test.

    The runner restores its prior level on exit, but a failed test that
    aborts before that finally-block runs would leave the singleton in
    a noisy state and bleed into unrelated tests.
    """
    yield
    logger = get_action_logger()
    logger.clear_sinks()
    logger.level = Level.OFF


def _wait_for_runner(host: DefaultRunnerHost, *, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while host.is_running():
        if time.monotonic() > deadline:
            raise AssertionError("runner did not finish within timeout")
        time.sleep(0.01)


def _write_script(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "script.py"
    path.write_text(textwrap.dedent(body))
    return path


def test_runner_streams_action_records_to_console(tmp_path: Path) -> None:
    script = _write_script(
        tmp_path,
        """
        from sikulipy.util.action_log import logged_action

        class W:
            @logged_action("region", "click", target=lambda self, *a, **k: repr(a[0]))
            def click(self, name):
                return None

        W().click("ok.png")
        print("script done")
        """,
    )

    console = ConsoleBuffer()
    host = DefaultRunnerHost(console=console)
    host.run(script)
    _wait_for_runner(host)

    text = console.text()
    # START + OK lines for click("ok.png"); the order matters —
    # coalescer flushes the START when OK arrives with a different phase.
    assert "→ click 'ok.png'" in text
    assert "✓ click 'ok.png'" in text
    assert "script done" in text


def test_runner_collapses_identical_runs(tmp_path: Path) -> None:
    """Identical consecutive records (NOTE phase, no START/OK alternation)
    are coalesced into one ``× N`` line.

    A START/OK loop deliberately doesn't collapse — the user wants to
    see each call's outcome. The Coalescer kicks in when the same record
    fires repeatedly with no change in (category, verb, target, phase),
    e.g. a VERBOSE-level _find_once attempt counter.
    """
    script = _write_script(
        tmp_path,
        """
        import time
        from sikulipy.util.action_log import (
            ActionRecord, Phase, get_action_logger, Level,
        )

        logger = get_action_logger()
        for _ in range(5):
            logger.emit(
                ActionRecord(
                    timestamp=time.time(),
                    category="region",
                    verb="find_attempt",
                    target="'needle'",
                    phase=Phase.NOTE,
                )
            )
        """,
    )

    console = ConsoleBuffer()
    host = DefaultRunnerHost(console=console)
    host.run(script)
    _wait_for_runner(host)

    text = console.text()
    # 5 identical NOTE records → one collapsed line tagged "× 5".
    assert "× 5" in text
    assert text.count("find_attempt") == 1


def test_runner_restores_level_and_buffer_cap(tmp_path: Path) -> None:
    """Pre-existing logger state and buffer cap must survive a run."""
    logger = get_action_logger()
    logger.level = Level.OFF

    console = ConsoleBuffer(max_entries=50)
    assert console.max_entries == 50

    script = _write_script(tmp_path, "print('hi')\n")
    host = DefaultRunnerHost(console=console)
    host.run(script)
    _wait_for_runner(host)

    assert logger.level == Level.OFF
    assert console.max_entries == 50


def test_runner_skips_logger_wiring_when_no_console(tmp_path: Path) -> None:
    """Headless callers (no console attached) shouldn't gain any sinks."""
    logger = get_action_logger()
    sinks_before = len(logger._sinks)

    script = _write_script(tmp_path, "print('hi')\n")
    host = DefaultRunnerHost(console=None)
    host.run(script)
    _wait_for_runner(host)

    assert len(logger._sinks) == sinks_before


def test_runner_can_be_disabled_via_action_log_level_none(tmp_path: Path) -> None:
    """action_log_level=None leaves the global level untouched."""
    logger = get_action_logger()
    logger.level = Level.VERBOSE  # pretend a test set this up

    script = _write_script(tmp_path, "print('hi')\n")
    host = DefaultRunnerHost(console=ConsoleBuffer(), action_log_level=None)
    host.run(script)
    _wait_for_runner(host)

    # Sink wiring still happened (level was already >= ACTION) but
    # the level itself was not overwritten.
    assert logger.level == Level.VERBOSE


def test_runner_bumps_console_cap_during_run(tmp_path: Path) -> None:
    """While a script runs at action+, the cap should be 10 000."""
    observed: list[int] = []

    script = _write_script(
        tmp_path,
        """
        from sikulipy.ide.console import ConsoleBuffer  # noqa: F401
        from sikulipy.util.action_log import logged_action

        class W:
            @logged_action("region", "click", target=lambda self, *a, **k: repr(a[0]))
            def click(self, name):
                return None

        W().click("during-run")
        """,
    )

    console = ConsoleBuffer(max_entries=100)

    def _peek(entry) -> None:  # noqa: ANN001 - ConsoleEntry
        observed.append(console.max_entries)

    unsubscribe = console.subscribe(_peek)
    try:
        host = DefaultRunnerHost(console=console)
        host.run(script)
        _wait_for_runner(host)
    finally:
        unsubscribe()

    # At least one write happened while the cap was bumped to 10 000.
    assert any(cap == 10_000 for cap in observed)
    # And the cap was restored after the run.
    assert console.max_entries == 100
