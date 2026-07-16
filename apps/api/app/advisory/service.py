"""Advice orchestration: LLM if available and safe, deterministic template
otherwise."""

from __future__ import annotations

import logging
from typing import Literal

from app.advisory.groq_client import AdvisoryLLMError, request_llm_advice
from app.advisory.inputs import AlertFact
from app.advisory.safety import validate_llm_items
from app.advisory.template import build_template_advice, no_action_item
from app.schemas import AdviceItem
from app.weather.client import WeatherSummary

logger = logging.getLogger(__name__)

Source = Literal["llm", "template"]


async def generate_advice(
    alerts: list[AlertFact],
    weather: WeatherSummary | None,
    crop: str | None,
    api_key: str | None,
) -> tuple[Source, list[AdviceItem]]:
    """Produce advice and report which path produced it.

    A field with no alerts always returns a single no-action item and never
    calls the LLM — there is nothing to phrase and nothing to invent. Otherwise
    the LLM is tried; its output must pass the hard-rule validator, or the
    deterministic template is used.
    """
    if not alerts:
        return "template", [no_action_item()]

    if api_key:
        try:
            raw = await request_llm_advice(alerts, weather, crop, api_key)
            items = validate_llm_items(raw, allowed_refs={a.ref for a in alerts})
            if items:
                return "llm", items
            logger.info("LLM advice rejected by validator; using template")
        except AdvisoryLLMError as exc:
            logger.warning("LLM advice unavailable (%s); using template", exc)

    return "template", build_template_advice(alerts, crop)
