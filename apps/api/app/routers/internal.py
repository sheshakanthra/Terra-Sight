"""Internal, unattended endpoints — the daily refresh cron.

Guarded by a shared secret rather than a user session, because it runs on a
schedule with no user. It uses the service-role client to reach every field
across all users, which is exactly why it must never be exposed without the
secret.
"""

import logging
import secrets
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, status
from postgrest.exceptions import APIError
from pydantic import BaseModel
from shapely.errors import ShapelyError
from shapely.geometry import shape

from app.alerts.store import evaluate_and_store_alerts
from app.config import get_settings
from app.imagery.pipeline import refresh_field
from app.imagery.stac import StacError
from app.supabase_client import SupabaseNotConfiguredError, create_service_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])


class RefreshAllResponse(BaseModel):
    fields_total: int
    fields_refreshed: int
    fields_failed: int
    observations_written: int


def _authorize(provided: str | None) -> None:
    """Constant-time check of the cron secret."""
    expected = get_settings().cron_secret
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cron is not configured on this server.",
        )
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authorized.")


@router.post("/refresh-all", response_model=RefreshAllResponse)
async def refresh_all(
    x_cron_secret: Annotated[str | None, Header()] = None,
) -> RefreshAllResponse:
    _authorize(x_cron_secret)

    settings = get_settings()
    try:
        client = await create_service_client()
    except SupabaseNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="This server is not connected to its database yet.",
        ) from exc

    try:
        result = await client.table("fields_geojson").select("id,geometry").execute()
    except APIError as exc:
        logger.error("refresh-all could not list fields: %s", exc.message)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not list fields.",
        ) from exc

    rows = [r for r in result.data if isinstance(r, dict)] if isinstance(result.data, list) else []
    refreshed = 0
    failed = 0
    observations = 0

    for row in rows:
        field_id = str(row.get("id"))
        try:
            polygon = shape(row["geometry"])
            summary = await refresh_field(
                client, settings.supabase_url or "", field_id, polygon
            )
            await evaluate_and_store_alerts(
                client, field_id, (polygon.centroid.y, polygon.centroid.x)
            )
            await _stamp_refreshed(client, field_id)
            observations += summary.valid_dates
            refreshed += 1
        except (StacError, APIError, ShapelyError, KeyError, TypeError, ValueError) as exc:
            logger.warning("refresh-all: field %s failed: %s", field_id, exc)
            failed += 1

    return RefreshAllResponse(
        fields_total=len(rows),
        fields_refreshed=refreshed,
        fields_failed=failed,
        observations_written=observations,
    )


async def _stamp_refreshed(client: Any, field_id: str) -> None:
    from datetime import UTC, datetime

    try:
        await (
            client.table("fields")
            .update({"last_refreshed_at": datetime.now(UTC).isoformat()})
            .eq("id", str(UUID(field_id)))
            .execute()
        )
    except (APIError, ValueError) as exc:
        logger.warning("refresh-all: cooldown stamp failed for %s: %s", field_id, exc)
