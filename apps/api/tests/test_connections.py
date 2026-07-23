"""Database connection API tests"""

import asyncio
import time

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.tables import Connection, Project, ProjectDataSource
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
async def test_connection_namespace_change_requires_linked_sources_to_be_prepared_again(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="连接范围保护")
    connection = Connection(
        name="经营库",
        driver="postgresql",
        host="warehouse.internal",
        port=5432,
        username="analyst",
        database_name="commerce",
        extra_options={"schema": "public"},
    )
    db_session.add_all([project, connection])
    await db_session.flush()
    source = ProjectDataSource(
        project_id=project.id,
        connection_id=connection.id,
        kind="connection",
        name="经营库",
        format="postgresql",
        status="ready",
        profile_data={
            "logical_name": "经营库",
            "is_current": True,
            "tables": [
                {
                    "name": "orders",
                    "schema": "public",
                    "columns": [{"name": "amount", "type": "numeric"}],
                }
            ],
        },
    )
    db_session.add(source)
    await db_session.commit()

    response = await client.put(
        f"/api/v1/config/connections/{connection.id}",
        json={
            "name": "经营库",
            "driver": "postgresql",
            "host": "warehouse.internal",
            "port": 5432,
            "username": "analyst",
            "database": "commerce",
            "extra_options": {"schema": "archive"},
        },
    )

    assert response.status_code == 200
    await db_session.refresh(source)
    assert source.status == "attached"
    assert source.profile_data["is_current"] is False
    assert source.profile_data["activation_state"] == "pending_confirmation"
    assert any(
        item.get("code") == "database_connection_scope_changed"
        for item in source.profile_data["issues"]
    )


@pytest.mark.asyncio
async def test_connection_display_name_change_keeps_linked_source_current(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="连接名称修改")
    connection = Connection(
        name="旧名称",
        driver="sqlite",
        database_name="warehouse.db",
    )
    db_session.add_all([project, connection])
    await db_session.flush()
    source = ProjectDataSource(
        project_id=project.id,
        connection_id=connection.id,
        kind="connection",
        name="经营库",
        format="sqlite",
        status="ready",
        profile_data={"logical_name": "经营库", "is_current": True},
    )
    db_session.add(source)
    await db_session.commit()

    response = await client.put(
        f"/api/v1/config/connections/{connection.id}",
        json={
            "name": "新名称",
            "driver": "sqlite",
            "database": "warehouse.db",
        },
    )

    assert response.status_code == 200
    await db_session.refresh(source)
    assert source.status == "ready"
    assert source.profile_data["is_current"] is True


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
