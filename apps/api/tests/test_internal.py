"""The refresh-all cron endpoint is reachable only with the shared secret."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.routers import internal


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Any:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class _FakeExec:
    def __init__(self, data: list[Any]) -> None:
        self._data = data

    async def execute(self) -> Any:
        return type("R", (), {"data": self._data})()


class _FakeTable:
    def select(self, *_: Any) -> _FakeExec:
        return _FakeExec([])


class _FakeClient:
    def table(self, *_: Any) -> _FakeTable:
        return _FakeTable()


def test_missing_secret_is_rejected(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CRON_SECRET", "expected-secret")
    get_settings.cache_clear()

    response = client.post("/internal/refresh-all")

    assert response.status_code == 401


def test_wrong_secret_is_rejected(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CRON_SECRET", "expected-secret")
    get_settings.cache_clear()

    response = client.post("/internal/refresh-all", headers={"X-Cron-Secret": "wrong"})

    assert response.status_code == 401


def test_unconfigured_cron_returns_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CRON_SECRET", raising=False)
    get_settings.cache_clear()

    response = client.post("/internal/refresh-all", headers={"X-Cron-Secret": "anything"})

    assert response.status_code == 503


def test_correct_secret_runs_the_job(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CRON_SECRET", "expected-secret")
    get_settings.cache_clear()

    async def fake_client() -> _FakeClient:
        return _FakeClient()

    monkeypatch.setattr(internal, "create_service_client", fake_client)

    response = client.post(
        "/internal/refresh-all", headers={"X-Cron-Secret": "expected-secret"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "fields_total": 0,
        "fields_refreshed": 0,
        "fields_failed": 0,
        "observations_written": 0,
    }
