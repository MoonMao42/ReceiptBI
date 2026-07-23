"""App settings consent API tests."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_processing_permissions_default_on_and_can_be_disabled(
    client: AsyncClient,
):
    initial = await client.get("/api/v1/settings")

    assert initial.status_code == 200
    assert initial.json()["data"]["preprocessing_enabled"] is True
    assert initial.json()["data"]["self_analysis_enabled"] is True

    updated = await client.put(
        "/api/v1/settings",
        json={
            "preprocessing_enabled": False,
            "self_analysis_enabled": False,
        },
    )

    assert updated.status_code == 200
    assert updated.json()["data"]["preprocessing_enabled"] is False
    assert updated.json()["data"]["self_analysis_enabled"] is False
