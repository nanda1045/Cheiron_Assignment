"""Smoke tests for operational endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from cheiron.config import Settings
from cheiron.main import app, create_app


async def test_health_endpoint() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "cheiron", "version": "0.1.0"}


async def test_readiness_endpoint() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"


async def test_readiness_reports_missing_key_for_openai_only_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    openai_only_app = create_app(settings=Settings(_env_file=None, planner_provider="openai"))
    async with AsyncClient(
        transport=ASGITransport(app=openai_only_app),
        base_url="http://test",
    ) as client:
        response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["effective_planner"] == "unavailable"
