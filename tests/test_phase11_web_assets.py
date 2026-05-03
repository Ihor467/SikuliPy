"""Phase 11 — asset folder layout + crop math."""

from __future__ import annotations

from pathlib import Path

import pytest

from sikulipy.web import ElementKind, WebElement, asset_root, crop_element, slug_for_element


np = pytest.importorskip("numpy")


def test_asset_root_carves_per_host(tmp_path: Path) -> None:
    a = asset_root(tmp_path, "https://example.com/foo")
    b = asset_root(tmp_path, "https://other.test:8080/x")
    assert a == tmp_path / "assets" / "web" / "example.com"
    assert b == tmp_path / "assets" / "web" / "other.test"
    assert a.is_dir() and b.is_dir()


def test_asset_root_idempotent(tmp_path: Path) -> None:
    a = asset_root(tmp_path, "https://example.com")
    b = asset_root(tmp_path, "https://example.com")
    assert a == b


def test_slug_includes_role_name_and_hash() -> None:
    el = WebElement(
        kind=ElementKind.BUTTON,
        role="button",
        name="Sign In!",
        selector="#login-btn",
        xpath="//*[@id='login-btn']",
        bounds=(0, 0, 100, 40),
    )
    slug = slug_for_element(el)
    assert "button" in slug
    assert "sign-in" in slug
    # 6-char hex digest at the tail
    tail = slug.rsplit("-", 1)[-1]
    assert len(tail) == 6 and all(c in "0123456789abcdef" for c in tail)


def test_slug_distinguishes_elements_with_same_name() -> None:
    common = dict(
        kind=ElementKind.BUTTON, role="button", name="Add",
        xpath="/html", bounds=(0, 0, 50, 30),
    )
    a = WebElement(selector="#a", **common)
    b = WebElement(selector="#b", **common)
    assert slug_for_element(a) != slug_for_element(b)


def test_crop_element_pads_around_bbox() -> None:
    frame = np.zeros((200, 300, 3), dtype=np.uint8)
    cropped = crop_element(frame, (50, 60, 80, 40), pad=4)
    # Expected size = (40 + 8, 80 + 8) before clipping
    assert cropped.shape == (48, 88, 3)


def test_crop_element_handles_dpr() -> None:
    frame = np.zeros((400, 600, 3), dtype=np.uint8)
    # CSS bounds at DPR=2 → effective frame coords doubled
    cropped = crop_element(frame, (10, 10, 50, 30), pad=0, device_pixel_ratio=2.0)
    assert cropped.shape == (60, 100, 3)


def test_crop_element_clips_to_frame() -> None:
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    # bbox extends beyond the frame; crop should clip to the frame edges.
    cropped = crop_element(frame, (90, 90, 50, 50), pad=0)
    assert cropped.shape == (10, 10, 3)


def test_crop_element_rejects_zero_area() -> None:
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    with pytest.raises(ValueError):
        crop_element(frame, (200, 200, 10, 10), pad=0)
