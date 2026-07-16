"""Field CRUD.

Reads go through the fields_geojson view so geometry arrives as GeoJSON rather
than WKB hex; writes send EWKT, which PostGIS casts to geometry(Polygon, 4326).
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from postgrest.exceptions import APIError
from shapely.errors import ShapelyError
from shapely.geometry import mapping, shape

from app.auth import CurrentUser
from app.config import get_settings
from app.geometry import GeometryError, validate_and_measure
from app.imagery.pipeline import OVERLAY_BUCKET, refresh_field
from app.imagery.stac import StacError
from app.schemas import (
    FieldCreate,
    FieldResponse,
    ObservationDetail,
    ObservationSummaryResponse,
    RefreshResponse,
)
from app.supabase_client import SupabaseNotConfiguredError, create_user_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/fields", tags=["fields"])

# Per Appendix A: at most one refresh per field per 10 minutes.
REFRESH_COOLDOWN = timedelta(minutes=10)

_UNAVAILABLE = HTTPException(
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    detail="This server is not connected to its database yet.",
)


def _as_rows(data: object) -> list[dict[str, Any]]:
    """Narrow PostgREST's loose JSON return type to the rows we expect.

    postgrest types `data` as any JSON value. Rather than cast and hope, assert
    the shape here so a surprising payload fails loudly at the boundary instead
    of as an AttributeError three frames deeper.
    """
    if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
        logger.error("unexpected PostgREST payload shape: %s", type(data).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Your fields could not be loaded.",
        )
    return data


def _row_to_response(row: dict[str, Any], geometry: dict[str, Any]) -> FieldResponse:
    return FieldResponse(
        id=row["id"],
        name=row["name"],
        area_ha=row["area_ha"],
        created_at=row["created_at"],
        geometry=geometry,
    )


@router.post("", response_model=FieldResponse, status_code=status.HTTP_201_CREATED)
async def create_field(payload: FieldCreate, user: CurrentUser) -> FieldResponse:
    try:
        polygon, area_ha = validate_and_measure(payload.geometry)
    except GeometryError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        client = await create_user_client(user.access_token)
    except SupabaseNotConfiguredError as exc:
        raise _UNAVAILABLE from exc

    record: dict[str, Any] = {
        "user_id": user.id,
        "name": payload.name,
        "geom": f"SRID=4326;{polygon.wkt}",
        "area_ha": round(area_ha, 4),
    }

    try:
        result = await client.table("fields").insert(record).execute()
    except APIError as exc:
        # RLS rejection surfaces here if user_id does not match the caller.
        logger.warning("field insert rejected: %s", exc.message)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That field could not be saved.",
        ) from exc

    rows = _as_rows(result.data)
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The field was not saved. Please try again.",
        )

    # Echo back the geometry we validated rather than re-reading it: the stored
    # value is byte-identical and this avoids a second round trip.
    return _row_to_response(rows[0], dict(mapping(polygon)))


@router.get("", response_model=list[FieldResponse])
async def list_fields(user: CurrentUser) -> list[FieldResponse]:
    try:
        client = await create_user_client(user.access_token)
    except SupabaseNotConfiguredError as exc:
        raise _UNAVAILABLE from exc

    try:
        result = (
            await client.table("fields_geojson")
            .select("id,name,area_ha,created_at,geometry")
            .order("created_at", desc=True)
            .execute()
        )
    except APIError as exc:
        logger.warning("field list failed: %s", exc.message)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Your fields could not be loaded.",
        ) from exc

    return [_row_to_response(row, row["geometry"]) for row in _as_rows(result.data)]


async def _load_field_row(client: Any, field_id: UUID) -> dict[str, Any]:
    """Fetch one field the caller owns (RLS enforced), or 404."""
    try:
        result = (
            await client.table("fields_geojson")
            .select("id,geometry,last_refreshed_at")
            .eq("id", str(field_id))
            .limit(1)
            .execute()
        )
    except APIError as exc:
        logger.warning("field load failed: %s", exc.message)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="That field could not be loaded.",
        ) from exc

    rows = _as_rows(result.data)
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Field not found.",
        )
    return rows[0]


def _enforce_cooldown(last_refreshed_at: Any) -> None:
    if not last_refreshed_at:
        return
    try:
        last = datetime.fromisoformat(str(last_refreshed_at))
    except ValueError:
        return
    elapsed = datetime.now(UTC) - last
    if elapsed < REFRESH_COOLDOWN:
        wait_s = int((REFRESH_COOLDOWN - elapsed).total_seconds())
        wait_min = wait_s // 60 + 1
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"This field was just refreshed. Try again in about {wait_min} minute(s).",
            headers={"Retry-After": str(wait_s)},
        )


@router.get("/{field_id}/refresh", response_model=RefreshResponse)
async def refresh(field_id: UUID, user: CurrentUser) -> RefreshResponse:
    settings = get_settings()
    if not settings.supabase_url:
        raise _UNAVAILABLE
    try:
        client = await create_user_client(user.access_token)
    except SupabaseNotConfiguredError as exc:
        raise _UNAVAILABLE from exc

    row = await _load_field_row(client, field_id)
    _enforce_cooldown(row.get("last_refreshed_at"))

    try:
        polygon = shape(row["geometry"])
    except (ShapelyError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="That field's outline could not be read.",
        ) from exc

    try:
        summary = await refresh_field(client, settings.supabase_url, str(field_id), polygon)
    except StacError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not reach the satellite catalog. Please try again shortly.",
        ) from exc

    # Stamp the cooldown only after a successful run, so a failed refresh does
    # not lock the field for ten minutes.
    try:
        await (
            client.table("fields")
            .update({"last_refreshed_at": datetime.now(UTC).isoformat()})
            .eq("id", str(field_id))
            .execute()
        )
    except APIError as exc:
        logger.warning("cooldown stamp failed for field %s: %s", field_id, exc.message)

    return RefreshResponse(
        scenes_found=summary.scenes_found,
        dates_processed=summary.dates_processed,
        valid_dates=summary.valid_dates,
        observations=[
            ObservationSummaryResponse(
                date=obs.date,
                scene_id=obs.scene_id,
                valid_pct=obs.valid_pct,
                median_ndvi=obs.median_ndvi,
                overlay_url=obs.overlay_url,
                bounds_wgs84=obs.bounds_wgs84,
            )
            for obs in summary.observations
        ],
    )


@router.get("/{field_id}/observations", response_model=list[ObservationDetail])
async def list_observations(field_id: UUID, user: CurrentUser) -> list[ObservationDetail]:
    settings = get_settings()
    try:
        client = await create_user_client(user.access_token)
    except SupabaseNotConfiguredError as exc:
        raise _UNAVAILABLE from exc

    # Confirms ownership (404 for someone else's field) before listing.
    await _load_field_row(client, field_id)

    try:
        result = (
            await client.table("observations")
            .select("date,scene_id,valid_pct,stats,zonal,overlay_path")
            .eq("field_id", str(field_id))
            .order("date", desc=True)
            .execute()
        )
    except APIError as exc:
        logger.warning("observation list failed: %s", exc.message)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Observations could not be loaded.",
        ) from exc

    base = settings.supabase_url or ""
    observations: list[ObservationDetail] = []
    for row in _as_rows(result.data):
        path = row.get("overlay_path")
        url = f"{base}/storage/v1/object/public/{OVERLAY_BUCKET}/{path}" if path and base else None
        observations.append(
            ObservationDetail(
                date=str(row["date"]),
                scene_id=row["scene_id"],
                valid_pct=row["valid_pct"],
                stats=row["stats"],
                zonal=row["zonal"],
                overlay_url=url,
            )
        )
    return observations
