"""Field CRUD.

Reads go through the fields_geojson view so geometry arrives as GeoJSON rather
than WKB hex; writes send EWKT, which PostGIS casts to geometry(Polygon, 4326).
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from postgrest.exceptions import APIError
from shapely.geometry import mapping

from app.auth import CurrentUser
from app.geometry import GeometryError, validate_and_measure
from app.schemas import FieldCreate, FieldResponse
from app.supabase_client import SupabaseNotConfiguredError, create_user_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/fields", tags=["fields"])

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
