"""POST /fields — in particular, that user_id can never be set by the caller."""

import math
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth import AuthenticatedUser, get_current_user
from app.main import app
from app.routers import fields as fields_router
from app.schemas import FieldCreate

OWNER_ID = "11111111-1111-1111-1111-111111111111"
ATTACKER_ID = "99999999-9999-9999-9999-999999999999"

_LON, _LAT = 79.13, 10.79
_KM_LAT = 1.0 / 110.6
_KM_LON = 1.0 / (111.32 * math.cos(math.radians(_LAT)))


def square(side_km: float) -> dict[str, Any]:
    dx = _KM_LON * side_km / 2
    dy = _KM_LAT * side_km / 2
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [_LON - dx, _LAT - dy],
                [_LON + dx, _LAT - dy],
                [_LON + dx, _LAT + dy],
                [_LON - dx, _LAT + dy],
                [_LON - dx, _LAT - dy],
            ]
        ],
    }


class _FakeResult:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class _FakeTable:
    def __init__(self, recorder: dict[str, Any]) -> None:
        self._recorder = recorder

    def insert(self, record: dict[str, Any]) -> "_FakeTable":
        self._recorder["record"] = record
        return self

    async def execute(self) -> _FakeResult:
        record = self._recorder["record"]
        return _FakeResult(
            [
                {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "name": record["name"],
                    "area_ha": record["area_ha"],
                    "created_at": "2026-07-16T00:00:00Z",
                }
            ]
        )


class _FakeClient:
    def __init__(self, recorder: dict[str, Any]) -> None:
        self._recorder = recorder

    def table(self, name: str) -> _FakeTable:
        self._recorder["table"] = name
        return _FakeTable(self._recorder)


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Capture what would be written to PostgREST, without a database."""
    captured: dict[str, Any] = {}

    async def fake_create_user_client(access_token: str) -> _FakeClient:
        captured["access_token"] = access_token
        return _FakeClient(captured)

    monkeypatch.setattr(fields_router, "create_user_client", fake_create_user_client)

    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=OWNER_ID, email="owner@example.com", access_token="owner-token"
    )
    yield captured
    app.dependency_overrides.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_user_id_comes_from_the_token_not_the_body(
    client: TestClient, recorder: dict[str, Any]
) -> None:
    response = client.post(
        "/fields",
        json={"name": "North plot", "geometry": square(0.5)},
    )

    assert response.status_code == 201
    assert recorder["record"]["user_id"] == OWNER_ID


def test_a_user_id_smuggled_in_the_body_is_rejected(
    client: TestClient, recorder: dict[str, Any]
) -> None:
    response = client.post(
        "/fields",
        json={"name": "North plot", "geometry": square(0.5), "user_id": ATTACKER_ID},
    )

    assert response.status_code == 422
    assert "record" not in recorder


def test_the_request_is_made_with_the_callers_own_token(
    client: TestClient, recorder: dict[str, Any]
) -> None:
    """RLS is only a real boundary if we act as the user, not as service-role."""
    client.post("/fields", json={"name": "North plot", "geometry": square(0.5)})

    assert recorder["access_token"] == "owner-token"


def test_an_invalid_polygon_is_rejected_before_any_write(
    client: TestClient, recorder: dict[str, Any]
) -> None:
    tiny = square(0.01)

    response = client.post("/fields", json={"name": "Too small", "geometry": tiny})

    assert response.status_code == 400
    assert "too small" in response.json()["detail"]
    assert "record" not in recorder


def test_a_blank_name_is_rejected(client: TestClient, recorder: dict[str, Any]) -> None:
    response = client.post("/fields", json={"name": "   ", "geometry": square(0.5)})

    assert response.status_code == 422
    assert "record" not in recorder


def test_the_name_is_stored_trimmed(client: TestClient, recorder: dict[str, Any]) -> None:
    client.post("/fields", json={"name": "  North plot  ", "geometry": square(0.5)})

    assert recorder["record"]["name"] == "North plot"


def test_geometry_is_stored_as_srid_qualified_ewkt(
    client: TestClient, recorder: dict[str, Any]
) -> None:
    client.post("/fields", json={"name": "North plot", "geometry": square(0.5)})

    assert recorder["record"]["geom"].startswith("SRID=4326;POLYGON")


def test_area_is_computed_server_side_and_not_taken_from_the_client(
    client: TestClient, recorder: dict[str, Any]
) -> None:
    """A 500 m square is ~25 ha however the client might describe it."""
    client.post("/fields", json={"name": "North plot", "geometry": square(0.5)})

    assert recorder["record"]["area_ha"] == pytest.approx(25.0, rel=0.02)


class TestSchema:
    def test_extra_keys_are_forbidden(self) -> None:
        with pytest.raises(ValueError):
            FieldCreate(name="x", geometry=square(0.5), user_id=ATTACKER_ID)  # type: ignore[call-arg]

    def test_the_model_has_no_user_id_field_at_all(self) -> None:
        assert "user_id" not in FieldCreate.model_fields
