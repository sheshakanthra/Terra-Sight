"""Groq-phrased advice. The model rewrites structured alerts into plain language;
it never originates an alert and its output is validated before use."""

from __future__ import annotations

import json
import logging
from typing import Any, Final

from groq import AsyncGroq

from app.advisory.inputs import AlertFact
from app.weather.client import WeatherSummary

logger = logging.getLogger(__name__)

MODEL: Final = "llama-3.3-70b-versatile"
_TIMEOUT_S: Final = 20.0
_MAX_TOKENS: Final = 800

_SYSTEM_PROMPT: Final = """You are an assistant for smallholder farmers. You turn \
satellite-derived crop alerts into a short, plain-language action list.

Follow these rules exactly:
1. Use ONLY the alerts provided. Never mention a field zone or problem that is not \
in the input. Do not invent measurements.
2. Every item must cite the alert(s) it is based on in "evidence_refs", using the \
exact "ref" strings given. Only use refs that appear in the input.
3. Cite the real numbers from the evidence (NDVI values, percent decline, days, \
rain in mm) in your reasons.
4. Hedge the cause. The satellite shows that health dropped, not why. Say things \
like "likely" and "check on foot". Never state a diagnosis as fact.
5. NEVER name any chemical, fertiliser, pesticide, or nutrient, and NEVER give a \
dose, quantity, or dilution. Advise inspection and general practices only.
6. Plain language a farmer can act on. At most 4 items, most important first.

Return JSON only: {"items": [{"priority": int, "action": str, "reason": str, \
"evidence_refs": [str]}]}."""


class AdvisoryLLMError(RuntimeError):
    """The LLM advice call failed or returned unusable output."""


def _build_user_prompt(
    alerts: list[AlertFact], weather: WeatherSummary | None, crop: str | None
) -> str:
    payload: dict[str, Any] = {
        "crop": crop or "unknown",
        "weather": (
            {
                "rain_next_7d_mm": weather.rain_next_7d_mm,
                "rain_past_14d_mm": weather.rain_past_14d_mm,
            }
            if weather is not None
            else None
        ),
        "alerts": [
            {
                "ref": alert.ref,
                "type": alert.type,
                "zone": alert.zone,
                "zone_name": alert.zone_name,
                "severity": alert.severity,
                "evidence": alert.evidence,
            }
            for alert in alerts
        ],
    }
    return (
        "Write the action list for these alerts. Use the exact ref strings in "
        "evidence_refs.\n\n" + json.dumps(payload, ensure_ascii=False)
    )


async def request_llm_advice(
    alerts: list[AlertFact],
    weather: WeatherSummary | None,
    crop: str | None,
    api_key: str,
) -> list[Any]:
    """Call Groq and return the raw 'items' list. Raises AdvisoryLLMError on any
    failure — the caller falls back to the template."""
    client = AsyncGroq(api_key=api_key, timeout=_TIMEOUT_S, max_retries=1)
    try:
        response = await client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(alerts, weather, crop)},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=_MAX_TOKENS,
        )
    except Exception as exc:  # any LLM failure must fall back cleanly
        raise AdvisoryLLMError(str(exc)) from exc
    finally:
        await client.close()

    content = response.choices[0].message.content if response.choices else None
    if not content:
        raise AdvisoryLLMError("Empty LLM response.")

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise AdvisoryLLMError("LLM did not return valid JSON.") from exc

    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise AdvisoryLLMError("LLM JSON had no 'items' list.")
    return items
