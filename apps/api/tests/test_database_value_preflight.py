from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from app.services.database import DatabaseConfig, DatabaseManager, QueryResult
from app.services.database_adapters import MySQLAdapter, PostgreSQLAdapter, SQLiteAdapter
from app.services.database_value_preflight import (
    DatabaseValuePreflightBudget,
    run_database_value_preflight,
)
from app.services.sqlite_trusted_executor import SIDECAR_ENV


def _create_profile_database(path: Path, *, rows: int = 300) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            '''
            CREATE TABLE "order-items" (
                order_id TEXT,
                order_date TEXT,
                amount REAL,
                channel TEXT,
                customer_email TEXT,
                freeform_note TEXT,
                "select" TEXT
            )
            '''
        )
        conn.executemany(
            'INSERT INTO "order-items" VALUES (?, ?, ?, ?, ?, ?, ?)',
            [
                (
                    f"ORDER-{index:04d}",
                    f"2026-07-{index % 28 + 1:02d}",
                    float(index),
                    "online" if index % 2 else "retail",
                    f"person{index}@example.test",
                    f"memo-private-{index}",
                    "yes" if index % 3 else "no",
                )
                for index in range(rows)
            ],
        )


def test_sqlite_value_preflight_profiles_bounded_aggregates_without_raw_sensitive_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(SIDECAR_ENV, raising=False)
    database_path = tmp_path / "shop.db"
    _create_profile_database(database_path)
    manager = DatabaseManager(DatabaseConfig(driver="sqlite", database=str(database_path)))
    executed_sql: list[str] = []
    original_execute = manager._execute_sql

    def capture_execute(conn: Any, sql: str, max_rows: int | None = None, **kwargs: Any):
        executed_sql.append(sql)
        return original_execute(conn, sql, max_rows, **kwargs)

    monkeypatch.setattr(manager, "_execute_sql", capture_execute)
    result = run_database_value_preflight(manager)

    assert result.status == "ready"
    assert result.preanalysis["read_only"] is True
    assert result.preanalysis["shape"] == {
        "tables": 1,
        "profiled_tables": 1,
        "columns": 7,
        "sampled_rows": 256,
        "rows_are_sampled": True,
    }
    portrait = result.preanalysis["tables"][0]
    assert portrait["table"] == "order-items"
    assert portrait["sample"]["rows_profiled"] == 256
    assert portrait["sample"]["truncated"] is True

    profiles = {item["column"]: item for item in portrait["candidate_roles"]}
    assert profiles["order_id"]["role"] == "identifier"
    assert profiles["order_id"]["sample_unique"] == 256
    assert profiles["order_id"]["value_visibility"] == "suppressed_identifier"
    assert profiles["order_date"]["role"] == "time"
    assert profiles["order_date"]["range"] == {
        "start": "2026-07-01T00:00:00",
        "end": "2026-07-28T00:00:00",
    }
    assert profiles["amount"]["role"] == "measure"
    assert profiles["amount"]["distribution"] == {
        "min": 0,
        "median": 127.5,
        "max": 255,
    }
    assert {item["value"] for item in profiles["channel"]["top_values"]} == {
        "online",
        "retail",
    }
    assert profiles["customer_email"]["value_visibility"] == "suppressed_sensitive"
    assert "top_values" not in profiles["customer_email"]
    assert profiles["freeform_note"]["value_visibility"] == "suppressed_high_cardinality"
    assert "top_values" not in profiles["freeform_note"]
    assert portrait["candidate_grain"][0]["column"] == "order_id"

    serialized = json.dumps(result.preanalysis, ensure_ascii=False)
    assert "person0@example.test" not in serialized
    assert "memo-private-0" not in serialized
    assert len(executed_sql) == 1
    assert executed_sql[0].startswith('SELECT "order_id", "order_date"')
    assert 'FROM "order-items" LIMIT 257' in executed_sql[0]
    assert "COUNT(" not in executed_sql[0].upper()

    with sqlite3.connect(database_path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM "order-items"').fetchone()[0] == 300


def test_sample_table_quotes_catalog_verified_keyword_and_punctuation_identifiers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(SIDECAR_ENV, raising=False)
    database_path = tmp_path / "quoted.db"
    with sqlite3.connect(database_path) as conn:
        conn.execute('CREATE TABLE "select" ("odd-name" TEXT, "a""b" INTEGER)')
        conn.execute('INSERT INTO "select" VALUES ("safe", 3)')

    manager = DatabaseManager(DatabaseConfig(driver="sqlite", database=str(database_path)))
    result = manager.sample_table("select", ["odd-name", 'a"b'])

    assert result.data == [{"odd-name": "safe", 'a"b': 3}]
    with pytest.raises(ValueError, match="不在当前目录"):
        manager.sample_table("select", ["odd-name", "not-real"])
    with pytest.raises(ValueError, match="最多读取 257 行"):
        manager.sample_table("select", ["odd-name"], max_rows=258)


def test_value_preflight_reports_table_column_and_byte_budget_exhaustion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(SIDECAR_ENV, raising=False)
    database_path = tmp_path / "budget.db"
    with sqlite3.connect(database_path) as conn:
        conn.execute("CREATE TABLE first_table (id TEXT, description TEXT)")
        conn.execute("INSERT INTO first_table VALUES ('one', 'a value larger than the budget')")
        conn.execute("CREATE TABLE second_table (id TEXT)")
        conn.execute("INSERT INTO second_table VALUES ('two')")

    manager = DatabaseManager(DatabaseConfig(driver="sqlite", database=str(database_path)))
    result = run_database_value_preflight(
        manager,
        budget=DatabaseValuePreflightBudget(
            max_tables=1,
            max_columns_per_table=1,
            max_total_columns=1,
            max_sample_bytes=2,
        ),
    )

    assert result.status == "partial"
    issue_codes = {item["code"] for item in result.issues}
    assert "database_table_budget_reached" in issue_codes
    assert "database_table_column_budget_reached" in issue_codes
    assert "database_sample_byte_budget_reached" in issue_codes
    assert result.preanalysis["tables"][0]["sample"]["rows_profiled"] == 0
    assert result.preanalysis["budget"]["sampled_bytes"] <= 2


def test_value_preflight_keeps_successful_tables_when_one_sample_fails() -> None:
    class PartialManager:
        def get_schema_catalog(self):
            return [
                {"name": "bad", "columns": [{"name": "id", "type": "INTEGER"}]},
                {"name": "good", "columns": [{"name": "amount", "type": "REAL"}]},
            ]

        def sample_table(self, table_name: str, columns: list[str], **kwargs: Any):
            assert kwargs["max_rows"] == 257
            if table_name == "bad":
                raise TimeoutError("server detail must not be exposed")
            return QueryResult(data=[{"amount": 4.5}], rows_count=1)

    result = run_database_value_preflight(PartialManager())  # type: ignore[arg-type]

    assert result.status == "partial"
    assert [item["table"] for item in result.preanalysis["tables"]] == ["good"]
    assert result.preanalysis["partial_failures"] == [
        {
            "table": "bad",
            "code": "sample_failed",
            "message": "只读画像未完成",
            "error_type": "TimeoutError",
        }
    ]
    assert "server detail" not in json.dumps(result.preanalysis, ensure_ascii=False)


def test_driver_identifier_quoting_escapes_delimiters_and_rejects_nul() -> None:
    assert MySQLAdapter.quote_identifier("a`b") == "`a``b`"
    assert PostgreSQLAdapter.quote_identifier('a"b') == '"a""b"'
    assert SQLiteAdapter.quote_identifier('a"b') == '"a""b"'
    with pytest.raises(ValueError, match="Invalid database identifier"):
        SQLiteAdapter.quote_identifier("bad\x00name")


def test_value_preflight_budget_rejects_more_than_256_profile_rows() -> None:
    with pytest.raises(ValueError, match="最多使用 256 行样本"):
        DatabaseValuePreflightBudget(profile_rows=257)


def test_catalog_budget_is_applied_before_full_schema_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(SIDECAR_ENV, raising=False)
    database_path = tmp_path / "large-catalog.db"
    with sqlite3.connect(database_path) as conn:
        for table_name in ("alpha", "beta", "gamma"):
            conn.execute(
                f'CREATE TABLE "{table_name}" '
                "(id INTEGER, first_value TEXT, second_value TEXT, third_value TEXT)"
            )

    manager = DatabaseManager(DatabaseConfig(driver="sqlite", database=str(database_path)))
    catalog = manager.get_bounded_schema_catalog(
        max_relations=2,
        max_columns_per_relation=2,
        max_total_columns=3,
    )

    assert [table["name"] for table in catalog.tables] == ["alpha", "beta"]
    assert sum(len(table["columns"]) for table in catalog.tables) == 3
    assert catalog.relations_truncated is True
    assert catalog.unread_relations_at_least == 1
    assert catalog.columns_truncated is True
    assert catalog.unread_columns_at_least == 2
    assert all(
        table["column_metadata_status"] == "truncated" for table in catalog.tables
    )

    result = run_database_value_preflight(
        manager,
        budget=DatabaseValuePreflightBudget(
            max_tables=2,
            max_columns_per_table=2,
            max_total_columns=3,
        ),
    )
    assert result.status == "partial"
    assert len(result.catalog) == 2
    assert result.preanalysis["catalog"] == {
        "relations_loaded": 2,
        "relations_truncated": True,
        "unread_relations_at_least": 1,
        "columns_loaded": 3,
        "columns_truncated": True,
        "unread_columns_at_least": 2,
    }
