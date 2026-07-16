"""Deterministic advice rendered directly from alert evidence.

This is the source of truth and the fallback: if the LLM is unavailable or
produces anything unsafe, this runs instead, so the product always works. It
hedges causes, cites the numbers already in the evidence, and never names a
chemical or a dose.
"""

from __future__ import annotations

from typing import Any, Final

from app.advisory.inputs import AlertFact, rank_alerts
from app.schemas import AdviceItem

MAX_ITEMS: Final = 4


def _num(evidence: dict[str, Any], key: str) -> float | None:
    value = evidence.get(key)
    return float(value) if isinstance(value, (int, float)) else None


def no_action_item() -> AdviceItem:
    return AdviceItem(
        priority=1,
        action="No action needed right now.",
        reason=(
            "No stress was detected in the latest clear satellite passes. Keep an "
            "eye on the field and check again after the next pass."
        ),
        evidence_refs=[],
    )


def _action(alert: AlertFact, crop: str | None) -> str:
    if alert.zone == "field":
        where = "the whole field"
    else:
        where = f"the {alert.zone_name} part of the field"
    lead = f"For your {crop}, walk" if crop else "Walk"
    action = f"{lead} {where} and check the crop and soil by hand."

    if alert.evidence.get("likely_water_stress"):
        rain = _num(alert.evidence, "rain_next_7d_mm")
        rain_text = f"about {rain:g} mm" if rain is not None else "little"
        action += (
            f" The next 7 days look dry ({rain_text} of rain forecast), so check soil "
            "moisture and water if it is dry."
        )
    return action


def _reason(alert: AlertFact) -> str:
    where = "the whole field" if alert.zone == "field" else f"the {alert.zone_name} area"
    decline = _num(alert.evidence, "decline_pct")
    start = _num(alert.evidence, "start_ndvi")
    end = _num(alert.evidence, "end_ndvi")
    window = _num(alert.evidence, "window_days")

    if decline is not None and start is not None and end is not None and window is not None:
        opening = (
            f"NDVI over {where} fell about {decline:g}% (from {start:.2f} to {end:.2f}) "
            f"in {int(window)} days and is now below its usual level."
        )
    else:
        opening = f"NDVI over {where} has dropped below its usual level."

    parts = [
        opening,
        "The satellite can see the decline but not its cause — this is often water or "
        "nutrient stress, so check on foot before acting.",
    ]

    if alert.evidence.get("likely_water_stress"):
        rain = _num(alert.evidence, "rain_next_7d_mm")
        rain_text = f"about {rain:g} mm" if rain is not None else "little"
        parts.append(
            f"With only {rain_text} of rain forecast in the next 7 days, water stress is "
            "more likely."
        )
    return " ".join(parts)


def build_template_advice(alerts: list[AlertFact], crop: str | None = None) -> list[AdviceItem]:
    """A ranked, hedged action list (max 4), or a single no-action item."""
    if not alerts:
        return [no_action_item()]

    ranked = rank_alerts(alerts)[:MAX_ITEMS]
    return [
        AdviceItem(
            priority=index + 1,
            action=_action(alert, crop),
            reason=_reason(alert),
            evidence_refs=[alert.ref],
        )
        for index, alert in enumerate(ranked)
    ]
