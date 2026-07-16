"""Persist trend alerts idempotently.

Each refresh recomputes the field's active alerts and reconciles the table to
match: existing conditions are updated in place (unique on field_id+zone+type),
and alerts whose condition no longer holds are cleared. A refresh therefore
never duplicates an alert and never leaves a stale one behind.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any

from supabase import AsyncClient

from app.alerts.engine import WINDOW_MAX, Alert, ObservationPoint, detect_alerts, zone_label

logger = logging.getLogger(__name__)


def _rows(data: object) -> list[dict[str, Any]]:
    if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
        return []
    return data


def _to_point(row: dict[str, Any]) -> ObservationPoint | None:
    stats = row.get("stats") or {}
    field_median = stats.get("median")
    if field_median is None:
        return None

    zone_medians: dict[str, float] = {}
    for zone in row.get("zonal") or []:
        zone_stats = zone.get("stats")
        if zone_stats and zone_stats.get("median") is not None:
            zone_medians[zone_label(zone["row"], zone["col"])] = float(zone_stats["median"])

    return ObservationPoint(
        date=date.fromisoformat(str(row["date"])),
        field_median=float(field_median),
        zone_medians=zone_medians,
    )


async def _load_points(client: AsyncClient, field_id: str) -> list[ObservationPoint]:
    result = (
        await client.table("observations")
        .select("date,stats,zonal")
        .eq("field_id", field_id)
        .order("date", desc=True)
        .limit(WINDOW_MAX)
        .execute()
    )
    points = [point for row in _rows(result.data) if (point := _to_point(row)) is not None]
    return points


async def _reconcile(client: AsyncClient, field_id: str, alerts: list[Alert]) -> None:
    existing = (
        await client.table("alerts").select("id,zone,type").eq("field_id", field_id).execute()
    )
    active_keys = {(alert.zone, alert.type) for alert in alerts}
    stale_ids = [
        row["id"] for row in _rows(existing.data) if (row["zone"], row["type"]) not in active_keys
    ]

    if alerts:
        now = datetime.now(UTC).isoformat()
        records: list[dict[str, Any]] = [
            {
                "field_id": field_id,
                "zone": alert.zone,
                "type": alert.type,
                "severity": alert.severity,
                "evidence": alert.evidence,
                "updated_at": now,
            }
            for alert in alerts
        ]
        # created_at is intentionally omitted so it survives updates (first-seen).
        await client.table("alerts").upsert(records, on_conflict="field_id,zone,type").execute()

    if stale_ids:
        await client.table("alerts").delete().in_("id", stale_ids).execute()


async def evaluate_and_store_alerts(client: AsyncClient, field_id: str) -> list[Alert]:
    """Recompute the field's alerts from its recent observations and persist them."""
    points = await _load_points(client, field_id)
    alerts = detect_alerts(points)
    await _reconcile(client, field_id, alerts)
    return alerts
