"""Render an NDVI array to a colored PNG overlay.

Brown (bare/stressed) through yellow to deep green (vigorous). Pixels outside
the field or masked as cloud are fully transparent, so the overlay hugs the
field footprint when pinned to its geographic bounds on the map.
"""

from __future__ import annotations

import io

import numpy as np
import numpy.typing as npt
from PIL import Image

FloatArray = npt.NDArray[np.float32]
BoolArray = npt.NDArray[np.bool_]

# NDVI values are clamped to this range before coloring. Below ~0.1 is bare soil
# or water; healthy crops saturate the green end well before 1.0.
_NDVI_MIN = 0.0
_NDVI_MAX = 0.8

# Control points (NDVI stop, R, G, B) for a brown->green ramp.
_STOPS: tuple[tuple[float, tuple[int, int, int]], ...] = (
    (0.00, (140, 81, 10)),
    (0.20, (191, 129, 45)),
    (0.35, (223, 194, 125)),
    (0.50, (199, 234, 177)),
    (0.65, (127, 188, 65)),
    (0.80, (35, 132, 67)),
)


def _ramp() -> npt.NDArray[np.uint8]:
    """A 256x3 lookup table interpolated across the control points."""
    xs = np.linspace(_NDVI_MIN, _NDVI_MAX, 256)
    stop_xs = np.array([s[0] for s in _STOPS])
    channels = []
    for channel in range(3):
        stop_ys = np.array([s[1][channel] for s in _STOPS])
        channels.append(np.interp(xs, stop_xs, stop_ys))
    return np.stack(channels, axis=1).astype(np.uint8)


_RAMP = _ramp()


def render_ndvi_png(ndvi: FloatArray, effective: BoolArray) -> bytes:
    """Encode NDVI as an RGBA PNG. `effective` pixels are opaque, others clear."""
    clamped = np.clip(np.nan_to_num(ndvi, nan=_NDVI_MIN), _NDVI_MIN, _NDVI_MAX)
    index = np.round((clamped - _NDVI_MIN) / (_NDVI_MAX - _NDVI_MIN) * 255).astype(np.intp)
    index = np.clip(index, 0, 255)

    rgb = _RAMP[index]  # (H, W, 3)
    alpha = np.where(effective, 255, 0).astype(np.uint8)
    rgba = np.dstack([rgb, alpha[..., np.newaxis]]).astype(np.uint8)

    buffer = io.BytesIO()
    Image.fromarray(rgba, mode="RGBA").save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
