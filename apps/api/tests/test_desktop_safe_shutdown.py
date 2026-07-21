"""Focused contract tests for the private desktop shutdown handshake."""

import asyncio
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1 import chat, system
from app.core.config import settings
from app.main import app
from app.services.chat_runtime import ActiveQueryRegistry


@pytest.mark.asyncio
async def test_registry_requests_stop_and_waits_for_query_cleanup() -> None:
    registry = ActiveQueryRegistry()
    query_key = registry.start(uuid4())

    async def release_query() -> None:
        await asyncio.sleep(0.01)
        registry.release(query_key)

    release_task = asyncio.create_task(release_query())
    result = await registry.prepare_shutdown(0.2)
    await release_task

    assert result == {
        "stop_requested": 1,
        "released_before_timeout": True,
        "remaining_active": 0,
    }
    assert registry.shutdown_requested is True

    racing_query_key = registry.start(uuid4())
    assert registry.is_active(racing_query_key) is False
    registry.release(racing_query_key)


@pytest.mark.asyncio
async def test_registry_timeout_never_claims_cleanup_or_resume() -> None:
    registry = ActiveQueryRegistry()
    query_key = registry.start(uuid4())

    result = await registry.prepare_shutdown(0.01)

    assert result == {
        "stop_requested": 1,
        "released_before_timeout": False,
        "remaining_active": 1,
    }
    assert registry.is_active(query_key) is False
    assert "resumable" not in result
    registry.release(query_key)


@pytest.mark.asyncio
async def test_prepare_shutdown_is_unavailable_without_desktop_capability(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "RECEIPTBI_DESKTOP_CONTROL_TOKEN", None)

    response = await client.post("/api/v1/system/prepare-shutdown")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_prepare_shutdown_requires_private_token_and_waits_for_release(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    control_token = "private-desktop-control-token"
    registry = ActiveQueryRegistry()
    query_key = registry.start(uuid4())
    monkeypatch.setattr(settings, "RECEIPTBI_DESKTOP_CONTROL_TOKEN", control_token)
    monkeypatch.setattr(chat, "active_query_registry", registry)
    monkeypatch.setattr(system, "DESKTOP_SHUTDOWN_GRACE_SECONDS", 0.2)

    denied = await client.post(
        "/api/v1/system/prepare-shutdown",
        headers={"X-ReceiptBI-Desktop-Control": "wrong-token"},
    )
    assert denied.status_code == 404
    assert registry.is_active(query_key) is True

    async def release_query() -> None:
        while registry.is_active(query_key):
            await asyncio.sleep(0.005)
        registry.release(query_key)

    release_task = asyncio.create_task(release_query())
    accepted = await client.post(
        "/api/v1/system/prepare-shutdown",
        headers={"X-ReceiptBI-Desktop-Control": control_token},
    )
    await release_task

    assert accepted.status_code == 200
    assert accepted.json()["data"] == {
        "stop_requested": 1,
        "released_before_timeout": True,
        "remaining_active": 0,
    }


@pytest.mark.asyncio
async def test_prepare_shutdown_rejects_non_loopback_even_with_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    control_token = "private-desktop-control-token"
    monkeypatch.setattr(settings, "RECEIPTBI_DESKTOP_CONTROL_TOKEN", control_token)
    transport = ASGITransport(app=app, client=("203.0.113.9", 4711))

    async with AsyncClient(transport=transport, base_url="http://receiptbi.test") as client:
        response = await client.post(
            "/api/v1/system/prepare-shutdown",
            headers={"X-ReceiptBI-Desktop-Control": control_token},
        )

    assert response.status_code == 404
