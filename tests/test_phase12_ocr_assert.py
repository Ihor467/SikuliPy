"""Phase 12 — OCR + Levenshtein text assertion."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from sikulipy.ocr import set_ocr
from sikulipy.testing.ocr_assert import compare_text, normalize


@dataclass
class FakeOcrBackend:
    text: str

    def read(self, image) -> str:
        return self.text

    def read_words(self, image):  # not used by compare_text
        return []


@pytest.fixture
def ocr_returning():
    def _install(text: str):
        set_ocr(FakeOcrBackend(text))
    yield _install
    set_ocr(None)


def test_exact_match_passes(ocr_returning) -> None:
    ocr_returning("Welcome, alice")
    diff = compare_text(object(), "Welcome, alice")
    assert diff.passed
    assert diff.ratio == 1.0


def test_case_insensitive_default(ocr_returning) -> None:
    ocr_returning("WELCOME, ALICE")
    diff = compare_text(object(), "welcome, alice")
    assert diff.passed


def test_whitespace_collapsed_default(ocr_returning) -> None:
    ocr_returning("Welcome,   \n  alice")
    diff = compare_text(object(), "Welcome, alice")
    assert diff.passed


def test_close_match_above_threshold(ocr_returning) -> None:
    # OCR mistook 'l' for 'I' once — ratio still high.
    ocr_returning("Welcome, aIice")
    diff = compare_text(object(), "Welcome, alice", ratio_threshold=0.85)
    assert diff.passed
    assert 0.85 < diff.ratio < 1.0


def test_far_off_text_fails(ocr_returning) -> None:
    ocr_returning("Goodbye, bob")
    diff = compare_text(object(), "Welcome, alice")
    assert not diff.passed
    assert "OCR ratio" in diff.message


def test_threshold_override_can_force_pass(ocr_returning) -> None:
    ocr_returning("xxxx")
    diff = compare_text(object(), "yyyy", ratio_threshold=0.0)
    assert diff.passed


def test_diacritic_strip_normalizer(ocr_returning) -> None:
    ocr_returning("café")
    diff_default = compare_text(object(), "cafe")
    assert not diff_default.passed  # 'café' vs 'cafe' default → 0.75 < 0.85
    diff_stripped = compare_text(
        object(),
        "cafe",
        normalize_fn=lambda s: normalize(s, strip_diacritics=True),
    )
    assert diff_stripped.passed
    assert diff_stripped.ratio == 1.0


def test_ocr_returns_empty_string_fails(ocr_returning) -> None:
    ocr_returning("")
    diff = compare_text(object(), "anything")
    assert not diff.passed
    assert diff.actual_raw == ""
