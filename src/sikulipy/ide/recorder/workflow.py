"""Recorder state machine — what action is in flight and what's allowed next.

Mirrors ``RecorderWorkflow.java`` from OculiX. The Java version uses
EDT-safe listener fan-out and watchdog timers; we keep the same shape
(IDLE → in-flight → IDLE) but skip the timers — the Flet dialog will
just stay enabled and the user can cancel at any time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class RecorderAction(str, Enum):
    """Which user gesture the next captured pattern represents."""

    CLICK = "click"
    DBLCLICK = "dblclick"
    RCLICK = "rclick"
    WAIT = "wait"
    WAIT_VANISH = "wait_vanish"
    DRAG_DROP = "drag_drop"
    SWIPE = "swipe"
    WHEEL = "wheel"
    TYPE = "type"
    KEY_COMBO = "key_combo"
    PAUSE = "pause"
    LAUNCH_APP = "launch_app"
    CLOSE_APP = "close_app"
    TEXT_CLICK = "text_click"
    TEXT_WAIT = "text_wait"
    TEXT_EXISTS = "text_exists"

    @property
    def needs_pattern(self) -> bool:
        return self in {
            RecorderAction.CLICK,
            RecorderAction.DBLCLICK,
            RecorderAction.RCLICK,
            RecorderAction.WAIT,
            RecorderAction.WAIT_VANISH,
        }

    @property
    def needs_two_patterns(self) -> bool:
        return self in {RecorderAction.DRAG_DROP, RecorderAction.SWIPE}


class RecorderState(str, Enum):
    IDLE = "idle"
    CAPTURING_REGION = "capturing_region"
    WAITING_USER_INPUT = "waiting_user_input"


@dataclass
class RecorderWorkflow:
    """Track the in-flight action and emit state changes to listeners."""

    state: RecorderState = RecorderState.IDLE
    pending: RecorderAction | None = None
    _listeners: list[Callable[[RecorderState, RecorderAction | None], None]] = field(
        default_factory=list, repr=False
    )

    def subscribe(
        self, listener: Callable[[RecorderState, RecorderAction | None], None]
    ) -> Callable[[], None]:
        self._listeners.append(listener)

        def _unsub() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return _unsub

    def begin(self, action: RecorderAction) -> None:
        if self.state is not RecorderState.IDLE:
            raise RuntimeError(
                f"cannot begin {action.value!r} while {self.state.value!r}"
            )
        self.pending = action
        self.state = (
            RecorderState.CAPTURING_REGION
            if action.needs_pattern or action.needs_two_patterns
            else RecorderState.WAITING_USER_INPUT
        )
        self._notify()

    def finish(self) -> None:
        self.pending = None
        self.state = RecorderState.IDLE
        self._notify()

    def cancel(self) -> None:
        self.finish()

    def is_idle(self) -> bool:
        return self.state is RecorderState.IDLE

    def _notify(self) -> None:
        for cb in list(self._listeners):
            cb(self.state, self.pending)
