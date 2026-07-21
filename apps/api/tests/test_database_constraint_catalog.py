from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from app.services.database import DatabaseConfig, DatabaseManager
from app.services.database_adapters import MySQLAdapter, PostgreSQLAdapter
from app.services.database_value_preflight import run_database_value_preflight
from app.services.sqlite_trusted_executor import SIDECAR_ENV


class _ScriptedCursor:
    def __init__(self, connection: _ScriptedConnection):
        self.connection = connection
        self.rows: list[Any] = []

    def __enter__(self) -> _ScriptedCursor:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def execute(self, sql: str, _params: Any = None) -> None:
        self.connection.executed.append(sql)
        response = self.connection.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        self.rows = response

    def fetchall(self) -> list[Any]:
        return self.rows


class _ScriptedConnection:
    def __init__(self, *responses: list[Any] | Exception):
        self.responses = list(responses)
        self.executed: list[str] = []

    def cursor(self) -> _ScriptedCursor:
        return _ScriptedCursor(self)


def test_sqlite_catalog_reports_real_keys_foreign_keys_and_relation_kind(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(SIDECAR_ENV, raising=False)
    database_path = tmp_path / "constraints.db"
    with sqlite3.connect(database_path) as conn:
        conn.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE stores (
                store_id TEXT PRIMARY KEY,
                external_code TEXT UNIQUE,
                name TEXT
            );
            CREATE TABLE orders (
                order_id INTEGER NOT NULL,
                line_no INTEGER NOT NULL,
                store_id TEXT NOT NULL,
                amount REAL,
                PRIMARY KEY (order_id, line_no),
                UNIQUE (store_id, order_id),
                FOREIGN KEY (store_id) REFERENCES stores(store_id)
                    ON UPDATE CASCADE ON DELETE RESTRICT
            );
            CREATE VIEW order_totals AS
                SELECT store_id, SUM(amount) AS amount FROM orders GROUP BY store_id;
            """
        )

    manager = DatabaseManager(DatabaseConfig(driver="sqlite", database=str(database_path)))
    catalog = {entry["name"]: entry for entry in manager.get_schema_catalog()}

    assert catalog["stores"]["kind"] == "table"
    assert catalog["order_totals"]["kind"] == "view"
    assert catalog["orders"]["constraint_metadata_status"] == "available"
    assert catalog["orders"]["primary_key"] == {
        "name": None,
        "columns": ["order_id", "line_no"],
    }
    assert any(
        item["columns"] == ["store_id", "order_id"]
        for item in catalog["orders"]["unique_constraints"]
    )
    assert catalog["orders"]["foreign_keys"] == [
        {
            "name": None,
            "catalog_id": 0,
            "columns": ["store_id"],
            "referenced_schema": "main",
            "referenced_table": "stores",
            "referenced_columns": ["store_id"],
            "on_update": "CASCADE",
            "on_delete": "RESTRICT",
            "match": "NONE",
        }
    ]
    store_columns = {item["name"]: item for item in catalog["stores"]["columns"]}
    assert store_columns["store_id"] == {
        "name": "store_id",
        "type": "TEXT",
        "nullable": True,
        "primary_key": True,
        "unique": True,
    }
    assert store_columns["external_code"]["unique"] is True
    order_columns = {item["name"]: item for item in catalog["orders"]["columns"]}
    assert order_columns["order_id"]["primary_key"] is True
    assert order_columns["order_id"]["unique"] is False


def test_mysql_catalog_groups_constraint_columns_and_preserves_declared_actions() -> None:
    connection = _ScriptedConnection(
        [
            {"TABLE_SCHEMA": "shop", "TABLE_NAME": "orders", "TABLE_TYPE": "BASE TABLE"},
            {"TABLE_SCHEMA": "shop", "TABLE_NAME": "stores", "TABLE_TYPE": "VIEW"},
        ],
        [
            {
                "TABLE_NAME": "orders",
                "COLUMN_NAME": "order_id",
                "COLUMN_TYPE": "bigint unsigned",
                "IS_NULLABLE": "NO",
            },
            {
                "TABLE_NAME": "orders",
                "COLUMN_NAME": "store_id",
                "COLUMN_TYPE": "varchar(36)",
                "IS_NULLABLE": "NO",
            },
        ],
        [
            {
                "TABLE_NAME": "orders",
                "CONSTRAINT_NAME": "PRIMARY",
                "CONSTRAINT_TYPE": "PRIMARY KEY",
                "COLUMN_NAME": "order_id",
                "ORDINAL_POSITION": 1,
                "REFERENCED_TABLE_SCHEMA": None,
                "REFERENCED_TABLE_NAME": None,
                "REFERENCED_COLUMN_NAME": None,
                "UPDATE_RULE": None,
                "DELETE_RULE": None,
            },
            {
                "TABLE_NAME": "orders",
                "CONSTRAINT_NAME": "orders_store_fk",
                "CONSTRAINT_TYPE": "FOREIGN KEY",
                "COLUMN_NAME": "store_id",
                "ORDINAL_POSITION": 1,
                "REFERENCED_TABLE_SCHEMA": "shop",
                "REFERENCED_TABLE_NAME": "stores",
                "REFERENCED_COLUMN_NAME": "store_id",
                "UPDATE_RULE": "CASCADE",
                "DELETE_RULE": "RESTRICT",
            },
        ],
    )

    catalog = {item["name"]: item for item in MySQLAdapter().get_schema_catalog(connection)}

    assert catalog["orders"]["kind"] == "table"
    assert catalog["stores"]["kind"] == "view"
    assert catalog["orders"]["primary_key"] == {
        "name": "PRIMARY",
        "columns": ["order_id"],
    }
    assert catalog["orders"]["foreign_keys"][0]["referenced_table"] == "stores"
    assert catalog["orders"]["foreign_keys"][0]["on_update"] == "CASCADE"
    assert "information_schema.TABLE_CONSTRAINTS" in connection.executed[2]
    assert connection.executed[2].count("WHERE tc.TABLE_SCHEMA = DATABASE()") == 1


def test_postgresql_catalog_uses_ordered_catalog_arrays_for_composite_constraints() -> None:
    connection = _ScriptedConnection(
        [("orders", "BASE TABLE")],
        [
            ("orders", "tenant_id", "uuid", "NO"),
            ("orders", "order_id", "bigint", "NO"),
            ("orders", "store_id", "uuid", "YES"),
        ],
        [
            (
                "orders",
                "orders_pkey",
                "p",
                ["tenant_id", "order_id"],
                None,
                None,
                None,
                "a",
                "a",
            ),
            (
                "orders",
                "orders_store_fk",
                "f",
                ["store_id"],
                "public",
                "stores",
                ["store_id"],
                "c",
                "r",
            ),
        ],
    )

    catalog = PostgreSQLAdapter().get_schema_catalog(connection)

    assert catalog[0]["schema"] == "public"
    assert catalog[0]["primary_key"]["columns"] == ["tenant_id", "order_id"]
    assert catalog[0]["foreign_keys"][0]["on_update"] == "CASCADE"
    assert catalog[0]["foreign_keys"][0]["on_delete"] == "RESTRICT"
    assert "pg_catalog.pg_constraint" in connection.executed[2]


def test_constraint_query_failure_is_explicitly_unknown_instead_of_empty() -> None:
    connection = _ScriptedConnection(
        [{"TABLE_SCHEMA": "shop", "TABLE_NAME": "orders", "TABLE_TYPE": "BASE TABLE"}],
        [
            {
                "TABLE_NAME": "orders",
                "COLUMN_NAME": "order_id",
                "COLUMN_TYPE": "bigint",
                "IS_NULLABLE": "NO",
            }
        ],
        RuntimeError("permission denied"),
    )

    catalog = MySQLAdapter().get_schema_catalog(connection)

    assert catalog[0]["column_metadata_status"] == "available"
    assert catalog[0]["constraint_metadata_status"] == "unavailable"
    assert catalog[0]["primary_key"] is None
    assert catalog[0]["foreign_keys"] is None
    assert catalog[0]["unique_constraints"] is None
    assert catalog[0]["columns"][0]["nullable"] is False
    assert catalog[0]["columns"][0]["primary_key"] is None
    assert catalog[0]["columns"][0]["unique"] is None


def test_mysql_bounded_catalog_limits_relations_and_columns_before_fetchall() -> None:
    connection = _ScriptedConnection(
        [
            {"TABLE_SCHEMA": "shop", "TABLE_NAME": "alpha", "TABLE_TYPE": "BASE TABLE"},
            {"TABLE_SCHEMA": "shop", "TABLE_NAME": "beta", "TABLE_TYPE": "BASE TABLE"},
            {"TABLE_SCHEMA": "shop", "TABLE_NAME": "gamma", "TABLE_TYPE": "BASE TABLE"},
        ],
        [
            {"COLUMN_NAME": "id", "COLUMN_TYPE": "bigint", "IS_NULLABLE": "NO"},
            {"COLUMN_NAME": "one", "COLUMN_TYPE": "text", "IS_NULLABLE": "YES"},
            {"COLUMN_NAME": "two", "COLUMN_TYPE": "text", "IS_NULLABLE": "YES"},
        ],
        [
            {"COLUMN_NAME": "id", "COLUMN_TYPE": "bigint", "IS_NULLABLE": "NO"},
            {"COLUMN_NAME": "one", "COLUMN_TYPE": "text", "IS_NULLABLE": "YES"},
        ],
    )

    catalog = MySQLAdapter().get_bounded_schema_catalog(
        connection,
        max_relations=2,
        max_columns_per_relation=2,
        max_total_columns=3,
    )

    assert [table["name"] for table in catalog.tables] == ["alpha", "beta"]
    assert sum(len(table["columns"]) for table in catalog.tables) == 3
    assert catalog.relations_truncated is True
    assert catalog.unread_relations_at_least == 1
    assert catalog.columns_truncated is True
    assert "ORDER BY TABLE_NAME LIMIT 3" in connection.executed[0]
    assert "LIMIT 3" in connection.executed[1]
    assert "LIMIT 2" in connection.executed[2]


def test_postgresql_bounded_catalog_limits_relations_and_columns_before_fetchall() -> None:
    connection = _ScriptedConnection(
        [
            ("alpha", "BASE TABLE"),
            ("beta", "BASE TABLE"),
            ("gamma", "BASE TABLE"),
        ],
        [
            ("id", "bigint", "NO"),
            ("one", "text", "YES"),
            ("two", "text", "YES"),
        ],
        [
            ("id", "bigint", "NO"),
            ("one", "text", "YES"),
        ],
    )

    catalog = PostgreSQLAdapter().get_bounded_schema_catalog(
        connection,
        max_relations=2,
        max_columns_per_relation=2,
        max_total_columns=3,
    )

    assert [table["name"] for table in catalog.tables] == ["alpha", "beta"]
    assert sum(len(table["columns"]) for table in catalog.tables) == 3
    assert catalog.relations_truncated is True
    assert catalog.unread_relations_at_least == 1
    assert catalog.columns_truncated is True
    assert "LIMIT %s" in connection.executed[0]
    assert "LIMIT %s" in connection.executed[1]
    assert "LIMIT %s" in connection.executed[2]


def test_database_preflight_prioritizes_declared_grain_and_emits_fk_evidence_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(SIDECAR_ENV, raising=False)
    database_path = tmp_path / "preflight-constraints.db"
    with sqlite3.connect(database_path) as conn:
        conn.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE stores (store_id TEXT PRIMARY KEY, name TEXT);
            CREATE TABLE orders (
                order_id TEXT PRIMARY KEY,
                store_id TEXT NOT NULL,
                amount REAL,
                FOREIGN KEY (store_id) REFERENCES stores(store_id)
            );
            INSERT INTO stores VALUES ('S-1', 'North'), ('S-2', 'South');
            INSERT INTO orders VALUES ('O-1', 'S-1', 10), ('O-2', 'S-2', 20);
            """
        )

    manager = DatabaseManager(DatabaseConfig(driver="sqlite", database=str(database_path)))
    result = run_database_value_preflight(manager)

    declared_grain = [
        item
        for item in result.preanalysis["candidate_grain"]
        if item["evidence_kind"] == "database_constraint"
    ]
    assert declared_grain
    assert all(item["catalog_verified"] is True for item in declared_grain)
    assert all(item["uniqueness_basis"] == "declared_constraint" for item in declared_grain)
    assert all(item["evidence_priority"] in {0, 1} for item in declared_grain)

    assert result.preanalysis["relationship_evidence"] == [
        {
            "kind": "declared_foreign_key",
            "state": "evidence_only",
            "validity": "unverified",
            "catalog_verified": True,
            "binding_complete": True,
            "automatic_confirmation": False,
            "requires_value_validation": True,
            "constraint_name": None,
            "source": {
                "schema": "main",
                "table": "orders",
                "columns": ["store_id"],
            },
            "target": {
                "schema": "main",
                "table": "stores",
                "columns": ["store_id"],
            },
            "on_update": "NO ACTION",
            "on_delete": "NO ACTION",
        }
    ]
