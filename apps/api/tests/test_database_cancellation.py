"""Deterministic cancellation tests for blocking DB-API adapters."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

import pytest

from app.services.database import DatabaseConfig, DatabaseManager
from app.services.database_adapters import (
    DatabaseQueryCancelledError,
    MySQLAdapter,
    PostgreSQLAdapter,
)


class _BlockingCursor:
    def __init__(
        self,
        started: threading.Event,
        released: threading.Event,
        *,
        rows: list[dict[str, Any]],
        fail_after_release: bool = True,
    ) -> None:
        self.started = started
        self.released = released
        self.rows = rows
        self.fail_after_release = fail_after_release
        self.calls: list[tuple[str, Any]] = []

    def __enter__(self) -> _BlockingCursor:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def execute(self, sql: str, parameters: Any = None) -> None:
        self.calls.append((sql, parameters))
        if sql.startswith("SET ") or "@@version_comment" in sql:
            return
        self.started.set()
        if not self.released.wait(2):
            raise AssertionError("test query was never released")
        if self.fail_after_release:
            raise RuntimeError("server interrupted the query")

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self.rows)

    def fetchone(self) -> dict[str, Any]:
        return {"version_comment": "MySQL Community Server"}

    def fetchmany(self, count: int) -> list[dict[str, Any]]:
        return list(self.rows[:count])


class _PostgreSQLConnection:
    def __init__(self, cursor: _BlockingCursor, *, cancel_fails: bool = False) -> None:
        self._cursor = cursor
        self.cancel_fails = cancel_fails
        self.cancel_calls = 0
        self.close_calls = 0
        self.readonly_calls: list[bool] = []

    def cursor(self, **_kwargs: Any) -> _BlockingCursor:
        return self._cursor

    def set_session(self, *, readonly: bool) -> None:
        self.readonly_calls.append(readonly)

    def cancel(self) -> None:
        self.cancel_calls += 1
        self._cursor.released.set()
        if self.cancel_fails:
            raise RuntimeError("cancel transport failed")

    def close(self) -> None:
        self.close_calls += 1
        self._cursor.released.set()


class _FakeSocket:
    def __init__(self, released: threading.Event) -> None:
        self.released = released
        self.shutdown_calls: list[int] = []
        self.close_calls = 0

    def shutdown(self, mode: int) -> None:
        self.shutdown_calls.append(mode)
        self.released.set()

    def close(self) -> None:
        self.close_calls += 1
        self.released.set()


class _MySQLConnection:
    def __init__(
        self,
        cursor: _BlockingCursor,
        *,
        thread_id: int = 73,
        fail_repeated_close: bool = False,
    ) -> None:
        self._cursor = cursor
        self._thread_id = thread_id
        self._sock = _FakeSocket(cursor.released)
        self.fail_repeated_close = fail_repeated_close
        self.close_calls = 0
        self.cursor_calls = 0

    def cursor(self, *_args: Any, **_kwargs: Any) -> _BlockingCursor:
        self.cursor_calls += 1
        return self._cursor

    def thread_id(self) -> int:
        return self._thread_id

    def close(self) -> None:
        self.close_calls += 1
        if self.fail_repeated_close and self.close_calls > 1:
            raise RuntimeError("connection was already closed")
        self._cursor.released.set()


class _ControlCursor:
    def __init__(
        self,
        calls: list[str],
        released: threading.Event,
        *,
        fail_execute: bool,
    ) -> None:
        self.calls = calls
        self.released = released
        self.fail_execute = fail_execute

    def __enter__(self) -> _ControlCursor:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def execute(self, sql: str) -> None:
        self.calls.append(sql)
        if self.fail_execute:
            raise RuntimeError("KILL QUERY was rejected")
        self.released.set()


class _ControlConnection:
    def __init__(self, released: threading.Event, *, fail_execute: bool = False) -> None:
        self.calls: list[str] = []
        self.released = released
        self.fail_execute = fail_execute
        self.close_calls = 0

    def cursor(self) -> _ControlCursor:
        return _ControlCursor(
            self.calls,
            self.released,
            fail_execute=self.fail_execute,
        )

    def close(self) -> None:
        self.close_calls += 1


def _run_in_background(operation: Callable[[], Any]) -> tuple[threading.Thread, dict[str, Any]]:
    outcome: dict[str, Any] = {}

    def run() -> None:
        try:
            outcome["result"] = operation()
        except BaseException as exc:
            outcome["error"] = exc

    thread = threading.Thread(target=run, name="database-adapter-test-query")
    thread.start()
    return thread, outcome


def _assert_query_thread_finished(thread: threading.Thread) -> None:
    thread.join(timeout=3)
    assert not thread.is_alive()
    assert not [
        candidate
        for candidate in threading.enumerate()
        if candidate.name.startswith("receiptbi-") and "-query-cancel-" in candidate.name
    ]


@pytest.mark.parametrize(
    ("adapter", "connection"),
    [
        (
            MySQLAdapter(),
            _MySQLConnection(_BlockingCursor(threading.Event(), threading.Event(), rows=[])),
        ),
        (
            PostgreSQLAdapter(),
            _PostgreSQLConnection(_BlockingCursor(threading.Event(), threading.Event(), rows=[])),
        ),
    ],
)
def test_already_cancelled_query_is_rejected_before_cursor_use(adapter: Any, connection: Any):
    cancellation = threading.Event()
    cancellation.set()

    with pytest.raises(DatabaseQueryCancelledError, match="before execution"):
        adapter.execute_sql(connection, "SELECT 1", cancellation_event=cancellation)

    assert getattr(connection, "cursor_calls", 0) == 0
    assert getattr(connection, "cancel_calls", 0) == 0


def test_postgresql_cancellation_interrupts_active_query_and_preserves_statement_timeout():
    started = threading.Event()
    released = threading.Event()
    cancellation = threading.Event()
    cursor = _BlockingCursor(started, released, rows=[])
    connection = _PostgreSQLConnection(cursor)
    adapter = PostgreSQLAdapter()

    thread, outcome = _run_in_background(
        lambda: adapter.execute_sql(
            connection,
            "SELECT pg_sleep(30)",
            cancellation_event=cancellation,
            timeout_seconds=1.5,
        )
    )
    assert started.wait(1)
    cancellation.set()
    _assert_query_thread_finished(thread)

    assert isinstance(outcome.get("error"), DatabaseQueryCancelledError)
    assert connection.cancel_calls == 1
    assert connection.close_calls == 0
    assert connection.readonly_calls == [True]
    assert cursor.calls[:2] == [
        ("SET LOCAL statement_timeout = %s", (1500,)),
        ("SELECT pg_sleep(30)", None),
    ]


def test_completed_postgresql_query_cannot_receive_late_cancellation():
    started = threading.Event()
    released = threading.Event()
    released.set()
    cancellation = threading.Event()
    cursor = _BlockingCursor(
        started,
        released,
        rows=[{"answer": 42}],
        fail_after_release=False,
    )
    connection = _PostgreSQLConnection(cursor)

    result = PostgreSQLAdapter().execute_sql(
        connection,
        "SELECT 42 AS answer",
        cancellation_event=cancellation,
    )
    cancellation.set()

    assert result.data == [{"answer": 42}]
    assert connection.cancel_calls == 0
    assert not [
        candidate
        for candidate in threading.enumerate()
        if candidate.name.startswith("receiptbi-postgresql-query-cancel-")
    ]


def test_mysql_cancellation_uses_short_lived_control_connection(monkeypatch):
    started = threading.Event()
    released = threading.Event()
    cancellation = threading.Event()
    cursor = _BlockingCursor(started, released, rows=[])
    target = _MySQLConnection(cursor, thread_id=73)
    control = _ControlConnection(released)
    adapter = MySQLAdapter()
    config = DatabaseConfig(
        driver="mysql",
        host="database.internal",
        user="analyst",
        password="secret",
        database="sales",
    )
    observed_configs: list[DatabaseConfig] = []

    def create_control(connection_config: DatabaseConfig) -> _ControlConnection:
        observed_configs.append(connection_config)
        return control

    monkeypatch.setattr(adapter, "_create_control_connection", create_control)
    thread, outcome = _run_in_background(
        lambda: adapter.execute_sql(
            target,
            "SELECT SLEEP(30)",
            cancellation_event=cancellation,
            timeout_seconds=2.5,
            connection_config=config,
        )
    )
    assert started.wait(1)
    cancellation.set()
    _assert_query_thread_finished(thread)

    assert isinstance(outcome.get("error"), DatabaseQueryCancelledError)
    assert observed_configs == [config]
    assert control.calls == ["KILL QUERY 73"]
    assert control.close_calls == 1
    assert target._sock.shutdown_calls == []
    assert target.close_calls == 0
    assert cursor.calls[:4] == [
        ("SELECT @@version_comment AS version_comment", None),
        ("SET SESSION TRANSACTION READ ONLY", None),
        ("SET SESSION MAX_EXECUTION_TIME = %s", (2500,)),
        ("SELECT SLEEP(30)", None),
    ]


def test_mysql_control_failure_force_closes_target_socket(monkeypatch):
    started = threading.Event()
    released = threading.Event()
    cancellation = threading.Event()
    cursor = _BlockingCursor(started, released, rows=[])
    target = _MySQLConnection(cursor)
    adapter = MySQLAdapter()
    config = DatabaseConfig(driver="mysql", database="sales")
    control = _ControlConnection(released, fail_execute=True)

    monkeypatch.setattr(adapter, "_create_control_connection", lambda _config: control)
    thread, outcome = _run_in_background(
        lambda: adapter.execute_sql(
            target,
            "SELECT SLEEP(30)",
            cancellation_event=cancellation,
            connection_config=config,
        )
    )
    assert started.wait(1)
    cancellation.set()
    _assert_query_thread_finished(thread)

    assert isinstance(outcome.get("error"), DatabaseQueryCancelledError)
    assert control.calls == ["KILL QUERY 73"]
    assert control.close_calls == 1
    assert target._sock.shutdown_calls
    assert target._sock.close_calls == 1
    assert target.close_calls == 1


def test_manager_preserves_cancel_error_after_mysql_fallback_closed_connection(monkeypatch):
    started = threading.Event()
    released = threading.Event()
    cancellation = threading.Event()
    cursor = _BlockingCursor(started, released, rows=[])
    target = _MySQLConnection(cursor, fail_repeated_close=True)
    config = DatabaseConfig(driver="mysql", database="sales")
    manager = DatabaseManager(config)
    adapter = manager._adapter
    assert isinstance(adapter, MySQLAdapter)

    def fail_control(_connection_config: DatabaseConfig) -> Any:
        raise OSError("control connection unavailable")

    monkeypatch.setattr(adapter, "_create_control_connection", fail_control)
    monkeypatch.setattr(manager, "_create_connection", lambda: target)
    thread, outcome = _run_in_background(
        lambda: manager.execute_query(
            "SELECT SLEEP(30)",
            cancellation_event=cancellation,
        )
    )
    assert started.wait(1)
    cancellation.set()
    _assert_query_thread_finished(thread)

    assert isinstance(outcome.get("error"), DatabaseQueryCancelledError)
    assert target.close_calls == 2


def test_sample_table_uses_the_same_cancellable_adapter_path(monkeypatch):
    started = threading.Event()
    released = threading.Event()
    cancellation = threading.Event()
    cursor = _BlockingCursor(started, released, rows=[])
    target = _MySQLConnection(cursor, thread_id=91)
    config = DatabaseConfig(driver="mysql", database="sales")
    manager = DatabaseManager(config)
    adapter = manager._adapter
    assert isinstance(adapter, MySQLAdapter)
    control = _ControlConnection(released)

    monkeypatch.setattr(adapter, "_create_control_connection", lambda _config: control)
    monkeypatch.setattr(adapter, "validate_relation_columns", lambda *_args: True)
    monkeypatch.setattr(manager, "_create_connection", lambda: target)
    monkeypatch.setattr(manager, "_get_tables", lambda _conn: ["events"])
    monkeypatch.setattr(
        manager,
        "_get_table_columns",
        lambda _conn, _table: [{"name": "id"}],
    )
    thread, outcome = _run_in_background(
        lambda: manager.sample_table(
            "events",
            ["id"],
            cancellation_event=cancellation,
        )
    )
    assert started.wait(1)
    cancellation.set()
    _assert_query_thread_finished(thread)

    assert isinstance(outcome.get("error"), DatabaseQueryCancelledError)
    assert control.calls == ["KILL QUERY 91"]
    assert target.close_calls == 1
    assert [sql for sql, _ in cursor.calls].count("SET SESSION TRANSACTION READ ONLY") == 1


@pytest.mark.parametrize("method_name", ["execute_query", "sample_table"])
def test_manager_rejects_pre_cancelled_work_before_connect(monkeypatch, method_name: str):
    manager = DatabaseManager(DatabaseConfig(driver="sqlite", database=":memory:"))
    cancellation = threading.Event()
    cancellation.set()

    def unexpected_connect() -> Any:
        raise AssertionError("cancelled work must not open a database connection")

    monkeypatch.setattr(manager, "_create_connection", unexpected_connect)
    with pytest.raises(DatabaseQueryCancelledError):
        if method_name == "execute_query":
            manager.execute_query("SELECT 1", cancellation_event=cancellation)
        else:
            manager.sample_table("events", cancellation_event=cancellation)
