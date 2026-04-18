"""Port of ``org.sikuli.script.Image`` + ``ImagePath`` + ``ScreenImage``.

Image is a lazy handle around a BGR numpy array loaded from disk (via OpenCV
with a Pillow fallback for alpha channels). ImagePath replicates SikuliX's
search-path semantics. ScreenImage wraps a raw screen capture together with
the Region it came from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
import numpy as np
from PIL import Image as PILImage

if TYPE_CHECKING:
    from sikulipy.core.region import Region


@lru_cache(maxsize=256)
def _imread_bgr_cached(resolved: str) -> np.ndarray:
    """Load an image as a BGR ``uint8`` numpy array. Raises FileNotFoundError if missing."""
    p = Path(resolved)
    if not p.exists():
        raise FileNotFoundError(resolved)
    data = cv2.imread(str(p), cv2.IMREAD_COLOR)
    if data is None:
        # Fallback for formats or paths that cv2 chokes on.
        pil = PILImage.open(str(p)).convert("RGB")
        data = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    return data


class Image:
    """Lazy image handle."""

    def __init__(self, source: str | Path | np.ndarray) -> None:
        self.source: str | Path | np.ndarray = source

    def load(self) -> np.ndarray:
        if isinstance(self.source, np.ndarray):
            return self.source
        resolved = ImagePath.resolve(self.source)
        if resolved is None:
            raise FileNotFoundError(self.source)
        return _imread_bgr_cached(str(resolved))

    @property
    def size(self) -> tuple[int, int]:
        """Return (width, height) of the loaded image."""
        arr = self.load()
        h, w = arr.shape[:2]
        return w, h


class ImagePath:
    """SikuliX-compatible image search path resolver."""

    _paths: list[Path] = []

    @classmethod
    def reset(cls) -> None:
        cls._paths = []
        _imread_bgr_cached.cache_clear()

    @classmethod
    def add(cls, path: str | Path) -> None:
        p = Path(path).resolve()
        if p not in cls._paths:
            cls._paths.append(p)

    @classmethod
    def paths(cls) -> list[Path]:
        return list(cls._paths)

    @classmethod
    def resolve(cls, name: str | Path) -> Path | None:
        p = Path(name)
        if p.is_absolute() and p.exists():
            return p
        # 1. CWD-relative
        if p.exists():
            return p.resolve()
        # 2. Registered image paths
        for base in cls._paths:
            candidate = base / p
            if candidate.exists():
                return candidate.resolve()
        return None


@dataclass
class ScreenImage:
    """A captured region of the screen with its BGR bitmap."""

    bitmap: np.ndarray
    bounds: "Region" = field(default=None)  # type: ignore[assignment]

    @property
    def width(self) -> int:
        return int(self.bitmap.shape[1])

    @property
    def height(self) -> int:
        return int(self.bitmap.shape[0])

    def save(self, path: str | Path) -> Path:
        out = Path(path)
        cv2.imwrite(str(out), self.bitmap)
        return out
