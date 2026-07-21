"""Database connection API tests"""

import asyncio
import time

import pytest
from httpx import AsyncClient

from app.services.database import ConnectionTestResult


async def create_sqlite_connection(client: AsyncClient, name: str = "Test SQLite DB") -> dict:
    response = await client.post(
        "/api/v1/config/connections",
        json={
            "name": name,
            "driver": "sqlite",
            "database": ":memory:",
        },
    )
    assert response.status_code == 200
    return response.json()["data"]


@pytest.mark.asyncio
async def test_list_connections_empty(client: AsyncClient):
    response = await client.get("/api/v1/config/connections")
    assert response.status_code == 200
    assert response.json()["data"] == []


@pytest.mark.asyncio
async def test_create_connection_sqlite(client: AsyncClient):
    data = await create_sqlite_connection(client)
    assert data["name"] == "Test SQLite DB"
    assert data["driver"] == "sqlite"
    assert "id" in data


@pytest.mark.asyncio
async def test_create_connection_mysql(client: AsyncClient):
    response = await client.post(
        "/api/v1/config/connections",
        json={
            "name": "Test MySQL DB",
            "driver": "mysql",
            "host": "localhost",
            "port": 3306,
            "username": "root",
            "password": "testpass",
            "database": "testdb",
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["name"] == "Test MySQL DB"
    assert data["driver"] == "mysql"


@pytest.mark.asyncio
async def test_update_connection(client: AsyncClient):
    conn = await create_sqlite_connection(client, "Original Name")
    response = await client.put(
        f"/api/v1/config/connections/{conn['id']}",
        json={
            "name": "Updated Name",
            "driver": "sqlite",
            "database": ":memory:",
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["name"] == "Updated Name"


@pytest.mark.asyncio
async def test_delete_connection(client: AsyncClient):
    conn = await create_sqlite_connection(client, "To Delete")
    response = await client.delete(f"/api/v1/config/connections/{conn['id']}")
    assert response.status_code == 200

    connections = (await client.get("/api/v1/config/connections")).json()["data"]
    assert not any(item["id"] == conn["id"] for item in connections)


@pytest.mark.asyncio
async def test_set_default_connection(client: AsyncClient):
    first = await client.post(
        "/api/v1/config/connections",
        json={
            "name": "Connection 1",
            "driver": "sqlite",
            "database": ":memory:",
            "is_default": True,
        },
    )
    second = await client.post(
        "/api/v1/config/connections",
        json={
            "name": "Connection 2",
            "driver": "sqlite",
            "database": ":memory:",
            "is_default": True,
        },
    )
    assert first.status_code == 200
    assert second.status_code == 200

    connections = (await client.get("/api/v1/config/connections")).json()["data"]
    defaults = [connection for connection in connections if connection["is_default"]]
    assert len(defaults) == 1
    assert defaults[0]["name"] == "Connection 2"


@pytest.mark.asyncio
async def test_connection_not_found(client: AsyncClient):
    fake_id = "00000000-0000-0000-0000-000000000000"
    response = await client.put(
        f"/api/v1/config/connections/{fake_id}",
        json={
            "name": "New Name",
            "driver": "sqlite",
            "database": ":memory:",
        },
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_connection_probe_does_not_block_the_async_api_loop(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    connection = await create_sqlite_connection(client)

    class SlowManager:
        @staticmethod
        def test_connection() -> ConnectionTestResult:
            time.sleep(0.15)
            return ConnectionTestResult(connected=True, message="连接成功")

    monkeypatch.setattr(
        "app.api.v1.connections.create_database_manager",
        lambda _config: SlowManager(),
    )
    started_at = asyncio.get_running_loop().time()
    request = asyncio.create_task(
        client.post(f"/api/v1/config/connections/{connection['id']}/test")
    )

    await asyncio.sleep(0.01)
    assert asyncio.get_running_loop().time() - started_at < 0.1

    response = await request
    assert response.status_code == 200
    assert response.json()["data"]["connected"] is True
