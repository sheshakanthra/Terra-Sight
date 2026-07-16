"""Pure NDVI / masking / statistics functions.

Nothing in this module does I/O. It operates on numpy arrays already read and
aligned to a common 10 m grid, which keeps the scientifically load-bearing logic
— cloud masking, the valid-pixel gate, NDVI, zonal stats — unit-testable without
touching the network.
"""

from typing import Final

import numpy as np
import numpy.typing as npt

# SCL (Scene Classification Layer) classes to exclude. Per Appendix B this rule
# is sacred: 3 cloud shadow, 8 cloud medium-probability, 9 cloud high-probability,
# 10 thin cirrus, 11 snow/ice. NDVI is never computed through these.
MASKED_SCL_CLASSES: Final[frozenset[int]] = frozenset({3, 8, 9, 10, 11})

# A date is only usable if at least this fraction of the field's pixels survive
# masking. Below it the scene is discarded — no stats, no observation.
MIN_VALID_FRACTION: Final = 0.60

ZONE_GRID: Final = 3  # 3x3 zonal grid

FloatArray = npt.NDArray[np.float32]
BoolArray = npt.NDArray[np.bool_]
IntArray = npt.NDArray[np.uint8]


def compute_ndvi(red: FloatArray, nir: FloatArray) -> FloatArray:
    """NDVI = (NIR - red) / (NIR + red), with NaN where the sum is non-positive.

    A zero denominator (both bands zero — nodata gaps) would divide by zero;
    those pixels become NaN and are excluded downstream rather than skewing
    statistics toward zero.
    """
    red = red.astype(np.float32, copy=False)
    nir = nir.astype(np.float32, copy=False)
    denom = nir + red
    with np.errstate(divide="ignore", invalid="ignore"):
        ndvi = np.where(denom > 0, (nir - red) / denom, np.nan)
    return ndvi.astype(np.float32)


def scl_valid_mask(scl: IntArray) -> BoolArray:
    """True where the SCL class is acceptable (not cloud/shadow/cirrus/snow)."""
    return ~np.isin(scl, list(MASKED_SCL_CLASSES))


def effective_mask(field_mask: BoolArray, valid_mask: BoolArray, ndvi: FloatArray) -> BoolArray:
    """Pixels that are inside the field, cloud-free, and have finite NDVI."""
    return field_mask & valid_mask & np.isfinite(ndvi)


def valid_fraction(field_mask: BoolArray, effective: BoolArray) -> float:
    """Share of in-field pixels that survived masking. 0.0 if the field is empty."""
    field_total = int(field_mask.sum())
    if field_total == 0:
        return 0.0
    return float(effective.sum()) / field_total


def summarize(ndvi: FloatArray, effective: BoolArray) -> dict[str, float] | None:
    """Mean / median / p10 / p90 over the effective pixels, or None if none."""
    values = ndvi[effective]
    if values.size == 0:
        return None
    return {
        "mean": round(float(np.mean(values)), 4),
        "median": round(float(np.median(values)), 4),
        "p10": round(float(np.percentile(values, 10)), 4),
        "p90": round(float(np.percentile(values, 90)), 4),
        "n_pixels": int(values.size),
    }


def _zone_bounds(length: int, index: int) -> tuple[int, int]:
    """Split an axis of `length` pixels into ZONE_GRID near-equal parts."""
    start = (length * index) // ZONE_GRID
    stop = (length * (index + 1)) // ZONE_GRID
    return start, stop


def zonal_stats(
    ndvi: FloatArray, field_mask: BoolArray, effective: BoolArray
) -> list[dict[str, object]]:
    """Per-zone NDVI stats over a 3x3 grid laid on the array's bounding box.

    Zones are indexed row-major from the top-left: row 0 is the northern band
    (arrays are north-up), so zone (row=0, col=0) is the north-west corner —
    the localisation that powers "NW zone down 14%" alerts in Phase 3.
    """
    rows, cols = ndvi.shape
    zones: list[dict[str, object]] = []
    for row in range(ZONE_GRID):
        r0, r1 = _zone_bounds(rows, row)
        for col in range(ZONE_GRID):
            c0, c1 = _zone_bounds(cols, col)
            sub_ndvi = ndvi[r0:r1, c0:c1]
            sub_field = field_mask[r0:r1, c0:c1]
            sub_eff = effective[r0:r1, c0:c1]
            stats = summarize(sub_ndvi, sub_eff)
            zones.append(
                {
                    "row": row,
                    "col": col,
                    "valid_pct": round(valid_fraction(sub_field, sub_eff) * 100, 1),
                    "stats": stats,
                }
            )
    return zones
