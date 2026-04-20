"""Phase 7 tests — recorder.

The recorder never touches pynput in these tests: we inject a fake
listener via :func:`set_listener_factory`.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from sikulipy.recorder import (
    ActionRecorder,
    RecordedAction,
    set_listener_factory,
)


# ---------------------------------------------------------------------------
# Fake listener
# ---------------------------------------------------------------------------


@dataclass
class FakeListener:
    on_click: object
    on_key: object
    started: int = 0
    stopped: int = 0

    def start(self) -> None:
        self.started += 1

    def stop(self) -> None:
        self.stopped += 1


@pytest.fixture
def capture_factory():
    created: list[FakeListener] = []

    def factory(*, on_click, on_key):
        lis = FakeListener(on_click=on_click, on_key=on_key)
        created.append(lis)
        return lis

    set_listener_factory(factory)
    yield created
    set_listener_factory(None)


@pytest.fixture
def fake_clock():
    """Clock advancing 0.1s per call — below the 0.5s wait threshold."""
    counter = itertools.count()
    return lambda: next(counter) * 0.1


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_start_and_stop_lifecycle(capture_factory):
    rec = ActionRecorder()
    rec.start()
    rec.start()  # idempotent
    assert capture_factory[0].started == 1
    rec.stop()
    assert capture_factory[0].stopped == 1
    rec.stop()  # idempotent
    assert capture_factory[0].stopped == 1


def test_records_click_and_type_and_wait(capture_factory):
    # Custom clock: click at 0.0, keys at 0.1/0.2 (fast), final click at 1.0.
    ticks = iter([0.0, 0.1, 0.2, 1.0, 1.0])
    rec = ActionRecorder(_now=lambda: next(ticks))
    rec.start()
    listener = capture_factory[0]

    listener.on_click(100, 200, "left", False)   # ts=0.0
    listener.on_key("h")                          # ts=0.1 (no wait)
    listener.on_key("i")                          # ts=0.2
    listener.on_click(10, 10, "right", False)    # ts=1.0 → wait between type and right_click
    rec.stop()

    actions = rec.actions()
    kinds = [a.kind for a in actions]
    assert kinds == ["click", "type", "wait", "right_click"]
    type_action = actions[1]
    assert type_action.text == "hi"
    wait_action = actions[2]
    assert wait_action.duration is not None
    assert wait_action.duration > 0
    assert actions[-1].x == 10 and actions[-1].y == 10


def test_clear_resets(capture_factory, fake_clock):
    rec = ActionRecorder(_now=fake_clock)
    rec.start()
    capture_factory[0].on_click(1, 1, "left", False)
    rec.stop()
    assert rec.actions()
    rec.clear()
    assert rec.actions() == []


def test_generate_script_shape(capture_factory, fake_clock):
    rec = ActionRecorder(_now=fake_clock)
    rec.start()
    listener = capture_factory[0]
    listener.on_click(100, 200, "left", False)
    listener.on_key("a")
    listener.on_key("b")
    rec.stop()

    source = rec.generate_script()
    assert "from sikulipy.core.screen import Screen" in source
    assert "screen = Screen.get_primary()" in source
    assert "screen.click((100, 200))" in source
    assert 'screen.type("ab")' in source


def test_generate_script_escapes_awkward_strings(capture_factory):
    rec = ActionRecorder()
    rec.start()
    listener = capture_factory[0]
    for ch in 'hi"bye':
        listener.on_key(ch)
    rec.stop()
    source = rec.generate_script()
    # The awkward quote forces repr() which uses single quotes.
    assert "screen.type('hi\"bye')" in source


def test_pattern_capture_skipped_without_screenshotter(capture_factory, tmp_path):
    rec = ActionRecorder(pattern_dir=tmp_path)
    rec.start()
    capture_factory[0].on_click(5, 5, "left", False)
    rec.stop()
    assert rec.actions()[0].pattern is None


def test_recorded_action_is_dataclass():
    a = RecordedAction(kind="click", timestamp=0.0, x=1, y=2)
    assert a.text is None
    assert a.duration is None
