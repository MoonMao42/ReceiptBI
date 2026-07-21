"""Deterministic regression contracts learned from confirmed project analyses."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any

from app.services.metric_lineage import prove_metric_application_lineage


def normalize_query_key(query: str) -> str:
    normalized = unicodedata.normalize("NFKC", query).casefold()
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", normalized)


def _canonical_rows_hash(rows: list[dict[str, Any]]) -> str:
    serialized = sorted(
        json.dumps(row, sort_keys=True, ensure_ascii=False, default=str) for row in rows
    )
    return hashlib.sha256("\n".join(serialized).encode()).hexdigest()


def _latest_validation(tool_history: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next(
        (
            item
            for item in reversed(tool_history)
            if item.get("kind") == "validation" and isinstance(item.get("profile"), dict)
        ),
        None,
    )


def _metric_application_consumed(
    tool_history: list[dict[str, Any]],
    application: dict[str, Any],
) -> bool:
    final_validation = _latest_validation(tool_history)
    final_result = str((final_validation or {}).get("result_name") or "")
    if not final_result:
        return False
    final_columns = {
        str(column)
        for column in ((final_validation or {}).get("profile") or {}).get("columns") or []
    }
    validation_index = next(
        (
            index
            for index in range(len(tool_history) - 1, -1, -1)
            if tool_history[index] is final_validation
        ),
        len(tool_history) - 1,
    )
    return (
        prove_metric_application_lineage(
            tool_history[: validation_index + 1],
            application,
            final_result=final_result,
            final_columns=final_columns,
        )
        is not None
    )


def _relationship_profiles(tool_history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    profiles: dict[tuple[str, str, str], dict[str, Any]] = {}
    order: list[tuple[str, str, str]] = []
    for item in tool_history:
        if item.get("kind") not in {
            "join",
            "relationship_validation",
            "relationship_application",
        }:
            continue
        profile = item.get("profile") or {}
        left_key = str(profile.get("left_key") or item.get("left_key") or "")
        right_key = str(profile.get("right_key") or item.get("right_key") or "")
        relationship_key = str(
            item.get("relationship_key") or item.get("candidate_relationship_key") or ""
        )
        definition_hash = str(item.get("definition_hash") or "")
        if relationship_key:
            # The semantic key survives monthly source replacement, while the
            # definition hash can legitimately change with a table schema
            # signature. Keep one profile for that stable relationship identity.
            signature = ("relationship_key", relationship_key, "semantic")
        elif left_key and right_key:
            signature = (left_key, right_key, "legacy")
        else:
            continue
        source_refs = [
            {
                "source_logical_name": str(ref.get("source_logical_name") or ""),
                "source_kind": str(ref.get("source_kind") or ""),
            }
            for ref in item.get("source_refs") or []
            if isinstance(ref, dict)
        ]
        previous = profiles.get(signature)
        if signature not in profiles:
            order.append(signature)
        profiles[signature] = {
            "relationship_key": relationship_key or None,
            "definition_hash": definition_hash or None,
            # A later validation call has fresher coverage metrics but no source_refs;
            # retain the source binding already proven by the guarded join.
            "source_refs": sorted(
                source_refs or ((previous or {}).get("source_refs") or []),
                key=lambda source: (
                    source["source_kind"],
                    source["source_logical_name"],
                ),
            ),
            "left_key": left_key,
            "right_key": right_key,
            "normalization": profile.get("normalization") or "exact",
            "cardinality": profile.get("cardinality"),
            "left_match_rate": float(profile.get("left_match_rate") or 0),
            "expansion_ratio": float(profile.get("expansion_ratio") or 1),
        }
    return [profiles[signature] for signature in order]


def _logical_source_signature(profile: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    return tuple(
        sorted(
            {
                (
                    str(ref.get("source_logical_name") or ""),
                    str(ref.get("source_kind") or ""),
                )
                for ref in profile.get("source_refs") or []
                if isinstance(ref, dict)
                and ref.get("source_logical_name")
                and ref.get("source_kind")
            }
        )
    )


def _relationship_matches(
    current: dict[str, Any],
    expected: dict[str, Any],
) -> bool:
    expected_relationship_key = str(expected.get("relationship_key") or "")
    if not expected_relationship_key:
        return current.get("left_key") == expected.get("left_key") and current.get(
            "right_key"
        ) == expected.get("right_key")
    if current.get("relationship_key") != expected_relationship_key:
        return False
    current_definition_hash = str(current.get("definition_hash") or "")
    expected_definition_hash = str(expected.get("definition_hash") or "")
    if (
        current_definition_hash
        and expected_definition_hash
        and current_definition_hash == expected_definition_hash
    ):
        return True

    # Relationship definitions include full-table schema signatures. A new
    # monthly file can therefore change the hash even when the durable semantic
    # relationship itself is unchanged and has been revalidated. Only accept
    # that benign drift when both endpoint columns and logical source bindings
    # still identify the same relationship.
    current_columns = sorted(
        (str(current.get("left_key") or ""), str(current.get("right_key") or ""))
    )
    expected_columns = sorted(
        (str(expected.get("left_key") or ""), str(expected.get("right_key") or ""))
    )
    current_sources = _logical_source_signature(current)
    expected_sources = _logical_source_signature(expected)
    return (
        all(current_columns)
        and current_columns == expected_columns
        and bool(current_sources)
        and current_sources == expected_sources
    )


def _rule_applications(tool_history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract complete, deterministic business-rule execution evidence."""

    applications: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, str, tuple[str, ...], str]] = set()
    for item in reversed(tool_history):
        if item.get("kind") != "business_rule_application":
            continue
        rule_key = str(item.get("rule_key") or "").strip()
        rule_value = str(item.get("rule_value") or "").strip()
        action_kind = str(item.get("action_kind") or "value_filter").strip()
        column = str(item.get("column") or "").strip()
        operator = str(item.get("operator") or "").strip()
        values = sorted({str(value) for value in item.get("values") or []})
        input_hash = str(item.get("input_hash") or "")
        output_hash = str(item.get("output_hash") or "")
        definition_hash = str(item.get("definition_hash") or "")
        is_filter = action_kind == "value_filter"
        if (
            not rule_key
            or not rule_value
            or not column
            or action_kind not in {
                "value_filter",
                "identity",
                "metric_column",
                "metric_formula",
            }
            or (is_filter and operator not in {"include", "exclude"})
            or (is_filter and not values)
            or re.fullmatch(r"[0-9a-f]{64}", input_hash) is None
            or re.fullmatch(r"[0-9a-f]{64}", output_hash) is None
        ):
            continue
        try:
            before_rows = int(item.get("before_rows"))
            after_rows = int(item.get("after_rows"))
            excluded_rows = int(item.get("excluded_rows"))
        except (TypeError, ValueError):
            continue
        signature = (
            rule_key,
            rule_value,
            action_kind,
            column,
            operator,
            tuple(values),
            definition_hash,
        )
        if signature in seen:
            continue
        seen.add(signature)
        application_contract = {
                "rule_key": rule_key,
                "rule_value": rule_value,
                "action_kind": action_kind,
                "column": column,
                "operator": operator or None,
                "values": values,
                "before_rows": before_rows,
                "after_rows": after_rows,
                "excluded_rows": excluded_rows,
                "input_hash": input_hash,
                "output_hash": output_hash,
                "definition_hash": definition_hash or None,
                "metric_consumed": (
                    _metric_application_consumed(tool_history, item)
                    if action_kind in {"metric_column", "metric_formula"}
                    else None
                ),
            }
        if action_kind == "metric_formula":
            formula_hash = str(item.get("formula_hash") or "")
            if re.fullmatch(r"[0-9a-f]{64}", formula_hash) is None:
                continue
            application_contract["formula_hash"] = formula_hash
        applications.append(application_contract)
    return list(reversed(applications))


def _rule_signature(
    item: dict[str, Any],
) -> tuple[str, str, str, str, str, tuple[str, ...]]:
    return (
        str(item.get("rule_key") or ""),
        str(item.get("rule_value") or ""),
        str(item.get("action_kind") or "value_filter"),
        str(item.get("column") or ""),
        str(item.get("operator") or ""),
        tuple(sorted(str(value) for value in item.get("values") or [])),
    )


def build_golden_contract(
    *,
    query: str,
    confirmed_knowledge: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    tool_history: list[dict[str, Any]],
    result_rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Capture stable structure and evidence, while allowing future business values to change."""

    validation = _latest_validation(tool_history)
    if validation is None:
        return None
    profile = validation["profile"]
    source_contracts = []
    for source in sources:
        schema_columns = [
            str(column.get("name"))
            for column in (source.get("profile") or {}).get("schema", {}).get("columns", [])
            if column.get("name")
        ]
        source_contracts.append(
            {
                "logical_name": source.get("view_name")
                or source.get("connection_name")
                or source.get("name"),
                "fingerprint": source.get("fingerprint"),
                "schema_columns": sorted(schema_columns),
            }
        )
    return {
        "version": 1,
        "query": query,
        "query_key": normalize_query_key(query),
        "confirmed_knowledge": {
            str(item.get("key")): str(item.get("value"))
            for item in confirmed_knowledge
            if item.get("key")
            and item.get("value") is not None
            and item.get("type") != "verified_query"
        },
        "sources": source_contracts,
        "result": {
            "required_columns": sorted(str(item) for item in profile.get("columns") or []),
            "key_columns": sorted(str(item) for item in (profile.get("keys") or {})),
            "numeric_columns": sorted(str(item) for item in (profile.get("numeric") or {})),
            "must_not_be_truncated": True,
            "same_input_rows_hash": _canonical_rows_hash(result_rows),
        },
        "relationships": [
            {
                **profile,
                "minimum_left_match_rate": max(
                    0.5, round(float(profile.get("left_match_rate") or 0) - 0.1, 6)
                ),
                "maximum_expansion_ratio": max(
                    1.0, round(float(profile.get("expansion_ratio") or 1) * 1.5, 6)
                ),
            }
            for profile in _relationship_profiles(tool_history)
        ],
        "required_rule_applications": _rule_applications(tool_history),
    }


def find_matching_contract(scenarios: list[dict[str, Any]], query: str) -> dict[str, Any] | None:
    query_key = normalize_query_key(query)
    return next(
        (
            item
            for item in reversed(scenarios)
            if item.get("version") == 1 and item.get("query_key") == query_key
        ),
        None,
    )


def evaluate_golden_contract(
    contract: dict[str, Any],
    *,
    confirmed_knowledge: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    tool_history: list[dict[str, Any]],
    result_rows: list[dict[str, Any]],
) -> list[str]:
    """Return user-safe regression failures; an empty list means the contract still holds."""

    failures: list[str] = []
    knowledge = {
        str(item.get("key")): str(item.get("value"))
        for item in confirmed_knowledge
        if item.get("key") and item.get("value") is not None
    }
    for key, value in (contract.get("confirmed_knowledge") or {}).items():
        if knowledge.get(str(key)) != str(value):
            failures.append(f"已确认口径“{key}”缺失或发生冲突")

    current_rule_applications = _rule_applications(tool_history)
    for expected in contract.get("required_rule_applications") or []:
        expected_signature = _rule_signature(expected)
        expected_definition_hash = str(expected.get("definition_hash") or "")
        expected_formula_hash = str(expected.get("formula_hash") or "")
        matching_applications = [
            item
            for item in current_rule_applications
            if _rule_signature(item) == expected_signature
        ]
        current = next(
            (
                item
                for item in reversed(matching_applications)
                if not expected_definition_hash
                or str(item.get("definition_hash") or "") == expected_definition_hash
                if not expected_formula_hash
                or str(item.get("formula_hash") or "") == expected_formula_hash
            ),
            None,
        )
        rule_key = str(expected.get("rule_key") or "业务规则")
        if current is None:
            if matching_applications and expected_definition_hash:
                failures.append(f"已确认规则“{rule_key}”使用了不同的规则版本")
            else:
                failures.append(f"已确认规则“{rule_key}”未在本次计算中执行")
            continue
        before_rows = int(current.get("before_rows") or 0)
        after_rows = int(current.get("after_rows") or 0)
        excluded_rows = int(current.get("excluded_rows") or 0)
        action_kind = str(current.get("action_kind") or "value_filter")
        if action_kind == "value_filter" and (
            before_rows < after_rows or excluded_rows != before_rows - after_rows
        ):
            failures.append(f"已确认规则“{rule_key}”的执行行数证据不一致")
        if (
            action_kind == "value_filter"
            and excluded_rows > 0
            and current.get("input_hash") == current.get("output_hash")
        ):
            failures.append(f"已确认规则“{rule_key}”声称排除了记录但结果没有变化")
        if action_kind in {"identity", "metric_column"} and (
            before_rows != after_rows
            or excluded_rows != 0
            or current.get("input_hash") != current.get("output_hash")
        ):
            failures.append(f"已确认规则“{rule_key}”的无损应用证据不一致")
        if action_kind == "metric_formula" and (
            before_rows != after_rows
            or excluded_rows != 0
            or current.get("input_hash") == current.get("output_hash")
        ):
            failures.append(f"已确认公式“{rule_key}”的派生列证据不一致")
        if action_kind in {"metric_column", "metric_formula"} and not current.get(
            "metric_consumed"
        ):
            failures.append(f"已确认指标“{rule_key}”没有用于本次最终汇总")
        if current.get("input_hash") == expected.get("input_hash") and current.get(
            "output_hash"
        ) != expected.get("output_hash"):
            failures.append(f"已确认规则“{rule_key}”对相同输入产生了不同结果")

    validation = _latest_validation(tool_history)
    if validation is None:
        failures.append("最终结果没有经过验证")
        return failures
    profile = validation["profile"]
    current_columns = {str(item) for item in profile.get("columns") or []}
    expected_result = contract.get("result") or {}
    missing_columns = set(expected_result.get("required_columns") or []) - current_columns
    if missing_columns:
        failures.append(f"最终结果缺少字段：{'、'.join(sorted(missing_columns))}")
    if expected_result.get("must_not_be_truncated") and profile.get("truncated"):
        failures.append("最终结果被截断")

    current_relationships = _relationship_profiles(tool_history)
    for expected in contract.get("relationships") or []:
        current = next(
            (
                item
                for item in current_relationships
                if _relationship_matches(item, expected)
            ),
            None,
        )
        if current is None:
            failures.append(
                f"缺少关联验证：{expected.get('left_key')} ↔ {expected.get('right_key')}"
            )
            continue
        if float(current.get("left_match_rate") or 0) < float(
            expected.get("minimum_left_match_rate") or 0
        ):
            failures.append(
                f"关联覆盖率低于已确认基线：{expected.get('left_key')} ↔ {expected.get('right_key')}"
            )
        if float(current.get("expansion_ratio") or 1) > float(
            expected.get("maximum_expansion_ratio") or 1
        ):
            failures.append(
                f"关联后的行数膨胀超过已确认范围：{expected.get('left_key')} ↔ {expected.get('right_key')}"
            )

    expected_sources = {
        str(item.get("logical_name")): item for item in contract.get("sources") or []
    }
    current_sources = {
        str(item.get("view_name") or item.get("connection_name") or item.get("name")): item
        for item in sources
    }
    same_inputs = bool(expected_sources) and set(expected_sources) == set(current_sources)
    if same_inputs:
        for name, expected in expected_sources.items():
            fingerprint = expected.get("fingerprint")
            if not fingerprint or current_sources[name].get("fingerprint") != fingerprint:
                same_inputs = False
                break
    if same_inputs and expected_result.get("same_input_rows_hash") != _canonical_rows_hash(
        result_rows
    ):
        failures.append("相同数据输入得到的结果与已确认结果不一致")
    return failures
