"""Phase 12 — baseline store I/O + metadata."""

from __future__ import annotations

from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from sikulipy.testing.baseline import BaselineMetadata, BaselineStore


def _solid(h: int, w: int, color: tuple[int, int, int]):
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:] = color
    return img


def test_path_for_lands_under_project_baselines(tmp_path: Path) -> None:
    store = BaselineStore(tmp_path, "example.com")
    target = store.path_for("login_btn.png")
    assert target == tmp_path / "baselines" / "web" / "example.com" / "login_btn.png"


def test_load_missing_baseline_raises_with_helpful_message(tmp_path: Path) -> None:
    store = BaselineStore(tmp_path, "example.com")
    with pytest.raises(FileNotFoundError, match="--update-baselines"):
        store.load("login_btn.png")


def test_write_then_load_roundtrips(tmp_path: Path) -> None:
    store = BaselineStore(tmp_path, "example.com")
    img = _solid(20, 30, (10, 20, 30))
    out = store.write("login_btn.png", img)
    assert out.is_file()
    loaded = store.load("login_btn.png")
    assert loaded.shape == img.shape
    assert np.array_equal(loaded, img)


def test_exists_reflects_disk_state(tmp_path: Path) -> None:
    store = BaselineStore(tmp_path, "example.com")
    assert not store.exists("login_btn.png")
    store.write("login_btn.png", _solid(10, 10, (0, 0, 0)))
    assert store.exists("login_btn.png")


def test_promote_from_copies_a_png(tmp_path: Path) -> None:
    src = tmp_path / "captured.png"
    cv2.imwrite(str(src), _solid(10, 10, (255, 0, 0)))
    store = BaselineStore(tmp_path, "example.com")
    out = store.promote_from("login_btn.png", src)
    assert out.is_file()
    assert out.read_bytes() == src.read_bytes()


def test_remove_returns_false_when_missing(tmp_path: Path) -> None:
    store = BaselineStore(tmp_path, "example.com")
    assert store.remove("nope.png") is False


def test_remove_returns_true_after_write(tmp_path: Path) -> None:
    store = BaselineStore(tmp_path, "example.com")
    store.write("x.png", _solid(5, 5, (0, 0, 0)))
    assert store.remove("x.png") is True
    assert not store.exists("x.png")


def test_metadata_roundtrip(tmp_path: Path) -> None:
    store = BaselineStore(tmp_path, "example.com")
    store.write_metadata(
        BaselineMetadata(dpr=2.0, viewport=(1920, 1080), notes={"who": "alice"})
    )
    meta = store.read_metadata()
    assert meta.dpr == 2.0
    assert meta.viewport == (1920, 1080)
    assert meta.notes == {"who": "alice"}


def test_metadata_defaults_when_missing(tmp_path: Path) -> None:
    store = BaselineStore(tmp_path, "example.com")
    meta = store.read_metadata()
    assert meta.dpr == 1.0
    assert meta.viewport == (1600, 900)


def test_list_assets_only_returns_pngs(tmp_path: Path) -> None:
    store = BaselineStore(tmp_path, "example.com")
    store.write("a.png", _solid(5, 5, (0, 0, 0)))
    store.write("b.png", _solid(5, 5, (0, 0, 0)))
    # Drop a non-png file in the same directory.
    (store.host_dir / "ignored.txt").write_text("nope", encoding="utf-8")
    assert store.list_assets() == ["a.png", "b.png"]
