from __future__ import annotations

from typing import Any

import pytest

from app.services.database import DatabaseConfig, DatabaseManager
from app.services.database_adapters import MySQLAdapter, PostgreSQLAdapter


class _MySQLHardeningCursor:
    def __init__(self, connection: _MySQLHardeningConnection) -> None:
        self.connection = connection
        self.rows: list[dict[str, Any]] = []

    def __enter__(self) -> _MySQLHardeningCursor:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def execute(self, sql: str, parameters: Any = None) -> None:
        self.connection.calls.append((sql, parameters))
        if "@@version_comment" in sql:
            self.rows = [{"version_comment": self.connection.version_comment}]
        elif sql == "SHOW GRANTS":
            self.rows = list(self.connection.grants)
        elif sql.startswith("SELECT VERSION()"):
            self.rows = [{"VERSION()": "3.0.3"}]
        elif "COUNT(*) AS table_count" in sql:
            self.rows = [{"table_count": 2}]
        elif sql.startswith("SET "):
            self.rows = []
        else:
            self.rows = list(self.connection.query_rows)

    def fetchone(self) -> dict[str, Any]:
        return self.rows[0]

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self.rows)

    def fetchmany(self, count: int) -> list[dict[str, Any]]:
        return list(self.rows[:count])


class _MySQLHardeningConnection:
    def __init__(
        self,
        *,
        grants: list[dict[str, Any]],
        version_comment: str = "Doris version doris-3.0.3",
        query_rows: list[dict[str, Any]] | None = None,
    ) -> None:
        self.grants = grants
        self.version_comment = version_comment
        self.query_rows = query_rows or [{"answer": 42}]
        self.calls: list[tuple[str, Any]] = []
        self.cursor_types: list[Any] = []
        self.closed = False

    def cursor(self, cursor_type: Any = None, **_kwargs: Any) -> _MySQLHardeningCursor:
        self.cursor_types.append(cursor_type)
        return _MySQLHardeningCursor(self)

    def thread_id(self) -> int:
        return 17

    def close(self) -> None:
        self.closed = True


def _doris_grants(privileges: str) -> list[dict[str, Any]]:
    return [
        {
            "UserIdentity": "'analyst'@'%'",
            "GlobalPrivs": None,
            "DatabasePrivs": f"internal.sales: {privileges}",
            "TablePrivs": None,
            "ColPrivs": None,
            "ResourcePrivs": "normal: Usage_priv",
        }
    ]


def test_doris_select_only_grants_enable_streaming_query_and_doris_timeout() -> None:
    import pymysql

    connection = _MySQLHardeningConnection(grants=_doris_grants("Select_priv"))

    result = MySQLAdapter().execute_sql(
        connection,
        "SELECT 42 AS answer",
        max_rows=2,
        timeout_seconds=2.2,
    )

    assert result.data == [{"answer": 42}]
    assert result.metadata["streaming"] is True
    assert result.metadata["connection_disposed_after_bounded_read"] is True
    assert connection.closed is True
    assert pymysql.cursors.SSDictCursor in connection.cursor_types
    executed = [sql for sql, _parameters in connection.calls]
    assert "SHOW GRANTS" in executed
    assert "SET query_timeout = 3" in executed
    assert "SET SESSION TRANSACTION READ ONLY" not in executed


@pytest.mark.parametrize(
    "privileges",
    [
        "Select_priv,Load_priv",
        "Select_priv,Alter_priv",
        "Select_priv,Create_priv",
        "Select_priv,Drop_priv",
        "Select_priv,Admin_priv",
        "Select_priv,Node_priv",
        "Select_priv,Grant_priv",
        "READ_WRITE",
        "Usage_priv",
    ],
)
def test_doris_missing_select_or_dangerous_grant_is_rejected(privileges: str) -> None:
    connection = _MySQLHardeningConnection(grants=_doris_grants(privileges))

    with pytest.raises(PermissionError):
        MySQLAdapter().enforce_read_only(connection, timeout_seconds=10)

    assert not any(sql.startswith("SET query_timeout") for sql, _ in connection.calls)


def test_connection_test_fails_when_doris_read_only_boundary_is_not_proven(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _MySQLHardeningConnection(grants=_doris_grants("Select_priv,Load_priv"))
    manager = DatabaseManager(DatabaseConfig(driver="mysql", database="sales"))
    monkeypatch.setattr(manager, "_create_connection", lambda: connection)

    result = manager.test_connection()

    assert result.connected is False
    assert "write or administrative" in result.message
    assert not any(sql.startswith("SELECT VERSION()") for sql, _ in connection.calls)


class _PostgreSQLHardeningCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.itersize = 0
        self.calls: list[tuple[str, Any]] = []

    def __enter__(self) -> _PostgreSQLHardeningCursor:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def execute(self, sql: str, parameters: Any = None) -> None:
        self.calls.append((sql, parameters))

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self.rows)

    def fetchmany(self, count: int) -> list[dict[str, Any]]:
        return list(self.rows[:count])


class _PostgreSQLHardeningConnection:
    def __init__(self) -> None:
        self.control = _PostgreSQLHardeningCursor([])
        self.streaming = _PostgreSQLHardeningCursor([{"answer": 42}])
        self.cursor_calls: list[dict[str, Any]] = []
        self.readonly_calls: list[bool] = []

    def cursor(self, **kwargs: Any) -> _PostgreSQLHardeningCursor:
        self.cursor_calls.append(kwargs)
        return self.streaming if kwargs.get("name") else self.control

    def set_session(self, *, readonly: bool) -> None:
        self.readonly_calls.append(readonly)

    def cancel(self) -> None:
        return None


def test_postgresql_query_uses_named_streaming_cursor() -> None:
    connection = _PostgreSQLHardeningConnection()

    result = PostgreSQLAdapter().execute_sql(
        connection,
        "SELECT 42 AS answer",
        max_rows=5,
    )

    named_call = next(call for call in connection.cursor_calls if call.get("name"))
    assert str(named_call["name"]).startswith("receiptbi_")
    assert result.data == [{"answer": 42}]
    assert result.metadata["streaming"] is True
    assert connection.streaming.itersize == 5
    assert connection.readonly_calls == [True]
