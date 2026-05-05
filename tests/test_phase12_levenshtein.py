"""Phase 12 — Levenshtein distance + ratio."""

from __future__ import annotations

import pytest

from sikulipy.testing.levenshtein import distance, ratio


@pytest.mark.parametrize(
    "a,b,expected",
    [
        ("", "", 0),
        ("abc", "abc", 0),
        ("", "abc", 3),
        ("abc", "", 3),
        ("kitten", "sitting", 3),
        ("flaw", "lawn", 2),
        ("abc", "yabd", 2),
    ],
)
def test_distance_known_pairs(a: str, b: str, expected: int) -> None:
    assert distance(a, b) == expected


def test_ratio_identical_strings_is_one() -> None:
    assert ratio("hello", "hello") == 1.0


def test_ratio_two_empty_strings_is_one() -> None:
    assert ratio("", "") == 1.0


def test_ratio_disjoint_short_strings_is_zero() -> None:
    assert ratio("abc", "xyz") == 0.0


def test_ratio_close_strings_pass_threshold() -> None:
    # "kitten" vs "sitting" — distance 3, max len 7 → 4/7 ≈ 0.571
    assert ratio("kitten", "sitting") == pytest.approx(4 / 7)


def test_ratio_one_empty_one_non_empty_is_zero() -> None:
    assert ratio("", "abc") == 0.0
    assert ratio("abc", "") == 0.0


def test_distance_is_symmetric() -> None:
    assert distance("abcdef", "azcdef") == distance("azcdef", "abcdef")
