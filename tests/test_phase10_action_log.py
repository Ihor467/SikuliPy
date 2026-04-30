"""Phase 10 step 1 — ActionLogger foundation.

Pin down the runtime contract the IDE Console will depend on:
level filtering, the @logged_action decorator's START/OK/FAIL
emission, signature/docstring preservation, sink registration races
under threads, formatter output, and the Coalescer's identical-line
collapsing. No instrumentation of real action methods yet — that
arrives in step 2.
"""

from __future__ import annotations

import threading
import time

import pytest

from sikulipy.util.action_log import (
    ActionLogger,
    ActionRecord,
    Coalescer,
    Level,
    Phase,
    collect_records,
    format_record,
    get_action_logger,
    logged_action,
)


# ---------------------------------------------------------------------------
# Logger basics
# ---------------------------------------------------------------------------


def test_singleton_returns_same_instance() -> None:
    assert get_action_logger() is get_action_logger()


def test_emit_below_level_drops_record() -> None:
    logger = ActionLogger(level=Level.OFF)
    seen: list[ActionRecord] = []
    logger.add_sink(seen.append)
    logger.emit(_make_record(Phase.START))
    assert seen == []


def test_emit_at_level_dispatches_to_sinks() -> None:
    logger = ActionLogger(level=Level.ACTION)
    a: list[ActionRecord] = []
    b: list[ActionRecord] = []
    logger.add_sink(a.append)
    logger.add_sink(b.append)
    rec = _make_record(Phase.START)
    logger.emit(rec)
    assert a == [rec]
    assert b == [rec]


def test_unsubscribe_returned_callable_removes_sink() -> None:
    logger = ActionLogger(level=Level.ACTION)
    seen: list[ActionRecord] = []
    unsubscribe = logger.add_sink(seen.append)
    logger.emit(_make_record(Phase.START))
    unsubscribe()
    logger.emit(_make_record(Phase.OK))
    assert len(seen) == 1


def test_misbehaving_sink_does_not_break_others() -> None:
    logger = ActionLogger(level=Level.ACTION)
    seen: list[ActionRecord] = []
    logger.add_sink(lambda _: (_ for _ in ()).throw(RuntimeError("boom")))
    logger.add_sink(seen.append)
    logger.emit(_make_record(Phase.START))
    assert len(seen) == 1


def test_verbose_records_gated_by_min_level() -> None:
    logger = ActionLogger(level=Level.ACTION)
    seen: list[ActionRecord] = []
    logger.add_sink(seen.append)
    logger.emit(_make_record(Phase.NOTE), min_level=Level.VERBOSE)
    assert seen == []
    logger.level = Level.VERBOSE
    logger.emit(_make_record(Phase.NOTE), min_level=Level.VERBOSE)
    assert len(seen) == 1


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------


class _Fake:
    @logged_action("region", "click", target=lambda self, *a, **k: f"Pattern({a[0]!r})")
    def click(self, name: str) -> str:
        return f"clicked {name}"

    @logged_action("region", "find")
    def find(self, target: str) -> str:
        raise FindFailed(f"no match for {target}")


class FindFailed(RuntimeError):
    pass


def test_decorator_off_level_is_passthrough() -> None:
    records, restore = collect_records(level=Level.OFF)
    try:
        out = _Fake().click("ok.png")
    finally:
        restore()
    assert out == "clicked ok.png"
    assert records == []


def test_decorator_emits_start_then_ok() -> None:
    records, restore = collect_records()
    try:
        _Fake().click("ok.png")
    finally:
        restore()
    assert [r.phase for r in records] == [Phase.START, Phase.OK]
    assert records[0].verb == "click"
    assert records[0].target == "Pattern('ok.png')"
    assert records[1].duration_ms is not None and records[1].duration_ms >= 0


def test_decorator_emits_fail_on_exception_and_reraises() -> None:
    records, restore = collect_records()
    try:
        with pytest.raises(FindFailed):
            _Fake().find("missing.png")
    finally:
        restore()
    assert [r.phase for r in records] == [Phase.START, Phase.FAIL]
    assert records[0].target == "'missing.png'"
    assert "FindFailed" in records[1].result


def test_decorator_preserves_signature_and_docstring() -> None:
    class C:
        @logged_action("x", "y")
        def m(self, a: int, b: int = 2) -> int:
            """sum a and b"""
            return a + b
    assert C.m.__doc__ == "sum a and b"
    assert C.m.__name__ == "m"


def test_decorator_target_callable_receives_args() -> None:
    received: list[tuple] = []
    def repr_target(self_, *a, **k):
        received.append((a, k))
        return "T"

    class C:
        @logged_action("c", "v", target=repr_target)
        def m(self, x, y=10):
            return x + y

    records, restore = collect_records()
    try:
        C().m(3, y=4)
    finally:
        restore()
    assert received == [((3,), {"y": 4})]
    assert records[0].target == "T"


def test_decorator_static_target_string() -> None:
    class C:
        @logged_action("c", "v", target="LITERAL")
        def m(self):
            return None

    records, restore = collect_records()
    try:
        C().m()
    finally:
        restore()
    assert records[0].target == "LITERAL"


def test_decorator_surface_callable_attaches_surface_name() -> None:
    class C:
        surface_name = "android-XYZ"

        @logged_action(
            "android",
            "click",
            target=lambda self, *a, **k: a[0],
            surface=lambda self, *a, **k: self.surface_name,
        )
        def click(self, x):
            return None

    records, restore = collect_records()
    try:
        C().click("Btn")
    finally:
        restore()
    assert all(r.surface == "android-XYZ" for r in records)


def test_decorator_target_repr_failure_is_swallowed() -> None:
    def bad(*a, **k):
        raise RuntimeError("oops")

    class C:
        @logged_action("c", "v", target=bad)
        def m(self):
            return None

    records, restore = collect_records()
    try:
        C().m()
    finally:
        restore()
    assert records[0].target.startswith("<target-repr failed:")


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def test_format_record_start_renders_arrow_and_target() -> None:
    rec = ActionRecord(
        timestamp=_fixed_ts(),
        category="region",
        verb="click",
        target='Pattern("ok.png")',
        phase=Phase.START,
        surface="desktop",
    )
    line = format_record(rec)
    assert "→" in line
    assert "click" in line
    assert 'Pattern("ok.png")' in line
    assert "desktop" in line
    assert "ms" not in line  # no duration on START


def test_format_record_ok_includes_duration() -> None:
    rec = ActionRecord(
        timestamp=_fixed_ts(),
        category="region",
        verb="click",
        target="",
        phase=Phase.OK,
        duration_ms=42.7,
    )
    line = format_record(rec)
    assert "✓" in line
    assert "in 43 ms" in line  # rounded


def test_format_record_fail_appends_reason() -> None:
    rec = ActionRecord(
        timestamp=_fixed_ts(),
        category="region",
        verb="find",
        target="ok.png",
        phase=Phase.FAIL,
        result="FindFailed: timed out",
        duration_ms=3000.0,
    )
    line = format_record(rec)
    assert "✗" in line
    assert "FindFailed" in line


# ---------------------------------------------------------------------------
# Coalescer
# ---------------------------------------------------------------------------


def test_coalescer_passes_through_distinct_records() -> None:
    c = Coalescer()
    out1 = c.feed(_make_record(Phase.START, verb="click"))
    out2 = c.feed(_make_record(Phase.START, verb="type"))
    out3 = c.flush()
    # First feed buffers; second feed flushes the first and buffers
    # itself; flush emits the last buffered line.
    assert out1 == []
    assert len(out2) == 1
    assert "click" in out2[0]
    assert len(out3) == 1
    assert "type" in out3[0]


def test_coalescer_collapses_identical_runs_with_count() -> None:
    c = Coalescer()
    rec = _make_record(Phase.START, verb="find", target="needle")
    for _ in range(5):
        c.feed(rec)
    out = c.flush()
    assert len(out) == 1
    assert "× 5" in out[0]


def test_coalescer_distinguishes_phase_within_same_target() -> None:
    c = Coalescer()
    a = _make_record(Phase.START, verb="click", target="X")
    b = _make_record(Phase.OK, verb="click", target="X")
    out_a = c.feed(a)
    out_b = c.feed(b)
    assert out_a == []
    assert len(out_b) == 1  # START flushed because phase differs


# ---------------------------------------------------------------------------
# Threading
# ---------------------------------------------------------------------------


def test_concurrent_emit_and_subscribe_does_not_corrupt_sink_list() -> None:
    logger = ActionLogger(level=Level.ACTION)
    rec = _make_record(Phase.START)

    seen: list[int] = []
    add_sink_calls = 0

    def emitter() -> None:
        for _ in range(500):
            logger.emit(rec)

    def subscriber() -> None:
        nonlocal add_sink_calls
        for _ in range(50):
            unsubscribe = logger.add_sink(lambda r: seen.append(1))
            add_sink_calls += 1
            unsubscribe()

    threads = [threading.Thread(target=emitter) for _ in range(3)]
    threads += [threading.Thread(target=subscriber) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # No assertion on exact `seen` length — the test passes by not
    # raising (the deque/list mutations would otherwise throw under
    # the GIL with sufficiently bad concurrent access). Sanity-check
    # that subscribers actually ran.
    assert add_sink_calls == 150


# ---------------------------------------------------------------------------
# collect_records helper
# ---------------------------------------------------------------------------


def test_collect_records_restores_prior_level() -> None:
    logger = get_action_logger()
    logger.level = Level.VERBOSE
    try:
        records, restore = collect_records(level=Level.ACTION)
        assert logger.level == Level.ACTION
        restore()
        assert logger.level == Level.VERBOSE
    finally:
        logger.level = Level.OFF


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fixed_ts() -> float:
    # Deterministic timestamp so format tests don't depend on now().
    # Picked so the millisecond field is non-zero, exercising the
    # formatter's zero-padding.
    return 1_700_000_000.123


def _make_record(
    phase: Phase,
    *,
    category: str = "region",
    verb: str = "click",
    target: str = "X",
) -> ActionRecord:
    return ActionRecord(
        timestamp=_fixed_ts(),
        category=category,
        verb=verb,
        target=target,
        phase=phase,
    )
