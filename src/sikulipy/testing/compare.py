"""OpenCV-based image comparison for visual assertions.

Three modes — pick by ``ImageDiff.mode``:

* ``exact`` — :func:`cv2.absdiff` per-pixel; counts pixels whose
  abs-difference (over any channel) exceeds ``tolerance``. Fails if
  the fraction of changed pixels is above ``threshold``. Default:
  ``tolerance=8`` (out of 255), ``threshold=0.005``.
* ``ssim`` — structural similarity (``skimage.metrics.
  structural_similarity``) on luma channel. Fails if ``score <
  threshold``. Default: ``threshold=0.97``. Robust to anti-aliasing
  and font hinting drift; this is the default mode.
* ``template`` — :func:`cv2.matchTemplate` (``TM_CCOEFF_NORMED``).
  Treats the *expected* image as a tight crop and the *actual* as a
  larger frame; passes if best match score ``>= threshold``. Default:
  ``threshold=0.92``. Returns the matched bbox so callers can chain
  visual + text assertions on the same region.

All modes return :class:`ImageDiff` with ``passed``, the numeric
``score``, an optional ``diff_image`` for failure artefacts, and the
matched ``bbox`` (template mode only).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    import numpy as np


Mode = Literal["exact", "ssim", "template"]


@dataclass
class ImageDiff:
    """Result of one image comparison.

    ``score`` semantics depend on ``mode``:
    * exact — fraction of *changed* pixels (lower is better).
    * ssim — SSIM score in ``[-1, 1]`` (higher is better).
    * template — matchTemplate peak in ``[-1, 1]`` (higher is better).
    """

    passed: bool
    mode: Mode
    score: float
    threshold: float
    diff_image: "np.ndarray | None" = None
    bbox: tuple[int, int, int, int] | None = None
    message: str = ""


_DEFAULT_THRESHOLD: dict[Mode, float] = {
    "exact": 0.005,
    "ssim": 0.97,
    "template": 0.92,
}


def compare_images(
    actual: "np.ndarray",
    expected: "np.ndarray",
    *,
    mode: Mode = "ssim",
    threshold: float | None = None,
    tolerance: int = 8,
) -> ImageDiff:
    """Compare ``actual`` against ``expected`` using ``mode``.

    ``actual`` and ``expected`` are BGR :class:`numpy.ndarray` images
    as returned by ``cv2.imread`` / ``cv2.imdecode``. Sizes must match
    for ``exact``/``ssim``; ``template`` allows ``actual`` to be
    larger (the search frame).
    """
    if mode not in _DEFAULT_THRESHOLD:
        raise ValueError(f"unknown compare mode: {mode!r}")
    th = _DEFAULT_THRESHOLD[mode] if threshold is None else float(threshold)

    if mode == "exact":
        return _compare_exact(actual, expected, threshold=th, tolerance=tolerance)
    if mode == "ssim":
        return _compare_ssim(actual, expected, threshold=th)
    return _compare_template(actual, expected, threshold=th)


def _require_same_shape(
    actual: "np.ndarray", expected: "np.ndarray", mode: Mode
) -> None:
    if actual.shape[:2] != expected.shape[:2]:
        raise ValueError(
            f"{mode} mode requires equal image sizes; got "
            f"actual={actual.shape[:2]} expected={expected.shape[:2]}"
        )


def _compare_exact(
    actual: "np.ndarray",
    expected: "np.ndarray",
    *,
    threshold: float,
    tolerance: int,
) -> ImageDiff:
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    _require_same_shape(actual, expected, "exact")
    diff = cv2.absdiff(actual, expected)
    if diff.ndim == 3:
        per_pixel = diff.max(axis=2)
    else:
        per_pixel = diff
    changed = np.count_nonzero(per_pixel > tolerance)
    total = per_pixel.size
    fraction = float(changed) / float(total) if total else 0.0
    passed = fraction <= threshold
    msg = "" if passed else (
        f"{changed}/{total} pixels exceeded tolerance={tolerance}; "
        f"fraction={fraction:.4f} > threshold={threshold:.4f}"
    )
    return ImageDiff(
        passed=passed,
        mode="exact",
        score=fraction,
        threshold=threshold,
        diff_image=diff,
        message=msg,
    )


def _compare_ssim(
    actual: "np.ndarray",
    expected: "np.ndarray",
    *,
    threshold: float,
) -> ImageDiff:
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    _require_same_shape(actual, expected, "ssim")
    try:
        from skimage.metrics import structural_similarity as _ssim
    except ImportError as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "ssim mode requires scikit-image; install with "
            "`pip install scikit-image`"
        ) from exc

    a_gray = cv2.cvtColor(actual, cv2.COLOR_BGR2GRAY) if actual.ndim == 3 else actual
    e_gray = cv2.cvtColor(expected, cv2.COLOR_BGR2GRAY) if expected.ndim == 3 else expected
    score, diff = _ssim(e_gray, a_gray, full=True)
    score = float(score)
    diff_u8 = (np.clip(diff, 0.0, 1.0) * 255).astype("uint8")
    passed = score >= threshold
    msg = "" if passed else (
        f"SSIM {score:.4f} < threshold {threshold:.4f}"
    )
    return ImageDiff(
        passed=passed,
        mode="ssim",
        score=score,
        threshold=threshold,
        diff_image=diff_u8,
        message=msg,
    )


def _compare_template(
    actual: "np.ndarray",
    expected: "np.ndarray",
    *,
    threshold: float,
) -> ImageDiff:
    import cv2  # noqa: PLC0415

    if (
        actual.shape[0] < expected.shape[0]
        or actual.shape[1] < expected.shape[1]
    ):
        raise ValueError(
            "template mode requires actual >= expected in both dims; "
            f"got actual={actual.shape[:2]} expected={expected.shape[:2]}"
        )
    res = cv2.matchTemplate(actual, expected, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    score = float(max_val)
    h, w = expected.shape[:2]
    bbox = (int(max_loc[0]), int(max_loc[1]), int(w), int(h))
    passed = score >= threshold
    msg = "" if passed else (
        f"template match {score:.4f} < threshold {threshold:.4f}"
    )
    return ImageDiff(
        passed=passed,
        mode="template",
        score=score,
        threshold=threshold,
        bbox=bbox,
        message=msg,
    )
