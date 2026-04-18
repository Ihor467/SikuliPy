"""Phase 3 tests — OCR facade + Region text helpers against a fake backend.

The FakeOcrBackend returns a preset word list so tests run without a
real Tesseract binary or NumPy-dependent image handling.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from sikulipy.core.region import Region
from sikulipy.ocr import OCR, Word, set_ocr
from sikulipy.ocr.paddle import PaddleOCR
from sikulipy.script.exceptions import FindFailed


@dataclass
class FakeOcrBackend:
    words: list[Word] = field(default_factory=list)
    read_calls: list[object] = field(default_factory=list)

    def read_words(self, image) -> list[Word]:
        self.read_calls.append(image)
        return list(self.words)

    def read(self, image) -> str:
        self.read_calls.append(image)
        return " ".join(w.text for w in self.words)


@pytest.fixture
def fake_ocr():
    backend = FakeOcrBackend(
        words=[
            Word(text="Submit", x=10, y=20, w=60, h=18, confidence=0.99, line=1, block=1),
            Word(text="Cancel", x=100, y=20, w=55, h=18, confidence=0.98, line=1, block=1),
            Word(text="submit", x=200, y=60, w=60, h=18, confidence=0.85, line=2, block=1),
        ]
    )
    set_ocr(backend)
    yield backend
    set_ocr(None)


# -----------------------------------------------------------------------------
# OCR facade
# -----------------------------------------------------------------------------


def test_ocr_read_concatenates_words(fake_ocr):
    assert OCR.read(object()) == "Submit Cancel submit"


def test_ocr_read_words_passes_through(fake_ocr):
    ws = OCR.read_words("whatever")
    assert [w.text for w in ws] == ["Submit", "Cancel", "submit"]


def test_ocr_read_lines_groups_by_block_line(fake_ocr):
    lines = OCR.read_lines(object())
    assert lines == ["Submit Cancel", "submit"]


def test_ocr_find_text_substring_match(fake_ocr):
    w = OCR.find_text(object(), "ubmi")
    assert w is not None and w.text == "Submit"


def test_ocr_find_text_missing_returns_none(fake_ocr):
    assert OCR.find_text(object(), "Nope") is None


def test_ocr_find_all_text_returns_matches(fake_ocr):
    hits = OCR.find_all_text(object(), "ubmit")
    assert [w.text for w in hits] == ["Submit", "submit"]


def test_ocr_find_word_ignore_case(fake_ocr):
    assert OCR.find_word(object(), "SUBMIT", ignore_case=True).text == "Submit"
    # Without ignore_case, exact-token "SUBMIT" is absent.
    assert OCR.find_word(object(), "SUBMIT") is None


# -----------------------------------------------------------------------------
# Region text helpers (patched capture)
# -----------------------------------------------------------------------------


def _patch_capture(monkeypatch, sentinel: object = b"fake-bitmap") -> None:
    monkeypatch.setattr(Region, "_capture_bgr", lambda self: sentinel)


def test_region_text_returns_string(fake_ocr, monkeypatch):
    _patch_capture(monkeypatch)
    r = Region(0, 0, 200, 100)
    assert r.text() == "Submit Cancel submit"


def test_region_words_translates_to_absolute_coords(fake_ocr, monkeypatch):
    _patch_capture(monkeypatch)
    r = Region(500, 600, 800, 400)
    ws = r.words()
    assert [(w.text, w.x, w.y) for w in ws] == [
        ("Submit", 510, 620),
        ("Cancel", 600, 620),
        ("submit", 700, 660),
    ]


def test_region_find_text_returns_match_in_absolute_coords(fake_ocr, monkeypatch):
    _patch_capture(monkeypatch)
    r = Region(1000, 2000, 500, 500)
    m = r.find_text("Submit")
    assert m.x == 1010
    assert m.y == 2020
    assert m.w == 60
    assert m.h == 18
    assert m.score == pytest.approx(0.99)


def test_region_find_text_raises_when_absent(fake_ocr, monkeypatch):
    _patch_capture(monkeypatch)
    r = Region(0, 0, 10, 10)
    with pytest.raises(FindFailed):
        r.find_text("nowhere")


def test_region_find_all_text_returns_list(fake_ocr, monkeypatch):
    _patch_capture(monkeypatch)
    r = Region(0, 0, 10, 10)
    ms = r.find_all_text("ubmit")
    assert len(ms) == 2
    assert all(m.w == 60 for m in ms)


def test_region_has_text(fake_ocr, monkeypatch):
    _patch_capture(monkeypatch)
    r = Region(0, 0, 10, 10)
    assert r.has_text("Cancel") is True
    assert r.has_text("Missing") is False


# -----------------------------------------------------------------------------
# PaddleOCR parity helpers (pure parsing, no network, no numpy)
# -----------------------------------------------------------------------------


_SAMPLE_PADDLE_RAW = [
    [[[10, 20], [70, 20], [70, 38], [10, 38]], ("Validate", 0.9997)],
    [[[100, 20], [160, 20], [160, 38], [100, 38]], ("Cancel", 0.9981)],
]


def test_paddle_raw_to_words_bbox_and_conf():
    words = PaddleOCR._raw_to_words(_SAMPLE_PADDLE_RAW)
    assert [(w.text, w.x, w.y, w.w, w.h) for w in words] == [
        ("Validate", 10, 20, 60, 18),
        ("Cancel", 100, 20, 60, 18),
    ]
    assert words[0].confidence == pytest.approx(0.9997)


def test_paddle_parse_texts_roundtrip():
    import json

    payload = json.dumps(_SAMPLE_PADDLE_RAW)
    p = PaddleOCR(endpoint="http://unused")  # endpoint irrelevant for parsing helpers
    assert p.parse_texts(payload) == ["Validate", "Cancel"]
    assert p.parse_text_with_confidence(payload)["Validate"] == pytest.approx(0.9997)
    assert p.find_text_coordinates(payload, "Cancel") == (100, 20, 60, 18)
    assert p.find_text_coordinates(payload, "Missing") is None
