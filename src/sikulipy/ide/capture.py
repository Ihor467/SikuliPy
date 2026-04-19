"""Pattern capture overlay — headless state model.

Ports the *behaviour* of ``OverlayCapturePrompt.java``: the user drags
out a rectangle on top of a frozen screenshot and the IDE saves the
crop as a PNG pattern. The Java version was a Swing window; here we
model only the state transitions and the cropping so the Flet overlay
(or a unit test) can drive it without pulling in any UI framework.

State machine::

    idle --start--> selecting --update--> selecting --commit--> captured
                          \\--cancel-----> cancelled

"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:  # numpy/cv2 are optional on this host
    import numpy as np

CaptureState = Literal["idle", "selecting", "captured", "cancelled"]


@dataclass(frozen=True)
class CaptureRect:
    """Inclusive-exclusive rectangle in screen coordinates."""

    x: int
    y: int
    w: int
    h: int

    @classmethod
    def from_corners(cls, x1: int, y1: int, x2: int, y2: int) -> "CaptureRect":
        x, w = (x1, x2 - x1) if x2 >= x1 else (x2, x1 - x2)
        y, h = (y1, y2 - y1) if y2 >= y1 else (y2, y1 - y2)
        return cls(x=x, y=y, w=w, h=h)

    @property
    def is_empty(self) -> bool:
        return self.w <= 0 or self.h <= 0


@dataclass
class CaptureSession:
    """Coordinates one capture interaction.

    The session owns the frozen background screenshot (a BGR ndarray)
    plus the live drag rectangle. The Flet overlay calls :meth:`begin`
    on mouse-down, :meth:`update` while dragging, :meth:`commit` on
    mouse-up, or :meth:`cancel` on Esc.
    """

    screenshot: "np.ndarray | None" = None
    state: CaptureState = "idle"
    rect: CaptureRect | None = None
    saved_path: Path | None = None
    _anchor: tuple[int, int] | None = field(default=None, repr=False)

    # ---- State transitions -----------------------------------------
    def begin(self, x: int, y: int) -> None:
        self._anchor = (x, y)
        self.rect = CaptureRect(x=x, y=y, w=0, h=0)
        self.state = "selecting"

    def update(self, x: int, y: int) -> None:
        if self.state != "selecting" or self._anchor is None:
            return
        ax, ay = self._anchor
        self.rect = CaptureRect.from_corners(ax, ay, x, y)

    def cancel(self) -> None:
        self.state = "cancelled"
        self.rect = None
        self._anchor = None

    def commit(self) -> CaptureRect | None:
        if self.state != "selecting" or self.rect is None or self.rect.is_empty:
            self.cancel()
            return None
        self.state = "captured"
        self._anchor = None
        return self.rect

    # ---- Saving -----------------------------------------------------
    def save(self, path: str | Path) -> Path:
        """Crop the screenshot to ``self.rect`` and write a PNG."""
        if self.state != "captured" or self.rect is None:
            raise RuntimeError("CaptureSession.save() requires a committed selection")
        if self.screenshot is None:
            raise RuntimeError("CaptureSession.save() requires a screenshot")

        try:
            import cv2  # type: ignore[import-not-found]
        except Exception as exc:  # pragma: no cover - host without cv2
            raise RuntimeError("OpenCV (cv2) is required to save patterns") from exc

        target = Path(path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)

        r = self.rect
        crop = self.screenshot[r.y : r.y + r.h, r.x : r.x + r.w]
        ok = bool(cv2.imwrite(str(target), crop))
        if not ok:
            raise OSError(f"cv2.imwrite failed for {target}")
        self.saved_path = target
        return target

    def reset(self) -> None:
        self.state = "idle"
        self.rect = None
        self.saved_path = None
        self._anchor = None
