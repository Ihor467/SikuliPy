"""Phase 12 — image comparison modes."""

from __future__ import annotations

import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from sikulipy.testing.compare import compare_images


def _solid(h: int, w: int, color: tuple[int, int, int]) -> "np.ndarray":
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:] = color
    return img


# ------------------------------ exact mode ------------------------------------


def test_exact_identical_images_pass() -> None:
    img = _solid(20, 20, (10, 20, 30))
    diff = compare_images(img, img.copy(), mode="exact")
    assert diff.passed
    assert diff.score == 0.0


def test_exact_within_tolerance_passes() -> None:
    a = _solid(20, 20, (100, 100, 100))
    b = _solid(20, 20, (104, 104, 104))  # delta=4, below default tolerance=8
    diff = compare_images(a, b, mode="exact")
    assert diff.passed
    assert diff.score == 0.0


def test_exact_above_tolerance_fails() -> None:
    a = _solid(20, 20, (0, 0, 0))
    b = _solid(20, 20, (200, 200, 200))
    diff = compare_images(a, b, mode="exact")
    assert not diff.passed
    assert diff.score == 1.0
    assert "exceeded tolerance" in diff.message


def test_exact_size_mismatch_raises() -> None:
    with pytest.raises(ValueError, match="equal image sizes"):
        compare_images(_solid(20, 20, (0, 0, 0)), _solid(10, 10, (0, 0, 0)), mode="exact")


# ------------------------------ template mode ---------------------------------


def test_template_finds_subimage() -> None:
    # Both frame and needle need texture: TM_CCOEFF_NORMED is mean-
    # subtracted, so a constant-colour template correlates equally
    # well with any uniform region.
    rng = np.random.default_rng(0)
    frame = rng.integers(0, 255, size=(100, 100, 3), dtype=np.uint8)
    needle = rng.integers(0, 255, size=(20, 20, 3), dtype=np.uint8)
    frame[30:50, 40:60] = needle
    diff = compare_images(frame, needle, mode="template")
    assert diff.passed
    assert diff.bbox is not None
    x, y, w, h = diff.bbox
    assert (x, y) == (40, 30)
    assert (w, h) == (20, 20)


def test_template_rejects_mismatched_subimage() -> None:
    rng = np.random.default_rng(1)
    frame = rng.integers(0, 255, size=(100, 100, 3), dtype=np.uint8)
    # A separately-seeded random patch the frame has never seen.
    needle = np.random.default_rng(99).integers(
        0, 255, size=(20, 20, 3), dtype=np.uint8
    )
    diff = compare_images(frame, needle, mode="template", threshold=0.92)
    assert not diff.passed


def test_template_actual_smaller_than_expected_raises() -> None:
    with pytest.raises(ValueError, match="actual >= expected"):
        compare_images(
            _solid(10, 10, (0, 0, 0)),
            _solid(20, 20, (0, 0, 0)),
            mode="template",
        )


# ------------------------------ ssim mode -------------------------------------


def test_ssim_identical_passes() -> None:
    pytest.importorskip("skimage")
    img = _solid(40, 40, (120, 80, 200))
    diff = compare_images(img, img.copy(), mode="ssim")
    assert diff.passed
    assert diff.score == pytest.approx(1.0)


def test_ssim_solid_vs_random_fails() -> None:
    pytest.importorskip("skimage")
    rng = np.random.default_rng(0)
    a = _solid(40, 40, (0, 0, 0))
    b = rng.integers(0, 255, size=(40, 40, 3), dtype=np.uint8)
    diff = compare_images(a, b, mode="ssim", threshold=0.97)
    assert not diff.passed
    assert "SSIM" in diff.message


# ------------------------------ misc ------------------------------------------


def test_unknown_mode_raises() -> None:
    img = _solid(10, 10, (0, 0, 0))
    with pytest.raises(ValueError, match="unknown compare mode"):
        compare_images(img, img, mode="bogus")  # type: ignore[arg-type]
