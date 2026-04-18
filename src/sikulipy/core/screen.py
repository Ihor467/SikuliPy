"""Port of ``org.sikuli.script.Screen`` — a monitor modelled as a Region.

Backed by ``mss`` for cross-platform capture.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

import mss
import numpy as np

from sikulipy.core.image import ScreenImage
from sikulipy.core.region import Region


@lru_cache(maxsize=1)
def _monitors() -> list[dict]:
    """Return ``mss`` monitor descriptors (index 0 is the virtual 'all screens')."""
    with mss.mss() as sct:
        return list(sct.monitors)


@dataclass
class Screen(Region):
    """A monitor as a Region. ``id=0`` is the primary monitor."""

    id: int = 0
    _mon: dict = field(default=None, repr=False)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        mons = _monitors()
        # mss monitor 0 is the union of all screens; real monitors start at 1.
        index = self.id + 1
        if index >= len(mons):
            raise IndexError(f"Screen id {self.id} out of range (have {len(mons) - 1})")
        self._mon = mons[index]
        self.x = int(self._mon["left"])
        self.y = int(self._mon["top"])
        self.w = int(self._mon["width"])
        self.h = int(self._mon["height"])

    # ---- Enumeration -------------------------------------------------
    @classmethod
    def get_number_screens(cls) -> int:
        return max(0, len(_monitors()) - 1)

    @classmethod
    def get_primary(cls) -> "Screen":
        return cls(id=0)

    @classmethod
    def all(cls) -> list["Screen"]:
        return [cls(id=i) for i in range(cls.get_number_screens())]

    # ---- Capture -----------------------------------------------------
    def capture(self, region: Region | None = None) -> ScreenImage:
        """Capture the whole screen (or a sub-region) and return a BGR ``ScreenImage``."""
        r = region if region is not None else Region(self.x, self.y, self.w, self.h)
        box = {"left": int(r.x), "top": int(r.y), "width": int(r.w), "height": int(r.h)}
        with mss.mss() as sct:
            raw = sct.grab(box)
        # mss returns BGRA; drop alpha and keep BGR for OpenCV.
        arr = np.asarray(raw, dtype=np.uint8)[:, :, :3]
        return ScreenImage(bitmap=arr.copy(), bounds=r)

    def user_capture(self, prompt: str = "Select a region") -> Region | None:
        """Interactive region picker — deferred to the Flet IDE overlay. Phase 7."""
        raise NotImplementedError("Phase 7: Flet capture overlay")
