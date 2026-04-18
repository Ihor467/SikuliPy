"""Phase 1 tests — Finder against synthetic in-memory haystacks.

These tests don't touch a real screen. We build a haystack numpy array
ourselves, crop a known patch as the needle, and verify Finder locates
it at the expected coordinates.
"""

from __future__ import annotations

import pytest

# Skip the whole module if numpy/cv2 cannot be imported at all on this host
# (e.g. CPU predates x86-64-v2 and the NumPy 2.x wheel refuses to load).
try:
    import numpy as np
    import cv2  # noqa: F401
except Exception as exc:  # pragma: no cover - host dependent
    pytest.skip(f"numpy/opencv unavailable: {exc}", allow_module_level=True)

from sikulipy.core.finder import Finder  # noqa: E402
from sikulipy.core.image import Image, ImagePath, ScreenImage  # noqa: E402
from sikulipy.core.match import Match  # noqa: E402
from sikulipy.core.region import Region  # noqa: E402


def _make_haystack(width: int = 400, height: int = 300, seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    # Random noise background (BGR uint8)
    return rng.integers(0, 256, size=(height, width, 3), dtype=np.uint8)


def _paint_needle(hay: np.ndarray, x: int, y: int, size: int = 40) -> np.ndarray:
    """Paint a bright red square into the haystack and return the needle crop."""
    hay[y : y + size, x : x + size] = (0, 0, 255)  # BGR red
    return hay[y : y + size, x : x + size].copy()


def test_finder_single_match_exact_coords():
    hay = _make_haystack()
    needle = _paint_needle(hay, x=123, y=77, size=50)

    match = Finder(hay).find(needle, similarity=0.9)

    assert match is not None
    assert match.x == 123
    assert match.y == 77
    assert match.w == 50
    assert match.h == 50
    assert match.score > 0.99


def test_finder_returns_none_when_missing():
    hay = _make_haystack(seed=2)
    # A solid-colour needle that (with overwhelming probability) isn't present.
    needle = np.full((30, 30, 3), fill_value=(10, 200, 50), dtype=np.uint8)

    assert Finder(hay).find(needle, similarity=0.95) is None


def test_finder_find_all_with_nms():
    hay = _make_haystack(width=600, height=400, seed=3)
    # Paint three identical red squares far enough apart that NMS keeps all three.
    _paint_needle(hay, 20, 20)
    _paint_needle(hay, 300, 20)
    _paint_needle(hay, 20, 200)
    # Re-grab one of them as the canonical needle.
    needle = hay[20:60, 20:60].copy()

    matches = Finder(hay).find_all(needle, similarity=0.9)

    assert len(matches) == 3
    coords = sorted((m.x, m.y) for m in matches)
    assert coords == [(20, 20), (20, 200), (300, 20)]
    for m in matches:
        assert isinstance(m, Match)
        assert m.score > 0.99


def test_finder_respects_region_offset():
    hay = _make_haystack()
    needle = _paint_needle(hay, x=50, y=60, size=30)

    region = Region(x=1000, y=2000, w=hay.shape[1], h=hay.shape[0])
    match = Finder(hay, region=region).find(needle, similarity=0.9)

    # Finder adds region.x/y so callers get absolute screen coordinates.
    assert match is not None
    assert match.x == 1000 + 50
    assert match.y == 2000 + 60


def test_screen_image_save_roundtrip(tmp_path):
    arr = _make_haystack(width=50, height=40, seed=9)
    shot = ScreenImage(bitmap=arr, bounds=Region(0, 0, 50, 40))
    out = shot.save(tmp_path / "shot.png")

    assert out.exists()
    assert out.stat().st_size > 0


def test_image_path_resolves_registered_dir(tmp_path):
    import cv2

    img = _make_haystack(width=20, height=20, seed=5)
    path = tmp_path / "needle.png"
    cv2.imwrite(str(path), img)

    ImagePath.reset()
    ImagePath.add(tmp_path)

    resolved = ImagePath.resolve("needle.png")
    assert resolved == path.resolve()

    # Image.load goes through the cache and returns a BGR array of matching shape.
    arr = Image("needle.png").load()
    assert arr.shape == (20, 20, 3)


def test_image_path_missing_returns_none(tmp_path):
    ImagePath.reset()
    assert ImagePath.resolve("nope.png") is None
    with pytest.raises(FileNotFoundError):
        Image("nope.png").load()
