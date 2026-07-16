"""Alert persistence: the observation->point transform and idempotent reconcile.

No live database — a fake Supabase client records the upsert/delete calls so we
can assert the reconciliation without I/O.
"""

import asyncio
from datetime import date, timedelta
from typing import Any

import numpy as np

from app.alerts import store


def _linear(a: float, b: float, n: int) -> list[float]:
    return [float(v) for v in np.linspace(a, b, n)]


class _Query:
    """Records terminal calls and returns canned data for select chains."""

    def __init__(self, table: str, recorder: dict[str, Any], canned: dict[str, Any]) -> None:
        self._table = table
        self._recorder = recorder
        self._canned = canned

    def select(self, *_: Any) -> "_Query":
        return self

    def eq(self, *_: Any) -> "_Query":
        return self

    def order(self, *_: Any, **__: Any) -> "_Query":
        return self

    def limit(self, *_: Any) -> "_Query":
        return self

    def upsert(self, records: Any, **__: Any) -> "_Query":
        self._recorder.setdefault("upserts", []).append(records)
        return self

    def delete(self) -> "_Query":
        self._recorder["delete_called"] = True
        return self

    def in_(self, _col: str, ids: Any) -> "_Query":
        self._recorder["deleted_ids"] = ids
        return self

    async def execute(self) -> Any:
        # Selects return canned data; writes return nothing meaningful.
        data = self._canned.get(self._table, [])
        return type("Result", (), {"data": data})()


class _FakeClient:
    def __init__(self, observations: list[dict], existing_alerts: list[dict]) -> None:
        self.recorder: dict[str, Any] = {}
        self._canned = {"observations": observations, "alerts": existing_alerts}

    def table(self, name: str) -> _Query:
        return _Query(name, self.recorder, self._canned)


def _obs_row(day_index: int, field_median: float, nw: float | None = None) -> dict[str, Any]:
    d = (date(2026, 6, 1) + timedelta(days=5 * day_index)).isoformat()
    zonal = [
        {"row": r, "col": c, "valid_pct": 100, "stats": None}
        for r in range(3)
        for c in range(3)
    ]
    if nw is not None:
        zonal[0] = {"row": 0, "col": 0, "valid_pct": 100, "stats": {"median": nw}}
    return {"date": d, "stats": {"median": field_median}, "zonal": zonal}


class TestToPoint:
    def test_maps_field_and_zone_medians(self) -> None:
        row = _obs_row(0, 0.6, nw=0.5)
        point = store._to_point(row)
        assert point is not None
        assert point.field_median == 0.6
        assert point.zone_medians == {"NW": 0.5}

    def test_skips_rows_without_a_field_median(self) -> None:
        assert store._to_point({"date": "2026-06-01", "stats": {}, "zonal": []}) is None


def test_declining_field_upserts_an_alert() -> None:
    obs = [_obs_row(i, v) for i, v in enumerate(_linear(0.8, 0.45, 6))]
    obs_desc = list(reversed(obs))  # store queries newest-first
    client = _FakeClient(observations=obs_desc, existing_alerts=[])

    alerts = asyncio.run(store.evaluate_and_store_alerts(client, "field-1"))  # type: ignore[arg-type]

    assert len(alerts) == 1
    upserts = client.recorder["upserts"][0]
    assert upserts[0]["type"] == "field_decline"
    assert upserts[0]["field_id"] == "field-1"
    assert "created_at" not in upserts[0]  # preserved across updates


def test_healthy_field_clears_a_stale_alert() -> None:
    obs = [_obs_row(i, 0.7) for i in range(6)]  # flat, healthy
    existing = [{"id": "stale-1", "zone": "field", "type": "field_decline"}]
    client = _FakeClient(observations=list(reversed(obs)), existing_alerts=existing)

    alerts = asyncio.run(store.evaluate_and_store_alerts(client, "field-1"))  # type: ignore[arg-type]

    assert alerts == []
    assert client.recorder.get("deleted_ids") == ["stale-1"]


def test_persisting_the_same_condition_twice_does_not_duplicate() -> None:
    obs = [_obs_row(i, v) for i, v in enumerate(_linear(0.8, 0.45, 6))]
    obs_desc = list(reversed(obs))

    # First run: no existing alerts -> one upsert, insert.
    c1 = _FakeClient(observations=obs_desc, existing_alerts=[])
    asyncio.run(store.evaluate_and_store_alerts(c1, "field-1"))  # type: ignore[arg-type]

    # Second run: the alert already exists -> upsert again (merge), no delete.
    existing = [{"id": "a1", "zone": "field", "type": "field_decline"}]
    c2 = _FakeClient(observations=obs_desc, existing_alerts=existing)
    asyncio.run(store.evaluate_and_store_alerts(c2, "field-1"))  # type: ignore[arg-type]

    assert len(c2.recorder["upserts"][0]) == 1
    assert "deleted_ids" not in c2.recorder  # nothing stale to remove
