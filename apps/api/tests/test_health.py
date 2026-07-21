"""Health check endpoint tests"""

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.main import app


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """Test health check endpoint returns OK"""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "instance_token" in data
    assert data["legacy_model_migration"] is None


@pytest.mark.asyncio
async def test_health_migration_ack_is_bound_to_the_desktop_instance(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "RECEIPTBI_INSTANCE_TOKEN", "launch-token")
    app.state.legacy_model_migration = "already_present"
    try:
        response = await client.get("/health")
    finally:
        app.state.legacy_model_migration = "not_requested"

    assert response.status_code == 200
    assert response.json()["legacy_model_migration"] == {
        "status": "already_present",
        "instance_token": "launch-token",
    }


@pytest.mark.asyncio
async def test_root_endpoint(client: AsyncClient):
    """Test root endpoint returns app info"""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert "version" in data
