"""Where Web-Auto captured PNGs live + how they're cropped.

Layout: ``<project>/assets/web/<host>/<slug>.png``. One folder per
host so a project that automates several sites doesn't end up with
hundreds of patterns sharing a flat directory. Filenames are slugified
from role + accessible name + a short selector hash so two different
elements with the same visible text don't collide.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    import numpy as np

from sikulipy.web.elements import WebElement


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _host_for(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.hostname or "unknown"
    return host.lower()


def asset_root(project_dir: Path | str, url: str) -> Path:
    """Return ``<project>/assets/web/<host>/``, creating it if needed."""
    base = Path(project_dir) / "assets" / "web" / _host_for(url)
    base.mkdir(parents=True, exist_ok=True)
    return base


def slug_for_element(el: WebElement) -> str:
    """Filesystem-safe slug: ``role-name-<hash6>`` (hash from selector).

    The hash component disambiguates two visually-identical buttons
    (e.g. several "Add to cart" buttons on a product page) so the
    second one doesn't overwrite the first.
    """
    role = _SLUG_RE.sub("-", el.display_role.lower()).strip("-") or "el"
    name = _SLUG_RE.sub("-", el.display_name.lower()).strip("-") or "unnamed"
    digest = hashlib.sha1(el.selector.encode("utf-8")).hexdigest()[:6]
    # Cap each segment to keep the final filename comfortable on every
    # filesystem (Windows path-component limit is 255 bytes).
    return f"{role[:24]}-{name[:48]}-{digest}"


def crop_element(
    frame: "np.ndarray",
    bounds: tuple[float, float, float, float],
    *,
    pad: int = 4,
    device_pixel_ratio: float = 1.0,
) -> "np.ndarray":
    """Crop ``frame`` (BGR ndarray) to ``bounds`` plus a small padding.

    ``bounds`` is in CSS pixels; the captured PNG was rendered at
    ``device_pixel_ratio`` so we scale before slicing. ``pad`` is in
    *frame* pixels (post-DPR) — a few pixels around the element keep
    Pattern matching tolerant to subpixel anti-aliasing without
    swallowing surrounding chrome.
    """
    if frame is None:  # pragma: no cover - defensive
        raise ValueError("frame is None")
    h, w = frame.shape[:2]
    x = int(bounds[0] * device_pixel_ratio) - pad
    y = int(bounds[1] * device_pixel_ratio) - pad
    bw = int(bounds[2] * device_pixel_ratio) + pad * 2
    bh = int(bounds[3] * device_pixel_ratio) + pad * 2
    x0 = max(0, x)
    y0 = max(0, y)
    x1 = min(w, x + bw)
    y1 = min(h, y + bh)
    if x1 <= x0 or y1 <= y0:
        raise ValueError(f"bounds out of frame: {bounds!r} vs {(w, h)}")
    return frame[y0:y1, x0:x1].copy()


def write_png(target: Path, image: "np.ndarray") -> Path:
    """Write a BGR ndarray to ``target`` as a PNG. Lazy cv2 import."""
    import cv2  # noqa: PLC0415 — keep cv2 out of headless test paths

    target.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(target), image)
    if not ok:
        raise OSError(f"cv2.imwrite failed for {target}")
    return target
