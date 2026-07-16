"""NDVI PNG rendering."""

import io

import numpy as np
from PIL import Image

from app.imagery.render import render_ndvi_png


def _decode(png: bytes) -> np.ndarray:
    return np.array(Image.open(io.BytesIO(png)).convert("RGBA"))


def test_output_is_a_valid_rgba_png_of_the_right_size() -> None:
    ndvi = np.full((12, 8), 0.5, dtype=np.float32)
    eff = np.ones((12, 8), dtype=bool)
    img = _decode(render_ndvi_png(ndvi, eff))
    assert img.shape == (12, 8, 4)


def test_masked_pixels_are_transparent_and_valid_pixels_opaque() -> None:
    ndvi = np.full((4, 4), 0.6, dtype=np.float32)
    eff = np.ones((4, 4), dtype=bool)
    eff[0, 0] = False
    img = _decode(render_ndvi_png(ndvi, eff))
    assert img[0, 0, 3] == 0  # masked -> transparent
    assert img[2, 2, 3] == 255  # kept -> opaque


def test_high_ndvi_is_greener_than_low_ndvi() -> None:
    low = _decode(render_ndvi_png(np.full((2, 2), 0.1, np.float32), np.ones((2, 2), bool)))
    high = _decode(render_ndvi_png(np.full((2, 2), 0.75, np.float32), np.ones((2, 2), bool)))
    # Green channel dominates red at the healthy end; the reverse at the bare end.
    assert high[0, 0, 1] > high[0, 0, 0]
    assert low[0, 0, 0] > low[0, 0, 1]


def test_nan_pixels_do_not_crash_and_render_transparent() -> None:
    ndvi = np.full((3, 3), np.nan, dtype=np.float32)
    eff = np.zeros((3, 3), dtype=bool)
    img = _decode(render_ndvi_png(ndvi, eff))
    assert (img[..., 3] == 0).all()
