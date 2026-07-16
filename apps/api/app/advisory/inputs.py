"""Normalized advisory inputs shared by the template and LLM paths."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

# Human-readable names for the 3x3 zone labels and the whole field.
ZONE_NAMES: Final[dict[str, str]] = {
    "field": "whole field",
    "NW": "north-west",
    "N": "north",
    "NE": "north-east",
    "W": "west",
    "C": "centre",
    "E": "east",
    "SW": "south-west",
    "S": "south",
    "SE": "south-east",
}

_SEVERITY_ORDER: Final[dict[str, int]] = {"high": 0, "medium": 1, "low": 2}
# Field-wide declines lead zone declines at equal severity.
_TYPE_ORDER: Final[dict[str, int]] = {"field_decline": 0, "zone_decline": 1}


@dataclass(frozen=True)
class AlertFact:
    type: str
    zone: str
    severity: str
    evidence: dict[str, Any]

    @property
    def ref(self) -> str:
        """Stable identifier an advice item cites, e.g. 'zone_decline:NW'."""
        return f"{self.type}:{self.zone}"

    @property
    def zone_name(self) -> str:
        return ZONE_NAMES.get(self.zone, self.zone)


def rank_alerts(alerts: list[AlertFact]) -> list[AlertFact]:
    """Most urgent first: by severity, then field-wide before single zones."""
    return sorted(
        alerts,
        key=lambda a: (
            _SEVERITY_ORDER.get(a.severity, 99),
            _TYPE_ORDER.get(a.type, 99),
            a.zone,
        ),
    )
