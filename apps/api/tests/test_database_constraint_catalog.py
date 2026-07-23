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


def test_mysql_selected_relation_schema_keeps_declared_foreign_key() -> None:
    connection = _ScriptedConnection(
        [
            {
                "TABLE_SCHEMA": "shop",
                "TABLE_NAME": "orders",
                "TABLE_TYPE": "BASE TABLE",
                "TABLE_COMMENT": "订单",
            }
        ],
        [
            {
                "COLUMN_NAME": "store_id",
                "COLUMN_TYPE": "varchar(36)",
                "IS_NULLABLE": "NO",
            }
        ],
        [
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
            }
        ],
    )

    entry = MySQLAdapter().get_bounded_relation_schema(
        connection,
        table_name="orders",
        max_columns=8,
    )

    assert entry["schema"] == "shop"
    assert entry["constraint_metadata_status"] == "available"
    assert entry["foreign_keys"][0]["referenced_table"] == "stores"
    assert "tc.TABLE_NAME = %s" in connection.executed[2]


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


def test_postgresql_selected_relation_schema_keeps_declared_foreign_key() -> None:
    connection = _ScriptedConnection(
        [("orders", "table", "订单")],
        [("store_id", "uuid", "NO")],
        [
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
            )
        ],
    )

    entry = PostgreSQLAdapter().get_bounded_relation_schema(
        connection,
        table_name="orders",
        max_columns=8,
    )

    assert entry["schema"] == "public"
    assert entry["constraint_metadata_status"] == "available"
    assert entry["foreign_keys"][0]["referenced_table"] == "stores"
    assert "relation.relname = %s" in connection.executed[2]


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


def test_mysql_relation_index_is_metadata_only_bounded_and_keeps_comments() -> None:
    connection = _ScriptedConnection(
        [
            {
                "TABLE_SCHEMA": "shop",
                "TABLE_NAME": "alpha",
                "TABLE_TYPE": "BASE TABLE",
                "TABLE_COMMENT": "2024 年商品主数据",
            },
            {
                "TABLE_SCHEMA": "shop",
                "TABLE_NAME": "beta",
                "TABLE_TYPE": "VIEW",
                "TABLE_COMMENT": "",
            },
            {
                "TABLE_SCHEMA": "shop",
                "TABLE_NAME": "gamma",
                "TABLE_TYPE": "BASE TABLE",
                "TABLE_COMMENT": "未返回",
            },
        ]
    )

    index = MySQLAdapter().get_bounded_relation_index(connection, max_relations=2)

    assert index.relations == [
        {
            "name": "alpha",
            "schema": "shop",
            "kind": "table",
            "comment": "2024 年商品主数据",
        },
        {"name": "beta", "schema": "shop", "kind": "view", "comment": None},
    ]
    assert index.truncated is True
    assert index.unread_relations_at_least == 1
    assert "TABLE_COMMENT" in connection.executed[0]
    assert "LIMIT 3" in connection.executed[0]


def test_postgresql_relation_index_uses_catalog_comments_and_kind() -> None:
    connection = _ScriptedConnection(
        [
            ("products", "partitioned_table", "按年份分区的商品表"),
            ("sales_view", "materialized_view", None),
        ]
    )

    index = PostgreSQLAdapter().get_bounded_relation_index(
        connection,
        max_relations=5,
    )

    assert index.relations == [
        {
            "name": "products",
            "schema": "public",
            "kind": "partitioned_table",
            "comment": "按年份分区的商品表",
        },
        {
            "name": "sales_view",
            "schema": "public",
            "kind": "materialized_view",
            "comment": None,
        },
    ]
    assert index.truncated is False
    assert "pg_catalog.obj_description" in connection.executed[0]


def test_sqlite_relation_index_pages_without_repeating_the_first_tables(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(SIDECAR_ENV, raising=False)
    database_path = tmp_path / "paged-index.db"
    with sqlite3.connect(database_path) as conn:
        conn.executescript(
            """
            CREATE TABLE alpha (id INTEGER);
            CREATE TABLE beta (id INTEGER);
            CREATE TABLE gamma (id INTEGER);
            """
        )

    manager = DatabaseManager(DatabaseConfig(driver="sqlite", database=str(database_path)))
    first = manager.get_bounded_relation_index(max_relations=2)
    second = manager.get_bounded_relation_index(
        max_relations=2,
        after=first.relations[-1]["name"],
    )

    assert [item["name"] for item in first.relations] == ["alpha", "beta"]
    assert first.truncated is True
    assert [item["name"] for item in second.relations] == ["gamma"]
    assert second.truncated is False


def test_selected_relation_schema_reads_the_requested_table_not_catalog_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(SIDECAR_ENV, raising=False)
    database_path = tmp_path / "selected-schema.db"
    with sqlite3.connect(database_path) as conn:
        conn.executescript(
            """
            CREATE TABLE alpha (ignored INTEGER);
            CREATE TABLE omega (published_at TEXT, sales_amount REAL);
            """
        )

    manager = DatabaseManager(DatabaseConfig(driver="sqlite", database=str(database_path)))
    selected = manager.get_bounded_relation_schema("omega", max_columns=8)

    assert selected["name"] == "omega"
    assert [item["name"] for item in selected["columns"]] == [
        "published_at",
        "sales_amount",
    ]


def test_selected_sqlite_relation_schema_preserves_declared_foreign_keys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(SIDECAR_ENV, raising=False)
    database_path = tmp_path / "selected-relationship.db"
    with sqlite3.connect(database_path) as conn:
        conn.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE stores (store_id TEXT PRIMARY KEY, name TEXT);
            CREATE TABLE orders (
                order_id TEXT PRIMARY KEY,
                store_id TEXT NOT NULL,
                FOREIGN KEY (store_id) REFERENCES stores(store_id)
            );
            """
        )

    manager = DatabaseManager(DatabaseConfig(driver="sqlite", database=str(database_path)))
    selected = manager.get_bounded_relation_schema("orders", max_columns=8)

    assert selected["constraint_metadata_status"] == "available"
    assert selected["primary_key"]["columns"] == ["order_id"]
    assert selected["foreign_keys"] == [
        {
            "name": None,
            "catalog_id": 0,
            "columns": ["store_id"],
            "referenced_schema": "main",
            "referenced_table": "stores",
            "referenced_columns": ["store_id"],
            "on_update": "NO ACTION",
            "on_delete": "NO ACTION",
            "match": "NONE",
        }
    ]


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
