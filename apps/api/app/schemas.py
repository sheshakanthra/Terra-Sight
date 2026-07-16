"""Request and response models for the public API."""

from datetime import datetime
from typing import Any
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
