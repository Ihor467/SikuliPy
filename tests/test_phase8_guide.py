"""Phase 8 tests — guide overlays + Highlight.

Shape rendering is gated on cv2 + numpy (skipped on this host's CPU if
NumPy fails to import). Everything else uses a recording backend.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from sikulipy.guide import (
    Arrow,
    Callout,
    Guide,
    Rectangle,
    Spotlight,
    Text,
    set_backend,
)
from sikulipy.guide._backend import _NullGuideBackend


# ---------------------------------------------------------------------------
# Recording backend
# ---------------------------------------------------------------------------


@dataclass
class RecordingGuideBackend:
    shown: list[tuple[list, float | None]] = field(default_factory=list)
    hidden: int = 0

    def show(self, shapes, *, duration=None):  # noqa: ANN001
        self.shown.append((list(shapes), duration))

    def hide(self):
        self.hidden += 1

    def is_visible(self) -> bool:
        return bool(self.shown) and self.hidden == 0


@pytest.fixture
def backend():
    b = RecordingGuideBackend()
    set_backend(b)
    yield b
    set_backend(None)


# ---------------------------------------------------------------------------
# Shape geometry
# ---------------------------------------------------------------------------


def test_rectangle_bounds_pass_through():
    r = Rectangle(10, 20, 100, 50)
    assert r.bounds() == (10, 20, 100, 50)


def test_arrow_bounds_normalise_direction():
    a = Arrow(from_xy=(100, 100), to_xy=(40, 40))
    assert a.bounds() == (40, 40, 60, 60)


def test_spotlight_bounds_match_region():
    s = Spotlight(x=5, y=6, w=7, h=8)
    assert s.bounds() == (5, 6, 7, 8)


def test_callout_bounds_include_padding():
    c = Callout(anchor_xy=(0, 0), text="x", padding=8)
    x, y, w, h = c.bounds()
    assert (x, y) == (0, 0)
    assert w >= 2 * 8
    assert h >= 2 * 8


# ---------------------------------------------------------------------------
# Guide routing
# ---------------------------------------------------------------------------


def test_guide_show_passes_shapes_to_backend(backend):
    g = Guide().arrow((0, 0), (10, 10)).rectangle((5, 5, 20, 20), color="green")
    g.show(duration=1.5)

    shapes, duration = backend.shown[0]
    assert duration == 1.5
    assert len(shapes) == 2
    assert isinstance(shapes[0], Arrow)
    assert isinstance(shapes[1], Rectangle)
    assert shapes[1].color == "green"


def test_guide_hide_calls_backend(backend):
    g = Guide().text((10, 10), "hi")
    g.show()
    g.hide()
    assert backend.hidden == 1


def test_guide_clear_resets_shape_list(backend):
    g = Guide().rectangle((0, 0, 10, 10)).clear()
    assert g.shapes == []


def test_guide_rectangle_accepts_tuple_or_region(backend):
    g = Guide()
    g.rectangle((1, 2, 3, 4))
    shape = g.shapes[0]
    assert isinstance(shape, Rectangle)
    assert (shape.x, shape.y, shape.w, shape.h) == (1, 2, 3, 4)


# ---------------------------------------------------------------------------
# Null backend (default-path smoke test)
# ---------------------------------------------------------------------------


def test_null_guide_backend_records_and_hides():
    nb = _NullGuideBackend()
    nb.show([Rectangle(0, 0, 1, 1)], duration=None)
    assert nb.is_visible()
    nb.hide()
    assert not nb.is_visible()
    assert len(nb.shown) == 1
    assert nb.hidden == 1


# ---------------------------------------------------------------------------
# Highlight
# ---------------------------------------------------------------------------


def test_highlight_show_close_round_trip(backend):
    from sikulipy.util.highlight import Highlight

    hl = Highlight((10, 10, 100, 100), color="yellow", duration=0)
    hl.show()
    shapes, duration = backend.shown[0]
    assert duration is None  # duration<=0 => indefinite
    assert isinstance(shapes[0], Rectangle)
    assert shapes[0].color == "yellow"
    hl.close()
    assert backend.hidden == 1


def test_highlight_context_manager(backend):
    from sikulipy.util.highlight import Highlight

    with Highlight((0, 0, 5, 5), duration=0):
        assert len(backend.shown) == 1
    assert backend.hidden == 1


# ---------------------------------------------------------------------------
# cv2-based rendering (optional)
# ---------------------------------------------------------------------------


def test_rectangle_draws_pixels_when_cv2_available():
    np = pytest.importorskip("numpy", exc_type=ImportError)
    cv2 = pytest.importorskip("cv2", exc_type=ImportError)  # noqa: F841

    canvas = np.zeros((100, 100, 3), dtype=np.uint8)
    Rectangle(10, 10, 30, 20, color="red", thickness=1).draw(canvas)
    # Red in BGR is (0, 0, 255); the top edge at y=10 should contain it.
    row = canvas[10, 10:41]
    assert (row == [0, 0, 255]).all(axis=-1).any()


def test_arrow_draws_pixels_when_cv2_available():
    np = pytest.importorskip("numpy", exc_type=ImportError)
    pytest.importorskip("cv2", exc_type=ImportError)

    canvas = np.zeros((100, 100, 3), dtype=np.uint8)
    Arrow((10, 50), (90, 50), color="green", thickness=2).draw(canvas)
    assert canvas.any()  # something got drawn


def test_text_draws_pixels_when_cv2_available():
    np = pytest.importorskip("numpy", exc_type=ImportError)
    pytest.importorskip("cv2", exc_type=ImportError)

    canvas = np.zeros((100, 400, 3), dtype=np.uint8)
    Text(xy=(10, 80), content="hello", color="white").draw(canvas)
    assert canvas.any()
