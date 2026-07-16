"""Refresh orchestration: search -> read -> mask -> stats -> render -> persist.

The rasterio work is synchronous and CPU/IO-blocking, so each scene is analyzed
in a worker thread; storage upload and the observations upsert are async against
Supabase.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, Final

from shapely.geometry import Polygon
from supabase import AsyncClient

from app.imagery.analysis import (
    MIN_VALID_FRACTION,
    compute_ndvi,
    effective_mask,
    scl_valid_mask,
    summarize,
    valid_fraction,
    zonal_stats,
)
from app.imagery.raster import RasterReadError, read_field_arrays
from app.imagery.render import render_ndvi_png
from app.imagery.stac import Scene, StacError, search_scenes

logger = logging.getLogger(__name__)

OVERLAY_BUCKET: Final = "ndvi-overlays"

# Cap on how many distinct dates a single refresh will process, newest first.
# The revisit cadence yields ~9 dates in 45 days; the cap bounds worst-case
# latency and range-read volume without threatening the >=3 valid dates target.
MAX_DATES: Final = 15


@dataclass(frozen=True)
class SceneAnalysis:
    date: date
    scene_id: str
    stats: dict[str, float]
    zonal: list[dict[str, object]]
    valid_pct: float
    overlay_png: bytes
    bounds_wgs84: tuple[float, float, float, float]


@dataclass(frozen=True)
class ObservationSummary:
    date: str
    scene_id: str
    valid_pct: float
    median_ndvi: float
    overlay_url: str
    bounds_wgs84: tuple[float, float, float, float]


@dataclass(frozen=True)
class RefreshSummary:
    scenes_found: int
    dates_processed: int
    valid_dates: int
    observations: list[ObservationSummary]


def analyze_scene(scene: Scene, polygon: Polygon) -> SceneAnalysis | None:
    """Read, mask, and summarize one scene. None if the date is not usable.

    Pure of Supabase — only reads from AWS and computes — so it runs safely in a
    worker thread. Returns None when under 60% of field pixels survive masking
    (the sacred cloud gate) or no pixels remain.
    """
    arrays = read_field_arrays(scene, polygon)
    ndvi = compute_ndvi(arrays.red, arrays.nir)
    valid = scl_valid_mask(arrays.scl)
    effective = effective_mask(arrays.field_mask, valid, ndvi)

    fraction = valid_fraction(arrays.field_mask, effective)
    if fraction < MIN_VALID_FRACTION:
        logger.info("scene %s discarded: valid fraction %.2f", scene.scene_id, fraction)
        return None

    stats = summarize(ndvi, effective)
    if stats is None:
        return None

    return SceneAnalysis(
        date=scene.date.date(),
        scene_id=scene.scene_id,
        stats=stats,
        zonal=zonal_stats(ndvi, arrays.field_mask, effective),
        valid_pct=round(fraction * 100, 1),
        overlay_png=render_ndvi_png(ndvi, effective),
        bounds_wgs84=arrays.bounds_wgs84,
    )


def _candidates_by_date(scenes: list[Scene]) -> list[tuple[date, list[Scene]]]:
    """Group scenes by calendar date, newest date first, clearest scene first.

    Adjacent Sentinel-2 tiles produce more than one item for the same date over
    a field near a tile edge, and one of them may only partially cover the field.
    Rather than commit to the lowest-cloud scene up front — which for an edge
    field can be the tile that does *not* cover it — each date keeps all its
    candidates so the caller can fall back to a covering tile.
    """
    by_date: dict[date, list[Scene]] = {}
    for scene in scenes:
        by_date.setdefault(scene.date.date(), []).append(scene)
    for candidates in by_date.values():
        candidates.sort(key=lambda s: s.cloud_cover)
    ordered = sorted(by_date.items(), key=lambda kv: kv[0], reverse=True)
    return ordered[:MAX_DATES]


async def _persist(
    client: AsyncClient,
    supabase_url: str,
    field_id: str,
    analysis: SceneAnalysis,
) -> ObservationSummary:
    path = f"{field_id}/{analysis.date.isoformat()}.png"
    await client.storage.from_(OVERLAY_BUCKET).upload(
        path,
        analysis.overlay_png,
        {"content-type": "image/png", "upsert": "true"},
    )

    record: dict[str, Any] = {
        "field_id": field_id,
        "date": analysis.date.isoformat(),
        "scene_id": analysis.scene_id,
        "stats": analysis.stats,
        "zonal": analysis.zonal,
        "valid_pct": analysis.valid_pct,
        "overlay_path": path,
    }
    await client.table("observations").upsert(record, on_conflict="field_id,date").execute()

    overlay_url = f"{supabase_url}/storage/v1/object/public/{OVERLAY_BUCKET}/{path}"
    return ObservationSummary(
        date=analysis.date.isoformat(),
        scene_id=analysis.scene_id,
        valid_pct=analysis.valid_pct,
        median_ndvi=float(analysis.stats["median"]),
        overlay_url=overlay_url,
        bounds_wgs84=analysis.bounds_wgs84,
    )


async def refresh_field(
    client: AsyncClient,
    supabase_url: str,
    field_id: str,
    polygon: Polygon,
) -> RefreshSummary:
    """Search recent scenes, analyze each usable date, persist observations."""
    try:
        scenes = await asyncio.to_thread(search_scenes, polygon.bounds)
    except StacError:
        raise

    dates = _candidates_by_date(scenes)
    observations: list[ObservationSummary] = []

    for _day, candidates in dates:
        analysis = await _first_usable(candidates, polygon)
        if analysis is not None:
            observations.append(await _persist(client, supabase_url, field_id, analysis))

    observations.sort(key=lambda o: o.date, reverse=True)
    return RefreshSummary(
        scenes_found=len(scenes),
        dates_processed=len(dates),
        valid_dates=len(observations),
        observations=observations,
    )


async def _first_usable(candidates: list[Scene], polygon: Polygon) -> SceneAnalysis | None:
    """Analyze a date's candidate scenes in cloud order; return the first that
    passes the valid-pixel gate, or None if none do."""
    for scene in candidates:
        try:
            analysis = await asyncio.to_thread(analyze_scene, scene, polygon)
        except (RasterReadError, ValueError) as exc:
            logger.warning("scene %s skipped: %s", scene.scene_id, exc)
            continue
        if analysis is not None:
            return analysis
    return None
