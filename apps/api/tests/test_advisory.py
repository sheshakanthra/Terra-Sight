"""Advisory: template rendering, the hard-rule validator, and LLM-vs-fallback."""

import asyncio

import pytest

from app.advisory import service
from app.advisory.groq_client import AdvisoryLLMError
from app.advisory.inputs import AlertFact
from app.advisory.safety import contains_prohibited, validate_llm_items
from app.advisory.template import build_template_advice, no_action_item


def field_alert(**evidence: object) -> AlertFact:
    base = {
        "decline_pct": 29.4,
        "start_ndvi": 0.8244,
        "end_ndvi": 0.5816,
        "window_days": 38,
    }
    base.update(evidence)
    return AlertFact(type="field_decline", zone="field", severity="medium", evidence=base)


def zone_alert(zone: str, severity: str = "high") -> AlertFact:
    return AlertFact(
        type="zone_decline",
        zone=zone,
        severity=severity,
        evidence={"decline_pct": 50.0, "start_ndvi": 0.75, "end_ndvi": 0.37, "window_days": 18},
    )


class TestTemplate:
    def test_no_alerts_returns_a_single_no_action_item(self) -> None:
        items = build_template_advice([])
        assert len(items) == 1
        assert "no action needed" in items[0].action.lower()
        assert items[0].evidence_refs == []

    def test_cites_the_real_evidence_numbers(self) -> None:
        items = build_template_advice([field_alert()])
        reason = items[0].reason
        assert "29.4%" in reason
        assert "0.82" in reason and "0.58" in reason
        assert "38 days" in reason

    def test_hedges_the_cause(self) -> None:
        reason = build_template_advice([field_alert()])[0].reason.lower()
        assert "check on foot" in reason
        assert "often" in reason or "likely" in reason

    def test_names_no_chemical_or_dose(self) -> None:
        items = build_template_advice([field_alert(likely_water_stress=True, rain_next_7d_mm=3.5)])
        for item in items:
            assert not contains_prohibited(item.action)
            assert not contains_prohibited(item.reason)

    def test_water_stress_mentions_the_dry_forecast(self) -> None:
        alerts = [field_alert(likely_water_stress=True, rain_next_7d_mm=3.5)]
        item = build_template_advice(alerts)[0]
        assert "3.5 mm" in item.reason or "3.5 mm" in item.action
        assert "dry" in item.action.lower()

    def test_caps_at_four_items_ranked_by_severity(self) -> None:
        alerts = [
            zone_alert("NW", "low"),
            zone_alert("N", "high"),
            zone_alert("NE", "high"),
            zone_alert("E", "medium"),
            zone_alert("SE", "high"),
            field_alert(),
        ]
        items = build_template_advice(alerts)
        assert len(items) == 4
        assert [i.priority for i in items] == [1, 2, 3, 4]

    def test_each_item_references_its_alert(self) -> None:
        items = build_template_advice([field_alert()])
        assert items[0].evidence_refs == ["field_decline:field"]


class TestProhibitedDetection:
    @pytest.mark.parametrize(
        "text",
        [
            "Apply urea to the field",
            "Spray 20 ml per litre of water",
            "Use 5 kg per acre",
            "Apply nitrogen fertiliser",
            "Increase the dose of the treatment",
            "Use glyphosate on the weeds",
        ],
    )
    def test_flags_chemicals_and_doses(self, text: str) -> None:
        assert contains_prohibited(text)

    @pytest.mark.parametrize(
        "text",
        [
            "Walk the north-west part of the field and check soil moisture.",
            "NDVI fell about 29% over 38 days; check on foot.",
            "The forecast is dry, so water if the soil is dry.",
        ],
    )
    def test_allows_safe_advice(self, text: str) -> None:
        assert not contains_prohibited(text)


class TestValidator:
    def _raw(self, **over: object) -> dict:
        item = {
            "priority": 1,
            "action": "Walk the whole field and check the soil.",
            "reason": "NDVI fell about 29%. Check on foot.",
            "evidence_refs": ["field_decline:field"],
        }
        item.update(over)
        return item

    def test_accepts_clean_grounded_items(self) -> None:
        items = validate_llm_items([self._raw()], allowed_refs={"field_decline:field"})
        assert items is not None
        assert len(items) == 1

    def test_rejects_batch_that_cites_an_unsupplied_alert(self) -> None:
        raw = self._raw(evidence_refs=["zone_decline:NW"])
        assert validate_llm_items([raw], allowed_refs={"field_decline:field"}) is None

    def test_rejects_batch_with_a_chemical(self) -> None:
        raw = self._raw(action="Apply urea across the field.")
        assert validate_llm_items([raw], allowed_refs={"field_decline:field"}) is None

    def test_rejects_ungrounded_item(self) -> None:
        raw = self._raw(evidence_refs=[])
        assert validate_llm_items([raw], allowed_refs={"field_decline:field"}) is None

    def test_truncates_to_four_items(self) -> None:
        raws = [self._raw() for _ in range(6)]
        items = validate_llm_items(raws, allowed_refs={"field_decline:field"})
        assert items is not None
        assert len(items) == 4

    def test_empty_or_malformed_returns_none(self) -> None:
        assert validate_llm_items([], allowed_refs=set()) is None
        assert validate_llm_items("not a list", allowed_refs=set()) is None


class TestService:
    def test_no_alerts_never_calls_the_llm(self) -> None:
        source, items = asyncio.run(service.generate_advice([], None, None, api_key="key"))
        assert source == "template"
        assert items == [no_action_item()]

    def test_falls_back_to_template_when_llm_errors(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom(*_: object, **__: object) -> list:
            raise AdvisoryLLMError("groq down")

        monkeypatch.setattr(service, "request_llm_advice", boom)
        source, items = asyncio.run(
            service.generate_advice([field_alert()], None, None, api_key="key")
        )
        assert source == "template"
        assert "29.4%" in items[0].reason

    def test_falls_back_when_llm_output_is_unsafe(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def unsafe(*_: object, **__: object) -> list:
            return [
                {"action": "Apply urea", "reason": "x", "evidence_refs": ["field_decline:field"]}
            ]

        monkeypatch.setattr(service, "request_llm_advice", unsafe)
        source, _ = asyncio.run(
            service.generate_advice([field_alert()], None, None, api_key="key")
        )
        assert source == "template"

    def test_uses_llm_when_output_is_clean(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def good(*_: object, **__: object) -> list:
            return [
                {
                    "priority": 1,
                    "action": "Walk the field and check the soil by hand.",
                    "reason": "NDVI fell about 29% over 38 days; check on foot.",
                    "evidence_refs": ["field_decline:field"],
                }
            ]

        monkeypatch.setattr(service, "request_llm_advice", good)
        source, items = asyncio.run(
            service.generate_advice([field_alert()], None, None, api_key="key")
        )
        assert source == "llm"
        assert len(items) == 1

    def test_no_api_key_uses_template(self) -> None:
        source, _ = asyncio.run(
            service.generate_advice([field_alert()], None, None, api_key=None)
        )
        assert source == "template"
