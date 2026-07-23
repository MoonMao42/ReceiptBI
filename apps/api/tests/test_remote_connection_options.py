from __future__ import annotations

from typing import Any

import psycopg2
import pymysql
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.tables import Connection, Project, ProjectDataSource
from app.services.database import DatabaseConfig
from app.services.database_adapters import MySQLAdapter, PostgreSQLAdapter
from app.services.execution_context import ExecutionContextResolver
from app.services.project_context import load_project_context


def _postgres_payload(**extra_options: Any) -> dict[str, Any]:
    return {
        "name": "Analytics warehouse",
        "driver": "postgresql",
        "host": "warehouse.internal",
        "port": 5432,
        "username": "readonly",
        "password": "secret",
        "database": "analytics",
        "extra_options": extra_options,
    }


@pytest.mark.asyncio
async def test_remote_options_round_trip_and_reach_connection_test(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    options = {
        "sslmode": "verify-full",
        "sslrootcert": "/certs/root.pem",
        "sslcert": "/certs/client.pem",
        "sslkey": "/certs/client.key",
        "schema": "finance",
    }
    response = await client.post(
        "/api/v1/config/connections",
        json=_postgres_payload(**options),
    )

    assert response.status_code == 200
    saved = response.json()["data"]
    assert saved["extra_options"] == options
    assert "password" not in saved

    captured: dict[str, Any] = {}

    class Manager:
        @staticmethod
        def test_connection() -> Any:
            from app.services.database import ConnectionTestResult

            return ConnectionTestResult(connected=True, message="连接成功")

    def create_manager(config: DatabaseConfig) -> Manager:
        captured["config"] = config
        return Manager()

    monkeypatch.setattr(
        "app.api.v1.connections.create_database_manager",
        create_manager,
    )
    test_response = await client.post(f"/api/v1/config/connections/{saved['id']}/test")

    assert test_response.status_code == 200
    assert test_response.json()["data"]["connected"] is True
    assert captured["config"].extra_options == options


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "options",
    [
        {"arbitrary_driver_argument": "unsafe"},
        {"schema": "finance; SET ROLE admin"},
        {"sslmode": "verify-full"},
        {"sslmode": "require", "sslcert": "/certs/client.pem"},
        {"sslmode": "verify-ca", "sslrootcert": "-----BEGIN CERTIFICATE-----"},
        {"sslmode": "verify-ca", "sslrootcert": "/certs/root.pem\ncertificate body"},
    ],
)
async def test_remote_options_reject_unknown_or_incomplete_values(
    client: AsyncClient,
    options: dict[str, Any],
) -> None:
    response = await client.post(
        "/api/v1/config/connections",
        json=_postgres_payload(**options),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_sqlite_rejects_remote_tls_options(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/config/connections",
        json={
            "name": "Local",
            "driver": "sqlite",
            "database": ":memory:",
            "extra_options": {"sslmode": "require"},
        },
    )

    assert response.status_code == 422


class _PostgreSQLCursor:
    def __init__(self, connection: _PostgreSQLConnection) -> None:
        self.connection = connection
        self.rows: list[Any] = []

    def __enter__(self) -> _PostgreSQLCursor:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def execute(self, sql: str, params: Any = None) -> None:
        self.connection.executed.append((sql, params))
        if "pg_catalog.pg_namespace" in sql:
            self.rows = [(params[0],)]
        elif "information_schema.tables" in sql:
            self.rows = [("orders",)]
        else:
            self.rows = []

    def fetchone(self) -> Any:
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[Any]:
        return self.rows


class _PostgreSQLConnection:
    def __init__(self) -> None:
        self.autocommit = False
        self.closed = 0
        self.executed: list[tuple[str, Any]] = []

    def cursor(self) -> _PostgreSQLCursor:
        return _PostgreSQLCursor(self)

    def close(self) -> None:
        self.closed = 1


def test_postgresql_adapter_applies_tls_search_path_and_catalog_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _PostgreSQLConnection()
    captured: dict[str, Any] = {}

    def connect(**kwargs: Any) -> _PostgreSQLConnection:
        captured.update(kwargs)
        return connection

    monkeypatch.setattr(psycopg2, "connect", connect)
    adapter = PostgreSQLAdapter()
    config = DatabaseConfig(
        driver="postgresql",
        host="warehouse.internal",
        database="analytics",
        extra_options={
            "sslmode": "verify-full",
            "sslrootcert": "/certs/root.pem",
            "sslcert": "/certs/client.pem",
            "sslkey": "/certs/client.key",
            "schema": "finance",
        },
    )

    assert adapter.create_connection(config) is connection
    assert captured["sslmode"] == "verify-full"
    assert captured["sslrootcert"] == "/certs/root.pem"
    assert captured["sslcert"] == "/certs/client.pem"
    assert captured["sslkey"] == "/certs/client.key"
    assert connection.autocommit is False
    assert any("set_config('search_path'" in sql for sql, _params in connection.executed)

    assert adapter.get_tables(connection) == ["orders"]
    catalog_call = connection.executed[-1]
    assert "table_schema = %s" in catalog_call[0]
    assert catalog_call[1] == ("finance",)


def test_postgresql_adapter_pins_default_search_path_to_public(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _PostgreSQLConnection()
    monkeypatch.setattr(psycopg2, "connect", lambda **_kwargs: connection)
    adapter = PostgreSQLAdapter()

    adapter.create_connection(DatabaseConfig(driver="postgresql"))

    search_path_call = next(
        (sql, params) for sql, params in connection.executed if "set_config('search_path'" in sql
    )
    assert search_path_call[1] == ("public",)
    assert adapter.get_tables(connection) == ["orders"]
    assert connection.executed[-1][1] == ("public",)


def test_mysql_adapter_translates_verified_tls_for_query_and_cancel_connections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    def connect(**kwargs: Any) -> object:
        calls.append(kwargs)
        return object()

    monkeypatch.setattr(pymysql, "connect", connect)
    config = DatabaseConfig(
        driver="mysql",
        extra_options={
            "sslmode": "verify-full",
            "sslrootcert": "/certs/root.pem",
            "sslcert": "/certs/client.pem",
            "sslkey": "/certs/client.key",
        },
    )
    adapter = MySQLAdapter()

    adapter.create_connection(config)
    adapter._create_control_connection(config)

    assert len(calls) == 2
    for kwargs in calls:
        assert kwargs["ssl_ca"] == "/certs/root.pem"
        assert kwargs["ssl_cert"] == "/certs/client.pem"
        assert kwargs["ssl_key"] == "/certs/client.key"
        assert kwargs["ssl_verify_cert"] is True
        assert kwargs["ssl_verify_identity"] is True


def test_database_config_rejects_schema_injection() -> None:
    with pytest.raises(ValueError, match="schema"):
        DatabaseConfig(
            driver="postgresql",
            extra_options={"schema": 'finance"; DROP SCHEMA public'},
        )


@pytest.mark.parametrize(
    "value",
    [
        "-----BEGIN TEST KEY-----",
        "/certs/client.key\n-----BEGIN TEST KEY-----",
    ],
)
def test_database_config_rejects_certificate_or_key_bodies(value: str) -> None:
    with pytest.raises(ValueError, match="路径"):
        DatabaseConfig(
            driver="postgresql",
            extra_options={
                "sslmode": "require",
                "sslcert": value,
                "sslkey": value,
            },
        )


@pytest.mark.asyncio
async def test_execution_and_project_contexts_preserve_remote_options(
    db_session: AsyncSession,
) -> None:
    options = {
        "sslmode": "require",
        "schema": "finance",
    }
    project = Project(name="Remote warehouse")
    connection = Connection(
        name="Finance warehouse",
        driver="postgresql",
        host="warehouse.internal",
        port=5432,
        username="readonly",
        database_name="analytics",
        extra_options=options,
    )
    db_session.add_all([project, connection])
    await db_session.flush()
    source = ProjectDataSource(
        project_id=project.id,
        connection_id=connection.id,
        kind="connection",
        name="Finance warehouse",
        format="postgresql",
        status="ready",
        profile_data={"is_current": True, "tables": []},
    )
    db_session.add(source)
    await db_session.commit()

    resolver = ExecutionContextResolver(
        db_session,
        connection_id=connection.id,
    )
    execution_config = await resolver.get_connection_config()
    assert execution_config is not None
    assert execution_config["extra_options"] == options

    project_context = await load_project_context(db_session, project.id)
    assert project_context.connection_configs[str(source.id)]["extra_options"] == options
