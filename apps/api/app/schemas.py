"""Request and response models for the public API."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FieldCreate(BaseModel):
    # Reject unknown keys outright. user_id is never accepted from a client —
    # it is taken from the verified JWT — and forbidding extras means an
    # attempt to smuggle one fails loudly instead of being silently dropped.
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    # Deliberately typed loosely here. app.geometry is the single source of
    # truth for what a field outline may be, and it rejects with messages a
    # farmer can act on; a stricter annotation would pre-empt it with a 422
    # full of schema jargon.
    geometry: dict[str, Any]

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("Please give the field a name.")
        return name


class FieldResponse(BaseModel):
    id: UUID
    name: str
    area_ha: float
    created_at: datetime
    geometry: dict[str, Any]


class ObservationSummaryResponse(BaseModel):
    date: str
    scene_id: str
    valid_pct: float
    median_ndvi: float
    overlay_url: str
    # (west, south, east, north) in EPSG:4326 — the extent to pin the overlay to.
    bounds_wgs84: tuple[float, float, float, float]


class RefreshResponse(BaseModel):
    scenes_found: int
    dates_processed: int
    valid_dates: int
    active_alerts: int
    observations: list[ObservationSummaryResponse]


class AlertResponse(BaseModel):
    zone: str
    type: str
    severity: str
    evidence: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class WeatherResponse(BaseModel):
    rain_next_7d_mm: float
    rain_past_14d_mm: float


class AdviceRequest(BaseModel):
    # Optional free-text crop name, e.g. "rice" or "sugarcane".
    crop: str | None = Field(default=None, max_length=80)


class AdviceItem(BaseModel):
    priority: int
    action: str
    reason: str
    # References to the alerts this item is grounded in, e.g. "field_decline:field".
    evidence_refs: list[str]


class AdviceResponse(BaseModel):
    # Which path produced the advice — "llm" or the deterministic "template".
    source: Literal["llm", "template"]
    crop: str | None
    items: list[AdviceItem]


class ObservationDetail(BaseModel):
    date: str
    scene_id: str
    valid_pct: float
    stats: dict[str, Any]
    zonal: list[dict[str, Any]]
    overlay_url: str | None
    # (west, south, east, north) in EPSG:4326; null for pre-0004 rows.
    bounds: list[float] | None
