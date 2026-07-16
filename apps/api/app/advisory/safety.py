"""Hard-rule validation of LLM advice.

The prompt asks the model to follow the rules; this enforces them regardless. If
any item violates — names a chemical or dose, or cites an alert that was not
supplied — the whole batch is rejected and the caller falls back to the
deterministic template, which is guaranteed clean.
"""

from __future__ import annotations

import re
from typing import Any

from app.advisory.template import MAX_ITEMS
from app.schemas import AdviceItem

# Specific agro-chemical names (pesticides, fungicides, fertilisers, nutrients).
# Naming any of these breaks the advisory-only, no-chemicals posture.
_CHEMICAL_TERMS: frozenset[str] = frozenset(
    {
        "urea", "dap", "npk", "potash", "muriate", "ammonium", "nitrate", "phosphate",
        "nitrogen", "phosphorus", "potassium", "sulphate", "sulfate", "zinc sulphate",
        "glyphosate", "imidacloprid", "chlorpyrifos", "mancozeb", "carbendazim",
        "monocrotophos", "endosulfan", "atrazine", "paraquat", "malathion",
        "cypermethrin", "acephate", "propiconazole", "tebuconazole", "gibberellic",
    }
)

# Dose expressions: a number followed by an agri unit, or per-area phrasing.
_DOSE_PATTERN = re.compile(
    r"\b\d+(\.\d+)?\s*"
    r"(kg|kgs|g|gram|grams|mg|ml|l|litre|litres|liter|liters|ppm|%|oz|lb)\b"
    r"|\bper\s+(acre|hectare|ha|bigha)\b"
    r"|\b(dose|dosage|dilution)\b",
    re.IGNORECASE,
)


def contains_prohibited(text: str) -> bool:
    """True if the text names a chemical or states a dose."""
    lowered = text.lower()
    if any(term in lowered for term in _CHEMICAL_TERMS):
        return True
    return _DOSE_PATTERN.search(lowered) is not None


def _coerce_item(raw: Any, allowed_refs: set[str], fallback_priority: int) -> AdviceItem | None:
    if not isinstance(raw, dict):
        return None
    action = raw.get("action")
    reason = raw.get("reason")
    if not isinstance(action, str) or not isinstance(reason, str):
        return None
    if not action.strip() or not reason.strip():
        return None

    if contains_prohibited(action) or contains_prohibited(reason):
        return None

    refs_raw = raw.get("evidence_refs", [])
    refs = [r for r in refs_raw if isinstance(r, str)] if isinstance(refs_raw, list) else []
    # Every cited ref must be one we supplied — no inventing alerts.
    if any(ref not in allowed_refs for ref in refs):
        return None
    if not refs:
        # An action with no grounding is exactly what we must not surface.
        return None

    priority = raw.get("priority")
    if not isinstance(priority, int) or isinstance(priority, bool):
        priority = fallback_priority

    return AdviceItem(
        priority=priority,
        action=action.strip(),
        reason=reason.strip(),
        evidence_refs=refs,
    )


def validate_llm_items(raw_items: Any, allowed_refs: set[str]) -> list[AdviceItem] | None:
    """Validate LLM output. Returns clean items, or None to force a fallback.

    Strict on purpose: a single prohibited or ungrounded item rejects the whole
    batch, because a safe deterministic answer always exists.
    """
    if not isinstance(raw_items, list) or not raw_items:
        return None

    items: list[AdviceItem] = []
    for index, raw in enumerate(raw_items[:MAX_ITEMS]):
        item = _coerce_item(raw, allowed_refs, fallback_priority=index + 1)
        if item is None:
            return None
        items.append(item)
    return items
