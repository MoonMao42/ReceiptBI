"""Bounded, read-only value profiling for attached databases.

Schema discovery alone leaves the analyst guessing whether a column is a key,
measure, time, or useful grouping dimension.  This module reads a deliberately
small sample and turns it into aggregate-only ``profile.preanalysis`` data.  It
never runs counts, writes to the source, or returns arbitrary sample records.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
import threading
import time
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.services.database import (
    MAX_DATABASE_PROFILE_SAMPLE_ROWS,
    DatabaseManager,
    QueryResult,
)
from app.services.database_adapters import (
    BoundedRelationIndex,
    BoundedSchemaCatalog,
    DatabaseQueryCancelledError,
)
from app.services.semantic_field_roles import (
    SEMANTIC_ROLE_INFERENCE_VERSION,
    infer_semantic_field_role,
)

PROFILE_ROWS = MAX_DATABASE_PROFILE_SAMPLE_ROWS - 1
DEFAULT_DATABASE_RELATION_INDEX_LIMIT = 512

_NUMERIC_TYPE_HINTS = (
    "int",
    "real",
    "float",
    "double",
    "decimal",
    "numeric",
    "number",
    "money",
)
_TIME_TYPE_HINTS = ("date", "time", "timestamp", "datetime")
_SENSITIVE_HINTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "credential",
    "private_key",
    "access_key",
    "api_key",
    "email",
    "e_mail",
    "phone",
    "mobile",
    "telephone",
    "address",
    "id_card",
    "identity_card",
    "passport",
    "ssn",
    "customer_name",
    "user_name",
    "full_name",
    "first_name",
    "last_name",
    "bank_account",
    "account_number",
    "card_number",
    "credit_card",
    "salary",
    "wage",
    "compensation",
    "ip_address",
    "birth_date",
    "birthday",
    "date_of_birth",
    "密码",
    "密钥",
    "令牌",
    "邮箱",
    "电话",
    "手机",
    "地址",
    "身份证",
    "护照",
    "客户姓名",
    "用户姓名",
    "银行卡",
    "银行账户",
    "卡号",
    "工资",
    "薪资",
    "薪酬",
    "生日",
)


@dataclass(frozen=True, slots=True)
class DatabaseValuePreflightBudget:
    """Hard limits for one database profiling pass."""

    max_tables: int = 24
    max_relation_index: int = DEFAULT_DATABASE_RELATION_INDEX_LIMIT
    max_columns_per_table: int = 80
    max_total_columns: int = 480
    max_sample_bytes: int = 2 * 1024 * 1024
    timeout_seconds: float = 10.0
    per_table_timeout_seconds: float = 3.0
    profile_rows: int = PROFILE_ROWS

    def __post_init__(self) -> None:
        integer_limits = {
            "max_tables": self.max_tables,
            "max_relation_index": self.max_relation_index,
            "max_columns_per_table": self.max_columns_per_table,
            "max_total_columns": self.max_total_columns,
            "max_sample_bytes": self.max_sample_bytes,
            "profile_rows": self.profile_rows,
        }
        if any(value <= 0 for value in integer_limits.values()):
            raise ValueError("数据库画像预算必须大于 0")
        if self.profile_rows > PROFILE_ROWS:
            raise ValueError(f"数据库画像最多使用 {PROFILE_ROWS} 行样本")
        if self.timeout_seconds <= 0 or self.per_table_timeout_seconds <= 0:
            raise ValueError("数据库画像时间预算必须大于 0")


@dataclass(frozen=True, slots=True)
class DatabaseValuePreflightResult:
    status: str
    summary: str
    preanalysis: dict[str, Any]
    issues: list[dict[str, Any]]
    catalog: list[dict[str, Any]] = field(default_factory=list)
    catalog_status: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DatabaseRelationProfileResult:
    """One selected relation's bounded schema and optional value portrait."""

    catalog_entry: dict[str, Any]
    portrait: dict[str, Any]


def bounded_relation_index_snapshot(
    relation_index: BoundedRelationIndex,
) -> dict[str, Any]:
    """Serialize one bounded metadata directory without claiming an unknown total."""

    relations = [dict(item) for item in relation_index.relations]
    unread_relations_at_least = max(
        int(relation_index.unread_relations_at_least),
        int(relation_index.truncated),
    )
    relations_total_at_least = len(relations) + unread_relations_at_least
    return {
        "relations": relations,
        "relations_loaded": len(relations),
        "relations_total": len(relations) if not relation_index.truncated else None,
        "relations_total_at_least": relations_total_at_least,
        "complete": not relation_index.truncated,
        "truncated": relation_index.truncated,
        "unread_relations_at_least": unread_relations_at_least,
    }


def run_database_value_preflight(
    manager: DatabaseManager,
    *,
    budget: DatabaseValuePreflightBudget | None = None,
    cancellation_event: threading.Event | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> DatabaseValuePreflightResult:
    """Build aggregate table portraits from bounded database samples.

    The returned ``preanalysis`` dictionary is ready to store at
    ``ProjectDataSource.profile_data["preanalysis"]``.
    """

    limits = budget or DatabaseValuePreflightBudget()
    started_at = clock()
    deadline = started_at + limits.timeout_seconds
    issues: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []

    try:
        relation_index: BoundedRelationIndex | None = None
        full_catalog: list[dict[str, Any]] | None = None
        relation_index_reader = getattr(manager, "get_bounded_relation_index", None)
        if callable(relation_index_reader):
            try:
                relation_index = relation_index_reader(
                    max_relations=limits.max_relation_index,
                )
            except Exception:
                # The deep catalog below remains a truthful bounded fallback for
                # older drivers or restricted metadata permissions.
                relation_index = None
        bounded_reader = getattr(manager, "get_bounded_schema_catalog", None)
        if callable(bounded_reader):
            bounded_catalog = bounded_reader(
                max_relations=limits.max_tables,
                max_columns_per_relation=limits.max_columns_per_table,
                max_total_columns=limits.max_total_columns,
            )
        else:
            # Compatibility for narrow test doubles. Production DatabaseManager
            # always executes the server-bounded path above.
            full_catalog = sorted(
                manager.get_schema_catalog(),
                key=lambda item: str(item.get("name", "")),
            )
            bounded_catalog = BoundedSchemaCatalog(
                tables=full_catalog[: limits.max_tables],
                relations_truncated=len(full_catalog) > limits.max_tables,
                unread_relations_at_least=int(len(full_catalog) > limits.max_tables),
            )
        catalog = sorted(
            bounded_catalog.tables,
            key=lambda item: str(item.get("name", "")),
        )
        if relation_index is None:
            fallback_catalog = full_catalog if full_catalog is not None else catalog
            fallback_relations = [
                {
                    "name": str(item.get("name") or ""),
                    "schema": item.get("schema"),
                    "kind": str(item.get("kind") or "unknown"),
                    "comment": item.get("comment"),
                }
                for item in fallback_catalog[: limits.max_relation_index]
                if str(item.get("name") or "")
            ]
            fallback_truncated = (
                len(fallback_catalog) > limits.max_relation_index
                or bounded_catalog.relations_truncated
            )
            relation_index = BoundedRelationIndex(
                relations=fallback_relations,
                truncated=fallback_truncated,
                unread_relations_at_least=int(fallback_truncated),
            )
    except Exception as exc:
        failure = _failure(None, "catalog_unavailable", exc)
        return DatabaseValuePreflightResult(
            status="error",
            summary="数据库字段目录暂时无法读取，未进行数据画像",
            preanalysis=_empty_preanalysis(failures=[failure]),
            issues=[
                _issue(
                    "database_catalog_unavailable",
                    "数据库字段目录暂时无法读取",
                    "没有读取任何业务数据，也没有修改数据库。",
                    severity="critical",
                )
            ],
        )

    total_tables = len(catalog)
    relation_index_data = bounded_relation_index_snapshot(relation_index)
    indexed_relations_at_least = relation_index_data["relations_total_at_least"]
    relationship_evidence = _foreign_key_relationship_evidence(catalog)
    selected_catalog = catalog
    if bounded_catalog.relations_truncated:
        issues.append(
            _issue(
                "database_table_budget_reached",
                f"本次先深入画像 {len(selected_catalog)} 张表",
                "其他表已保留在目录中，可在需要时继续读取字段并画像。",
            )
        )
    if bounded_catalog.columns_truncated:
        issues.append(
            _issue(
                "database_catalog_column_budget_reached",
                "本次字段目录已达到预算",
                "部分表至少还有字段未读取目录和值，可按需继续画像。",
            )
        )
        for table in catalog:
            if table.get("column_metadata_status") != "truncated":
                continue
            issues.append(
                _issue(
                    "database_table_column_budget_reached",
                    f"{table.get('name') or '当前表'} 只读取了预算内字段",
                    "该表至少还有 1 个字段未读取目录和值。",
                    table=str(table.get("name") or ""),
                )
            )

    portraits: list[dict[str, Any]] = []
    flattened_roles: list[dict[str, Any]] = []
    flattened_grain: list[dict[str, Any]] = []
    remaining_columns = limits.max_total_columns
    remaining_bytes = limits.max_sample_bytes
    byte_budget_exhausted = False
    time_budget_exhausted = False

    for catalog_entry in selected_catalog:
        table_name = str(catalog_entry.get("name") or "")
        if cancellation_event is not None and cancellation_event.is_set():
            failures.append(
                {
                    "table": table_name,
                    "code": "cancelled",
                    "message": "用户已取消剩余数据库画像",
                }
            )
            break
        remaining_time = deadline - clock()
        if remaining_time <= 0:
            time_budget_exhausted = True
            break
        if remaining_columns <= 0:
            issues.append(
                _issue(
                    "database_column_budget_reached",
                    "本次字段画像额度已用完",
                    "剩余表仅保留字段目录，没有读取字段值。",
                )
            )
            break
        if remaining_bytes <= 0:
            byte_budget_exhausted = True
            break

        raw_columns = [
            item
            for item in list(catalog_entry.get("columns") or [])
            if isinstance(item, dict) and item.get("name")
        ]
        selected_columns = raw_columns[
            : min(limits.max_columns_per_table, remaining_columns)
        ]
        if len(selected_columns) < len(raw_columns):
            issues.append(
                _issue(
                    "database_table_column_budget_reached",
                    f"{table_name} 只画像前 {len(selected_columns)} 个字段",
                    f"该表另有 {len(raw_columns) - len(selected_columns)} 个字段未读取值。",
                    table=table_name,
                )
            )
        if not selected_columns:
            failures.append(
                {
                    "table": table_name,
                    "code": "no_profileable_columns",
                    "message": "没有可画像字段",
                }
            )
            continue

        column_names = [str(item["name"]) for item in selected_columns]
        try:
            query_result = manager.sample_table(
                table_name,
                column_names,
                max_rows=limits.profile_rows + 1,
                timeout_seconds=min(limits.per_table_timeout_seconds, remaining_time),
                cancellation_event=cancellation_event,
            )
        except Exception as exc:
            failures.append(_failure(table_name, "sample_failed", exc))
            continue

        sample_rows, consumed_bytes, sample_byte_limited = _rows_within_byte_budget(
            query_result.data[: limits.profile_rows],
            columns=column_names,
            byte_budget=remaining_bytes,
        )
        remaining_bytes -= consumed_bytes
        remaining_columns -= len(selected_columns)
        sample_truncated = (
            query_result.truncated
            or query_result.rows_count > limits.profile_rows
            or sample_byte_limited
        )
        portrait = _profile_table(
            catalog_entry,
            selected_columns,
            sample_rows,
            sample_truncated=sample_truncated,
            sampled_bytes=consumed_bytes,
            profile_row_limit=limits.profile_rows,
            query_result=query_result,
        )
        if sample_byte_limited:
            portrait["partial_reasons"] = ["byte_budget_reached"]
            issues.append(
                _issue(
                    "database_sample_byte_budget_reached",
                    f"{table_name} 的值画像已达到字节预算",
                    "只保留预算内的聚合统计，没有暴露被截断的原值。",
                    table=table_name,
                )
            )
            byte_budget_exhausted = True
        portraits.append(portrait)
        flattened_roles.extend(
            {"table": table_name, **item} for item in portrait["candidate_roles"]
        )
        flattened_grain.extend(portrait["candidate_grain"])
        if clock() >= deadline:
            time_budget_exhausted = True
            break
        if byte_budget_exhausted:
            break

    if time_budget_exhausted:
        issues.append(
            _issue(
                "database_preflight_time_budget_reached",
                "数据库画像已达到时间预算",
                "已完成的表画像可以正常使用，剩余表没有读取值。",
            )
        )
    if byte_budget_exhausted and not any(
        item["code"] == "database_sample_byte_budget_reached" for item in issues
    ):
        issues.append(
            _issue(
                "database_preflight_byte_budget_reached",
                "数据库画像已达到字节预算",
                "已完成的聚合画像可以正常使用，剩余表没有读取值。",
            )
        )
    if failures:
        issues.append(
            _issue(
                "database_tables_partially_unavailable",
                f"有 {len(failures)} 张表本次没有完成画像",
                "其他表的结果仍可使用；失败信息已单独记录，没有修改数据库。",
            )
        )

    elapsed_ms = max(0, round((clock() - started_at) * 1000))
    profiled_rows = sum(int(item["sample"]["rows_profiled"]) for item in portraits)
    preanalysis = {
        "generated_by": "deterministic_database_value_preflight",
        "semantic_role_inference_version": SEMANTIC_ROLE_INFERENCE_VERSION,
        "requires_query_verification": True,
        "read_only": True,
        "catalog": {
            "relations_loaded": total_tables,
            "relations_truncated": bounded_catalog.relations_truncated,
            "unread_relations_at_least": bounded_catalog.unread_relations_at_least,
            "columns_loaded": sum(
                len(table.get("columns") or []) for table in catalog
            ),
            "columns_truncated": bounded_catalog.columns_truncated,
            "unread_columns_at_least": bounded_catalog.unread_columns_at_least,
        },
        "relation_index": relation_index_data,
        "shape": {
            "tables": indexed_relations_at_least,
            "profiled_tables": len(portraits),
            "columns": sum(len(item["candidate_roles"]) for item in portraits),
            "sampled_rows": profiled_rows,
            "rows_are_sampled": True,
        },
        "tables": portraits,
        "candidate_roles": flattened_roles,
        "candidate_grain": flattened_grain,
        "relationship_evidence": relationship_evidence,
        "partial_failures": failures,
        "budget": {
            "profile_rows_per_table": limits.profile_rows,
            "query_rows_per_table": limits.profile_rows + 1,
            "max_tables": limits.max_tables,
            "max_relation_index": limits.max_relation_index,
            "max_columns_per_table": limits.max_columns_per_table,
            "max_total_columns": limits.max_total_columns,
            "max_sample_bytes": limits.max_sample_bytes,
            "timeout_seconds": limits.timeout_seconds,
            "sampled_bytes": limits.max_sample_bytes - max(remaining_bytes, 0),
            "elapsed_ms": elapsed_ms,
        },
    }
    if relation_index.truncated:
        preanalysis["shape"]["tables_are_lower_bound"] = True
    partial = bool(
        failures
        or issues
        or len(portraits) < total_tables
        or time_budget_exhausted
        or byte_budget_exhausted
        or bounded_catalog.relations_truncated
        or bounded_catalog.columns_truncated
    )
    if not portraits and total_tables:
        status = "error"
        summary = "数据库连接可用，但本次没有完成值画像"
    else:
        status = "partial" if partial else "ready"
        summary = (
            f"已用只读采样画像 {len(portraits)} 张表、"
            f"{sum(len(item['candidate_roles']) for item in portraits)} 个字段"
        )
        if partial:
            summary += "，部分表或字段可按需继续"
    preanalysis["summary_code"] = "database_value_preflight"
    preanalysis["summary_facts"] = {
        "profiled_tables": len(portraits),
        "profiled_columns": sum(len(item["candidate_roles"]) for item in portraits),
        "status": status,
        "partial": partial,
    }
    return DatabaseValuePreflightResult(
        status=status,
        summary=summary,
        preanalysis=preanalysis,
        issues=issues,
        catalog=catalog,
        catalog_status=dict(preanalysis["catalog"]),
    )


def profile_selected_database_relation(
    manager: DatabaseManager,
    relation: dict[str, Any],
    *,
    budget: DatabaseValuePreflightBudget | None = None,
    cancellation_event: threading.Event | None = None,
) -> DatabaseRelationProfileResult:
    """Profile exactly one user-selected relation within the existing hard limits.

    Relation selection comes from the metadata-only relation index.  This helper
    deliberately does not enumerate the first N catalog tables, which lets a
    resumable inventory reach catalog-only tables beyond the automatic preflight
    prefix without widening any row, byte, column, or time budget.
    """

    limits = budget or DatabaseValuePreflightBudget(
        max_tables=1,
        max_total_columns=80,
    )
    table_name = str(relation.get("name") or "").strip()
    if not table_name:
        raise ValueError("数据库画像必须指定表")
    if cancellation_event is not None and cancellation_event.is_set():
        raise DatabaseQueryCancelledError("Database profile was cancelled before execution")

    catalog_entry = manager.get_bounded_relation_schema(
        table_name,
        max_columns=min(limits.max_columns_per_table, limits.max_total_columns),
    )
    catalog_entry.update(
        {
            key: relation.get(key)
            for key in ("schema", "kind", "comment", "description")
            if relation.get(key) is not None
        }
    )
    columns = [
        dict(item)
        for item in catalog_entry.get("columns") or []
        if isinstance(item, dict) and item.get("name")
    ]
    if not columns:
        raise ValueError("所选表没有可画像字段")

    query_result = manager.sample_table(
        table_name,
        [str(item["name"]) for item in columns],
        max_rows=limits.profile_rows + 1,
        timeout_seconds=limits.per_table_timeout_seconds,
        cancellation_event=cancellation_event,
    )
    rows, sampled_bytes, byte_limited = _rows_within_byte_budget(
        query_result.data[: limits.profile_rows],
        columns=[str(item["name"]) for item in columns],
        byte_budget=limits.max_sample_bytes,
    )
    portrait = _profile_table(
        catalog_entry,
        columns,
        rows,
        sample_truncated=(
            query_result.truncated
            or query_result.rows_count > limits.profile_rows
            or byte_limited
        ),
        sampled_bytes=sampled_bytes,
        profile_row_limit=limits.profile_rows,
        query_result=query_result,
    )
    if byte_limited:
        portrait["partial_reasons"] = ["byte_budget_reached"]
    return DatabaseRelationProfileResult(
        catalog_entry=catalog_entry,
        portrait=portrait,
    )


def _profile_table(
    catalog_entry: dict[str, Any],
    columns: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    *,
    sample_truncated: bool,
    sampled_bytes: int,
    profile_row_limit: int,
    query_result: QueryResult,
) -> dict[str, Any]:
    table_name = str(catalog_entry.get("name") or "")
    roles: list[dict[str, Any]] = []
    candidate_grain = _catalog_grain_candidates(
        catalog_entry,
        rows,
        selected_columns={str(column["name"]) for column in columns},
        sample_truncated=sample_truncated,
    )
    catalog_grain_signatures = {
        tuple(str(column) for column in item.get("columns") or [])
        for item in candidate_grain
    }
    for column in columns:
        name = str(column["name"])
        declared_type = str(column.get("type") or "")
        values = [row.get(name) for row in rows]
        profile = _profile_column(name, declared_type, values)
        roles.append(profile)
        non_null = int(profile["non_null"])
        uniqueness = float(profile.get("uniqueness") or 0)
        if (
            profile["role"] == "identifier"
            and non_null >= 2
            and uniqueness >= 0.98
            and (name,) not in catalog_grain_signatures
        ):
            candidate_grain.append(
                {
                    "table": table_name,
                    "column": name,
                    "columns": [name],
                    "non_null": non_null,
                    "sample_unique": int(profile["sample_unique"]),
                    "uniqueness": round(uniqueness, 6),
                    "uniqueness_basis": "bounded_sample",
                    "duplicate_values": non_null - int(profile["sample_unique"]),
                    "sample_truncated": sample_truncated,
                    "status": "candidate",
                    "evidence_kind": "sample_profile",
                    "evidence_priority": 2,
                }
            )

    return {
        "table": table_name,
        "kind": catalog_entry.get("kind") or "unknown",
        "status": "profiled",
        "constraint_metadata_status": catalog_entry.get(
            "constraint_metadata_status", "unavailable"
        ),
        "sample": {
            "rows_profiled": len(rows),
            "row_limit": profile_row_limit,
            "truncated": sample_truncated,
            "bytes_profiled": sampled_bytes,
            "execution_backend": query_result.execution_backend,
        },
        "candidate_roles": roles,
        "candidate_grain": candidate_grain,
    }


def _catalog_grain_candidates(
    catalog_entry: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    selected_columns: set[str],
    sample_truncated: bool,
) -> list[dict[str, Any]]:
    """Prefer declared PK/UNIQUE constraints without treating them as confirmed semantics."""

    if catalog_entry.get("constraint_metadata_status") != "available":
        return []
    table_name = str(catalog_entry.get("name") or "")
    column_metadata = {
        str(column.get("name")): column
        for column in catalog_entry.get("columns") or []
        if isinstance(column, dict) and column.get("name")
    }
    constraints: list[tuple[str, dict[str, Any]]] = []
    primary_key = catalog_entry.get("primary_key")
    if isinstance(primary_key, dict):
        constraints.append(("primary_key", primary_key))
    constraints.extend(
        ("unique", constraint)
        for constraint in catalog_entry.get("unique_constraints") or []
        if isinstance(constraint, dict) and not constraint.get("partial", False)
    )

    candidates: list[dict[str, Any]] = []
    for constraint_type, constraint in constraints:
        evidence_priority = 0 if constraint_type == "primary_key" else 1
        constraint_columns = [
            str(column) for column in constraint.get("columns") or [] if column is not None
        ]
        if not constraint_columns:
            continue
        nullable_values = [
            column_metadata.get(column, {}).get("nullable") for column in constraint_columns
        ]
        if any(value is True for value in nullable_values):
            nullable = True
            complete = False
        elif all(value is False for value in nullable_values):
            nullable = False
            complete = True
        else:
            nullable = None
            complete = None

        complete_sample_rows = (
            [
                row
                for row in rows
                if all(row.get(column) is not None for column in constraint_columns)
            ]
            if set(constraint_columns) <= selected_columns
            else []
        )
        sample_unique = len(
            {
                _stable_value_digest([row.get(column) for column in constraint_columns])
                for row in complete_sample_rows
            }
        )
        candidates.append(
            {
                "table": table_name,
                "column": (
                    constraint_columns[0]
                    if len(constraint_columns) == 1
                    else f"({', '.join(constraint_columns)})"
                ),
                "columns": constraint_columns,
                "constraint_name": constraint.get("name"),
                "constraint_type": constraint_type,
                "nullable": nullable,
                "complete": complete,
                "non_null": len(complete_sample_rows),
                "sample_unique": sample_unique,
                "uniqueness": 1.0,
                "uniqueness_basis": "declared_constraint",
                "duplicate_values": max(len(complete_sample_rows) - sample_unique, 0),
                "sample_truncated": sample_truncated,
                "status": "candidate",
                "catalog_verified": True,
                "evidence_kind": "database_constraint",
                "evidence_priority": evidence_priority,
            }
        )
    return candidates


def _foreign_key_relationship_evidence(
    catalog: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Expose declared FKs as evidence; execution still has to validate actual values."""

    evidence: list[dict[str, Any]] = []
    table_lookup = {
        (str(table.get("schema") or ""), str(table.get("name") or "")): table
        for table in catalog
    }
    for table in catalog:
        if table.get("constraint_metadata_status") != "available":
            continue
        source_columns = {
            str(column.get("name"))
            for column in table.get("columns") or []
            if isinstance(column, dict) and column.get("name")
        }
        for foreign_key in table.get("foreign_keys") or []:
            if not isinstance(foreign_key, dict):
                continue
            columns = [
                str(column)
                for column in foreign_key.get("columns") or []
                if column is not None
            ]
            referenced_columns = [
                str(column)
                for column in foreign_key.get("referenced_columns") or []
                if column is not None
            ]
            referenced_table = foreign_key.get("referenced_table")
            target = table_lookup.get(
                (
                    str(foreign_key.get("referenced_schema") or ""),
                    str(referenced_table or ""),
                )
            )
            target_columns = {
                str(column.get("name"))
                for column in (target or {}).get("columns") or []
                if isinstance(column, dict) and column.get("name")
            }
            binding_complete = bool(
                columns
                and referenced_table
                and len(columns) == len(referenced_columns)
                and set(columns) <= source_columns
                and set(referenced_columns) <= target_columns
            )
            evidence.append(
                {
                    "kind": "declared_foreign_key",
                    "state": "evidence_only",
                    "validity": "unverified",
                    "catalog_verified": True,
                    "binding_complete": binding_complete,
                    "automatic_confirmation": False,
                    "requires_value_validation": True,
                    "constraint_name": foreign_key.get("name"),
                    "source": {
                        "schema": table.get("schema"),
                        "table": table.get("name"),
                        "columns": columns,
                    },
                    "target": {
                        "schema": foreign_key.get("referenced_schema"),
                        "table": referenced_table,
                        "columns": referenced_columns,
                    },
                    "on_update": foreign_key.get("on_update"),
                    "on_delete": foreign_key.get("on_delete"),
                }
            )
    return sorted(
        evidence,
        key=lambda item: (
            str(item["source"].get("schema") or ""),
            str(item["source"].get("table") or ""),
            str(item.get("constraint_name") or ""),
        ),
    )


def _profile_column(name: str, declared_type: str, values: list[Any]) -> dict[str, Any]:
    non_null_values = [value for value in values if value is not None]
    sample_unique = len({_stable_value_digest(value) for value in non_null_values})
    non_null = len(non_null_values)
    role = _infer_role(name, declared_type, non_null_values)
    sensitive = _is_sensitive(name)
    uniqueness = sample_unique / non_null if non_null else 0.0
    high_cardinality = sample_unique > 20 and (uniqueness > 0.2 or sample_unique > 50)
    profile: dict[str, Any] = {
        "column": name,
        "declared_type": declared_type,
        "role": role,
        "status": "candidate",
        "non_null": non_null,
        "missing": len(values) - non_null,
        "sample_unique": sample_unique,
        "unique": sample_unique,
        "sampled": True,
    }
    if non_null:
        profile["uniqueness"] = round(uniqueness, 6)

    if sensitive:
        profile["value_visibility"] = "suppressed_sensitive"
    elif role == "identifier":
        profile["value_visibility"] = "suppressed_identifier"
    elif high_cardinality:
        profile["value_visibility"] = "suppressed_high_cardinality"
    else:
        profile["value_visibility"] = "aggregate_only"

    if role == "measure" and not sensitive:
        numeric = [_as_decimal(value) for value in non_null_values]
        usable_numeric = [value for value in numeric if value is not None]
        if usable_numeric:
            profile["distribution"] = {
                "min": _json_number(min(usable_numeric)),
                "median": _json_number(statistics.median(usable_numeric)),
                "max": _json_number(max(usable_numeric)),
            }
    elif role == "time" and not sensitive:
        parsed = [_as_datetime(value) for value in non_null_values]
        usable_dates = [value for value in parsed if value is not None]
        if usable_dates:
            profile["range"] = {
                "start": min(usable_dates).isoformat(),
                "end": max(usable_dates).isoformat(),
            }
    elif role == "dimension" and not sensitive and not high_cardinality and non_null:
        counts: Counter[str] = Counter()
        safe_values: dict[str, Any] = {}
        for value in non_null_values:
            key = _stable_value_digest(value)
            counts[key] += 1
            safe_values.setdefault(key, _json_safe_dimension(value))
        profile["top_values"] = [
            {
                "value": safe_values[key],
                "count": count,
                "share": round(count / non_null, 6),
            }
            for key, count in counts.most_common(5)
        ]
    return profile


def _infer_role(name: str, declared_type: str, values: list[Any]) -> str:
    normalized_type = declared_type.casefold()
    numeric_type = any(hint in normalized_type for hint in _NUMERIC_TYPE_HINTS)
    numeric_values = sum(_as_decimal(value) is not None for value in values)
    mostly_numeric = bool(values) and numeric_values / len(values) >= 0.8
    is_boolean = "bool" in normalized_type
    return infer_semantic_field_role(
        name,
        is_numeric=numeric_type and not is_boolean,
        is_datetime=any(hint in normalized_type for hint in _TIME_TYPE_HINTS),
        mostly_numeric=mostly_numeric and not is_boolean,
    )


def _is_sensitive(name: str) -> bool:
    lowered = name.casefold().replace("-", "_").replace(" ", "_")
    return lowered in {"name", "姓名", "contact", "联系人"} or any(
        hint in lowered for hint in _SENSITIVE_HINTS
    )


def _rows_within_byte_budget(
    rows: Iterable[dict[str, Any]],
    *,
    columns: list[str],
    byte_budget: int,
) -> tuple[list[dict[str, Any]], int, bool]:
    accepted: list[dict[str, Any]] = []
    consumed = 0
    for row in rows:
        row_bytes = sum(_value_size(row.get(column)) for column in columns)
        if consumed + row_bytes > byte_budget:
            return accepted, consumed, True
        consumed += row_bytes
        accepted.append(row)
    return accepted, consumed, False


def _value_size(value: Any) -> int:
    if value is None:
        return 1
    if isinstance(value, bytes):
        return len(value)
    return len(str(value).encode("utf-8", errors="replace"))


def _stable_value_digest(value: Any) -> str:
    if isinstance(value, bytes):
        payload = value
    elif isinstance(value, (date, datetime)):
        payload = value.isoformat().encode("utf-8")
    else:
        try:
            payload = json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError):
            payload = str(value).encode("utf-8", errors="replace")
    return hashlib.sha256(type(value).__name__.encode("ascii") + b":" + payload).hexdigest()


def _as_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        converted = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return converted if converted.is_finite() else None


def _json_number(value: Decimal) -> int | float:
    integral = value.to_integral_value()
    if value == integral:
        return int(integral)
    converted = float(value)
    return converted if math.isfinite(converted) else 0.0


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time())
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = datetime.combine(date.fromisoformat(text[:10]), datetime.min.time())
            except ValueError:
                return None
    else:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone().replace(tzinfo=None)
    return parsed


def _json_safe_dimension(value: Any) -> str | int | float | bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    if isinstance(value, Decimal):
        return _json_number(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, bytes):
        return "[binary]"
    text = str(value)
    return text if len(text) <= 160 else text[:157] + "..."


def _failure(table: str | None, code: str, exc: Exception) -> dict[str, str]:
    return {
        "table": table or "",
        "code": code,
        "message": "只读画像未完成",
        "error_type": type(exc).__name__,
    }


def _issue(
    code: str,
    title: str,
    detail: str,
    *,
    severity: str = "warning",
    table: str | None = None,
) -> dict[str, Any]:
    issue: dict[str, Any] = {
        "code": code,
        "title": title,
        "detail": detail,
        "severity": severity,
        "automatic": True,
    }
    if table:
        issue["table"] = table
    return issue


def _empty_preanalysis(*, failures: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "generated_by": "deterministic_database_value_preflight",
        "summary_code": "database_value_preflight",
        "summary_facts": {
            "profiled_tables": 0,
            "profiled_columns": 0,
            "status": "error",
            "partial": True,
        },
        "requires_query_verification": True,
        "read_only": True,
        "relation_index": {
            "relations": [],
            "relations_loaded": 0,
            "relations_total": None,
            "relations_total_at_least": 0,
            "complete": False,
            "truncated": False,
            "unread_relations_at_least": 0,
        },
        "shape": {
            "tables": 0,
            "profiled_tables": 0,
            "columns": 0,
            "sampled_rows": 0,
            "rows_are_sampled": True,
        },
        "tables": [],
        "candidate_roles": [],
        "candidate_grain": [],
        "relationship_evidence": [],
        "partial_failures": failures,
    }
