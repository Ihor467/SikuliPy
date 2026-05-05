"""Golden image store for visual assertions.

Layout under ``<project>/baselines/web/<host>/``:

* ``<asset>.png`` — the locked-in expected crop. Captured at CSS-pixel
  size (``actual_pixel / dpr``) so a Retina-class capture matches a
  DPR=1 CI runner.
* ``.metadata.json`` (per host folder) — keeps the recorded DPR /
  viewport / capture timestamp so promotion can warn if the new
  baseline was taken under different conditions.

Promotion is gated by an explicit flag (``--update-baselines`` from
the pytest plugin); the API exposed here is intentionally low-level
so the plugin and the IDE can share it.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    import numpy as np


_METADATA = ".metadata.json"


@dataclass
class BaselineMetadata:
    """Per-host metadata side-car."""

    dpr: float = 1.0
    viewport: tuple[int, int] = (1600, 900)
    notes: dict[str, str] = field(default_factory=dict)

    def to_json(self) -> dict:
        return {
            "dpr": self.dpr,
            "viewport": list(self.viewport),
            "notes": self.notes,
        }

    @classmethod
    def from_json(cls, data: dict) -> "BaselineMetadata":
        vp = data.get("viewport") or [1600, 900]
        return cls(
            dpr=float(data.get("dpr", 1.0)),
            viewport=(int(vp[0]), int(vp[1])),
            notes=dict(data.get("notes") or {}),
        )


class BaselineStore:
    """File-backed baseline catalogue rooted at ``<project>/baselines``.

    ``host`` is the page-object host slug (e.g. ``example.com``); each
    ``asset`` is the same filename used in the recorder asset folder
    so the user can eyeball the correspondence without renaming.
    """

    def __init__(self, project_dir: Path, host: str) -> None:
        self.project_dir = Path(project_dir)
        self.host = host
        self.host_dir = self.project_dir / "baselines" / "web" / host

    # ---- Paths ------------------------------------------------------
    def path_for(self, asset: str) -> Path:
        return self.host_dir / asset

    def metadata_path(self) -> Path:
        return self.host_dir / _METADATA

    def exists(self, asset: str) -> bool:
        return self.path_for(asset).is_file()

    # ---- I/O --------------------------------------------------------
    def load(self, asset: str) -> "np.ndarray":
        """Read the baseline as BGR ndarray. Raises if missing."""
        import cv2  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415

        target = self.path_for(asset)
        if not target.is_file():
            raise FileNotFoundError(
                f"baseline missing: {target}. Run with "
                f"--update-baselines to seed it from the current frame."
            )
        data = np.fromfile(str(target), dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if img is None:
            raise OSError(f"cv2.imdecode failed for {target}")
        return img

    def write(self, asset: str, image: "np.ndarray") -> Path:
        """Write or replace ``asset`` on disk. Returns the path."""
        import cv2  # noqa: PLC0415

        target = self.path_for(asset)
        target.parent.mkdir(parents=True, exist_ok=True)
        ok = cv2.imwrite(str(target), image)
        if not ok:
            raise OSError(f"cv2.imwrite failed for {target}")
        return target

    def promote_from(self, asset: str, source: Path) -> Path:
        """Copy a captured PNG into the baseline slot (no decode)."""
        target = self.path_for(asset)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(source), str(target))
        return target

    def remove(self, asset: str) -> bool:
        target = self.path_for(asset)
        if target.is_file():
            target.unlink()
            return True
        return False

    # ---- Metadata ---------------------------------------------------
    def read_metadata(self) -> BaselineMetadata:
        path = self.metadata_path()
        if not path.is_file():
            return BaselineMetadata()
        try:
            return BaselineMetadata.from_json(
                json.loads(path.read_text(encoding="utf-8"))
            )
        except (OSError, json.JSONDecodeError, KeyError):
            return BaselineMetadata()

    def write_metadata(self, meta: BaselineMetadata) -> Path:
        path = self.metadata_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(meta.to_json(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return path

    # ---- Listing ----------------------------------------------------
    def list_assets(self) -> list[str]:
        if not self.host_dir.is_dir():
            return []
        return sorted(
            p.name for p in self.host_dir.iterdir()
            if p.is_file() and p.suffix.lower() == ".png"
        )
