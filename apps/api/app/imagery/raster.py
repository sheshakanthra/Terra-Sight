"""Windowed Cloud-Optimized GeoTIFF reads and field rasterization.

Only the field's window is read from each COG via HTTP range requests —
kilobytes per band, never a whole scene. Red and NIR arrive at 10 m; SCL is
20 m and is resampled onto the 10 m grid so the three align pixel-for-pixel.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import rasterio
from rasterio.enums import Resampling
from rasterio.errors import RasterioError
from rasterio.features import rasterize
from rasterio.warp import transform_bounds
from rasterio.windows import Window, from_bounds
from rasterio.windows import transform as window_transform
from shapely.geometry import Polygon, mapping
from shapely.ops import transform as shapely_transform

from app.imagery.stac import Scene

logger = logging.getLogger(__name__)

# GDAL/curl tuning for reading remote COGs efficiently and without AWS creds
# (the Sentinel-2 bucket is public).
_GDAL_ENV = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
    "GDAL_HTTP_MULTIPLEX": "YES",
    "GDAL_HTTP_MAX_RETRY": "3",
    "GDAL_HTTP_RETRY_DELAY": "1",
    "AWS_NO_SIGN_REQUEST": "YES",
    "VSI_CACHE": "TRUE",
}

FloatArray = npt.NDArray[np.float32]
BoolArray = npt.NDArray[np.bool_]
IntArray = npt.NDArray[np.uint8]


class RasterReadError(RuntimeError):
    """A COG window could not be read."""


@dataclass(frozen=True)
class FieldArrays:
    """Aligned band windows plus the field mask and georeferencing.

    bounds_wgs84 is (west, south, east, north) in EPSG:4326 — the extent a map
    image-overlay must be pinned to for the PNG to line up with the ground.
    """

    red: FloatArray
    nir: FloatArray
    scl: IntArray
    field_mask: BoolArray
    bounds_wgs84: tuple[float, float, float, float]


def _reproject_polygon(polygon: Polygon, dst_crs: rasterio.crs.CRS) -> Polygon:
    from pyproj import Transformer

    transformer = Transformer.from_crs("EPSG:4326", dst_crs, always_xy=True)
    return shapely_transform(
        lambda xs, ys: transformer.transform(xs, ys), polygon
    )


def _read_aligned(
    href: str, bounds: tuple[float, float, float, float], out_shape: tuple[int, int],
    resampling: Resampling,
) -> npt.NDArray[np.generic]:
    """Read a band over `bounds`, boundless, onto exactly out_shape.

    boundless with fill 0 means a field near a tile edge (only partially covered
    by this scene) still returns a full-shaped array; the uncovered pixels are 0
    and fall out as NaN NDVI / non-vegetation downstream, so they correctly count
    as invalid rather than crashing on a shape mismatch.
    """
    with rasterio.open(href) as src:
        window = from_bounds(*bounds, src.transform)
        data: npt.NDArray[np.generic] = src.read(
            1,
            window=window,
            out_shape=out_shape,
            resampling=resampling,
            boundless=True,
            fill_value=0,
        )
        return data


def read_field_arrays(scene: Scene, polygon: Polygon) -> FieldArrays:
    """Read red/NIR/SCL over the field's window and rasterize the field mask.

    Raises RasterReadError on any network/raster failure, and ValueError if the
    field footprint is too small to yield any pixels.
    """
    bbox_wgs84 = polygon.bounds  # (minx, miny, maxx, maxy) in lon/lat

    try:
        with rasterio.Env(**_GDAL_ENV):
            with rasterio.open(scene.red_href) as red_src:
                crs = red_src.crs
                left, bottom, right, top = transform_bounds("EPSG:4326", crs, *bbox_wgs84)
                ref_bounds = (left, bottom, right, top)

                window = from_bounds(*ref_bounds, red_src.transform)
                window = _round_window(window)
                if window.width < 1 or window.height < 1:
                    raise ValueError("Field footprint is smaller than one pixel.")
                shape = (int(window.height), int(window.width))
                win_transform = window_transform(window, red_src.transform)

                red = red_src.read(
                    1, window=window, boundless=True, fill_value=0
                ).astype(np.float32)

            nir = _read_aligned(scene.nir_href, ref_bounds, shape, Resampling.bilinear)
            scl = _read_aligned(scene.scl_href, ref_bounds, shape, Resampling.nearest)
    except (RasterioError, OSError) as exc:
        logger.warning("windowed read failed for scene %s: %s", scene.scene_id, exc)
        raise RasterReadError("Could not read satellite imagery for this field.") from exc

    field_projected = _reproject_polygon(polygon, crs)
    field_mask = rasterize(
        [(mapping(field_projected), 1)],
        out_shape=shape,
        transform=win_transform,
        fill=0,
        all_touched=False,
        dtype="uint8",
    ).astype(bool)

    # The map overlay is pinned to the actual pixel-window extent, not the raw
    # field bbox, so it stays aligned after the window was rounded to pixels.
    pixel_bounds = _window_bounds(win_transform, shape)
    west, south, east, north = transform_bounds(crs, "EPSG:4326", *pixel_bounds)
    return FieldArrays(
        red=red,
        nir=nir.astype(np.float32),
        scl=scl.astype(np.uint8),
        field_mask=field_mask,
        bounds_wgs84=(west, south, east, north),
    )


def _round_window(window: Window) -> Window:
    return window.round_offsets(op="floor").round_lengths(op="ceil")


def _window_bounds(
    transform: rasterio.Affine, shape: tuple[int, int]
) -> tuple[float, float, float, float]:
    rows, cols = shape
    west, north = transform * (0, 0)
    east, south = transform * (cols, rows)
    return west, south, east, north
