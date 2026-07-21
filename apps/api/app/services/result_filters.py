"""Deterministic row filters with auditable business-rule evidence."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Iterable
from typing import Any, Literal

from app.services.metric_formula import (
    metric_formula_columns,
    validate_metric_formula_action,
)

FilterOperator = Literal["include", "exclude"]

_REFUND_COLUMN_HINTS = ("refund", "return", "退款", "退货")
_NET_AMOUNT_HINTS = (
    "net_amount",
    "net amount",
    "net_revenue",
    "net revenue",
    "净额",
    "净收入",
    "退款后金额",
)
_NEGATIVE_REFUND_VALUES = {
    "0",
    "false",
    "n",
    "no",
    "否",
    "正常",
    "未退",
    "未退款",
    "无退款",
    "未发生退款",
}
_POSITIVE_REFUND_VALUES = {
    "1",
    "true",
    "y",
    "yes",
    "是",
    "已退",
    "已退款",
    "退款",
    "退货",
}

_BOOLEAN_TYPE_HINTS = ("bool", "boolean")
_DATETIME_TYPE_HINTS = ("date", "time", "timestamp", "datetime")
_NUMBER_TYPE_HINTS = (
    "int",
    "decimal",
    "numeric",
    "number",
    "float",
    "double",
    "real",
    "money",
)
_TEXT_TYPE_HINTS = ("char", "text", "string", "object", "category", "categorical")


def _rows_hash(rows: list[dict[str, Any]]) -> str:
    serialized = sorted(
        json.dumps(row, sort_keys=True, ensure_ascii=False, default=str) for row in rows
    )
    return hashlib.sha256("\n".join(serialized).encode()).hexdigest()


def _normalized_value(value: Any) -> str:
    return unicodedata.normalize("NFKC", str(value)).strip().casefold()


def _stable_observed_values(rows: list[dict[str, Any]], column: str) -> list[str]:
    by_normalized: dict[str, str] = {}
    for row in rows:
        raw = row.get(column)
        if raw is None or not str(raw).strip():
            continue
        normalized = _normalized_value(raw)
        by_normalized.setdefault(normalized, str(raw).strip())
    return [by_normalized[key] for key in sorted(by_normalized)]


def _is_refunded_value(value: str) -> bool:
    normalized = _normalized_value(value)
    if normalized in _NEGATIVE_REFUND_VALUES:
        return False
    if normalized in _POSITIVE_REFUND_VALUES:
        return True
    if normalized.startswith(("未", "无", "不", "not ", "no ")):
        return False
    return any(token in normalized for token in ("退款", "退货", "refunded", "returned"))


def canonical_data_type(raw_type: Any) -> Literal[
    "boolean", "number", "datetime", "text", "unknown"
]:
    """Map source-specific type names to the small stable semantic type set."""

    normalized = _normalized_value(raw_type)
    if any(hint in normalized for hint in _BOOLEAN_TYPE_HINTS):
        return "boolean"
    if any(hint in normalized for hint in _DATETIME_TYPE_HINTS):
        return "datetime"
    if any(hint in normalized for hint in _NUMBER_TYPE_HINTS):
        return "number"
    if any(hint in normalized for hint in _TEXT_TYPE_HINTS):
        return "text"
    return "unknown"


def stable_schema_signature(columns: Iterable[dict[str, Any]]) -> str:
    """Hash a table/view schema using names and canonical types, not source UUIDs."""

    normalized = sorted(
        [
            {
                "name": str(column.get("name") or "").strip(),
                "canonical_type": canonical_data_type(
                    column.get("type")
                    or column.get("dtype")
                    or column.get("data_type")
                    or "unknown"
                ),
            }
            for column in columns
            if str(column.get("name") or "").strip()
        ],
        key=lambda item: (item["name"], item["canonical_type"]),
    )
    return hashlib.sha256(
        json.dumps(
            normalized,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def stable_field_binding_candidates(
    source: dict[str, Any],
    action_column: str,
) -> list[dict[str, str]]:
    """Return schema-proven stable bindings for one action column.

    File sources expose one maintained logical view. Database connections may
    expose several tables/views, so callers must reject more than one candidate.
    """

    profile = source.get("profile")
    if not isinstance(profile, dict):
        profile = source.get("profile_data")
    if not isinstance(profile, dict):
        return []
    logical_name = str(
        profile.get("logical_name") or source.get("source_logical_name") or ""
    ).strip()
    source_kind = str(source.get("kind") or source.get("source_kind") or "").strip()
    if not logical_name or source_kind not in {"file", "connection"}:
        return []

    structures: list[tuple[str, list[dict[str, Any]]]] = []
    if source_kind == "file":
        schema = profile.get("schema")
        columns = schema.get("columns") if isinstance(schema, dict) else None
        if isinstance(columns, list) and columns:
            structures.append((logical_name, [item for item in columns if isinstance(item, dict)]))
    else:
        for table in profile.get("tables") or []:
            if not isinstance(table, dict):
                continue
            table_name = str(table.get("name") or "").strip()
            columns = table.get("columns")
            if table_name and isinstance(columns, list) and columns:
                structures.append(
                    (table_name, [item for item in columns if isinstance(item, dict)])
                )

    bindings: list[dict[str, str]] = []
    for table_or_view, columns in structures:
        matches = [
            column
            for column in columns
            if str(column.get("name") or "").strip() == action_column
        ]
        if len(matches) != 1:
            continue
        canonical_type = canonical_data_type(
            matches[0].get("type")
            or matches[0].get("dtype")
            or matches[0].get("data_type")
            or "unknown"
        )
        if canonical_type == "unknown":
            continue
        bindings.append(
            {
                "source_logical_name": logical_name,
                "source_kind": source_kind,
                "table_or_view": table_or_view,
                "action_column": action_column,
                "canonical_type": canonical_type,
                "schema_signature": stable_schema_signature(columns),
            }
        )
    return bindings


def revenue_refund_candidate_columns(rows: Iterable[dict[str, Any]]) -> list[str]:
    """Return every observed column that independently looks like a refund marker."""

    materialized = [dict(row) for row in rows]
    columns = sorted({str(key) for row in materialized for key in row})
    candidates: list[str] = []
    for column in columns:
        lowered = _normalized_value(column)
        if not any(hint in lowered for hint in _REFUND_COLUMN_HINTS):
            continue
        observed = _stable_observed_values(materialized, column)
        if any(_is_refunded_value(value) for value in observed):
            candidates.append(column)
    return candidates


def build_revenue_refund_option_strategies(
    rows: Iterable[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Derive executable refund-policy choices only from observed columns and values."""

    materialized = [dict(row) for row in rows]
    columns = sorted({str(key) for row in materialized for key in row})
    refund_candidates: list[tuple[int, str, list[str], list[str]]] = []
    candidate_columns = set(revenue_refund_candidate_columns(materialized))
    for column in columns:
        lowered = _normalized_value(column)
        if column not in candidate_columns:
            continue
        observed = _stable_observed_values(materialized, column)
        refunded = [value for value in observed if _is_refunded_value(value)]
        if not refunded:
            continue
        score = 2 if any(token in lowered for token in ("状态", "status", "flag", "是否")) else 1
        refund_candidates.append((score, column, observed, refunded))
    if not refund_candidates:
        return {}

    _score, refund_column, observed_values, refunded_values = sorted(
        refund_candidates,
        key=lambda item: (-item[0], item[1]),
    )[0]

    def definition(option: str, action: dict[str, Any]) -> dict[str, Any]:
        return {
            "version": 1,
            "kind": "business_rule_strategy",
            "rule_key": "revenue_refund_policy",
            "selected_option": option,
            "action": action,
        }

    strategies = {
        "扣除退款": definition(
            "扣除退款",
            {
                "kind": "value_filter",
                "column": refund_column,
                "operator": "exclude",
                "values": refunded_values,
                "observed_values": observed_values,
            },
        ),
        "保留退款订单": definition(
            "保留退款订单",
            {
                "kind": "identity",
                "column": refund_column,
                "observed_values": observed_values,
            },
        ),
    }
    net_columns = [
        column
        for column in columns
        if any(hint in _normalized_value(column) for hint in _NET_AMOUNT_HINTS)
    ]
    if len(net_columns) == 1:
        strategies["按现有净额字段"] = definition(
            "按现有净额字段",
            {"kind": "metric_column", "column": net_columns[0]},
        )
    return strategies


def validate_business_rule_strategy_definition(
    definition: Any,
    *,
    expected_key: str,
    expected_value: str,
) -> dict[str, Any]:
    """Validate the small internal strategy schema before it becomes executable."""

    if not isinstance(definition, dict):
        raise ValueError("已确认口径缺少可执行策略")
    if (
        definition.get("version") != 1
        or definition.get("kind") != "business_rule_strategy"
        or str(definition.get("rule_key") or "") != expected_key
        or str(definition.get("selected_option") or "") != expected_value
    ):
        raise ValueError("已确认口径的可执行策略与当前定义不一致")
    action = definition.get("action")
    if not isinstance(action, dict):
        raise ValueError("已确认口径缺少可执行动作")
    action_kind = str(action.get("kind") or "")
    column = str(action.get("column") or "").strip()
    if action_kind == "value_filter":
        values = action.get("values")
        observed = action.get("observed_values")
        if (
            not column
            or action.get("operator") not in {"include", "exclude"}
            or not isinstance(values, list)
            or not values
            or not isinstance(observed, list)
            or not observed
        ):
            raise ValueError("已确认口径的筛选策略不完整")
    elif action_kind == "identity":
        if not column or not isinstance(action.get("observed_values"), list):
            raise ValueError("已确认口径的保留策略不完整")
    elif action_kind == "metric_column":
        if not column:
            raise ValueError("已确认口径的净额字段策略不完整")
    elif action_kind == "metric_formula":
        action = validate_metric_formula_action(action)
        columns = metric_formula_columns(action)
        if not columns:
            raise ValueError("已确认口径的指标公式没有引用来源字段")
    else:
        raise ValueError("已确认口径包含不支持的执行策略")
    applies_to = definition.get("applies_to")
    if action_kind == "metric_formula" and applies_to is None:
        raise ValueError("已确认口径缺少公式字段的数据源绑定")
    if applies_to is not None:
        if action_kind == "metric_formula":
            if not isinstance(applies_to, list) or len(applies_to) != len(columns):
                raise ValueError("已确认口径缺少公式字段的数据源绑定")
            bindings_by_column: dict[str, dict[str, Any]] = {}
            for raw_binding in applies_to:
                if not isinstance(raw_binding, dict):
                    raise ValueError("已确认口径缺少有效的数据源范围")
                binding_column = str(raw_binding.get("action_column") or "")
                _validate_stable_binding(raw_binding, expected_column=binding_column)
                if raw_binding.get("canonical_type") != "number":
                    raise ValueError("指标公式只能绑定已确认的数值字段")
                if binding_column in bindings_by_column:
                    raise ValueError("指标公式字段存在重复的数据源绑定")
                bindings_by_column[binding_column] = raw_binding
            if set(bindings_by_column) != set(columns):
                raise ValueError("指标公式字段与数据源绑定不一致")
        else:
            if not isinstance(applies_to, dict):
                raise ValueError("已确认口径缺少有效的数据源范围")
            _validate_stable_binding(applies_to, expected_column=column)
    return dict(definition)


def _validate_stable_binding(
    binding: dict[str, Any],
    *,
    expected_column: str,
) -> None:
    expected_fields = {
        "source_logical_name",
        "source_kind",
        "table_or_view",
        "action_column",
        "canonical_type",
        "schema_signature",
    }
    if set(binding) != expected_fields:
        raise ValueError("已确认口径的数据源范围不是稳定的逻辑字段绑定")
    schema_signature = str(binding.get("schema_signature") or "")
    if (
        not str(binding.get("source_logical_name") or "").strip()
        or binding.get("source_kind") not in {"file", "connection"}
        or not str(binding.get("table_or_view") or "").strip()
        or str(binding.get("action_column") or "") != expected_column
        or binding.get("canonical_type") not in {"boolean", "number", "datetime", "text"}
        or len(schema_signature) != 64
        or any(character not in "0123456789abcdef" for character in schema_signature)
    ):
        raise ValueError("已确认口径缺少有效的数据源字段绑定")


def _resolve_stable_source_binding(
    binding: dict[str, Any],
    *,
    source_refs: Iterable[dict[str, Any]],
    source_catalog: Iterable[dict[str, Any]],
) -> None:
    catalog = [dict(item) for item in source_catalog if isinstance(item, dict)]
    logical_name = str(binding["source_logical_name"])
    source_kind = str(binding["source_kind"])
    matching_sources = []
    for source in catalog:
        profile = source.get("profile")
        if not isinstance(profile, dict):
            profile = source.get("profile_data")
        if not isinstance(profile, dict):
            continue
        if (
            str(profile.get("logical_name") or "") == logical_name
            and str(source.get("kind") or source.get("source_kind") or "") == source_kind
            and str(source.get("status") or "") != "superseded"
            and profile.get("is_current") is not False
        ):
            matching_sources.append(source)
    if len(matching_sources) != 1:
        raise ValueError("找不到这条已确认口径绑定的唯一当前数据源")
    current_source = matching_sources[0]
    current_source_id = str(current_source.get("id") or current_source.get("source_id") or "")
    has_matching_ref = False
    for ref in source_refs:
        if not isinstance(ref, dict):
            continue
        ref_id = str(ref.get("source_id") or "")
        ref_logical_name = str(ref.get("source_logical_name") or "")
        ref_kind = str(ref.get("source_kind") or "")
        if (ref_logical_name == logical_name and ref_kind == source_kind) or (
            current_source_id and ref_id == current_source_id
        ):
            has_matching_ref = True
            break
    if not has_matching_ref:
        raise ValueError("当前结果的来源角色与这条已确认口径不一致")

    candidates = stable_field_binding_candidates(
        current_source,
        str(binding["action_column"]),
    )
    exact = [candidate for candidate in candidates if candidate == binding]
    if len(exact) != 1:
        raise ValueError("这条已确认口径绑定的数据源字段或结构已经变化")


def resolve_confirmed_rule_strategy(
    confirmed: dict[str, Any],
    rows: Iterable[dict[str, Any]],
    *,
    proposed_column: str | None = None,
    proposed_operator: FilterOperator | None = None,
    proposed_values: Iterable[str] | None = None,
    source_refs: Iterable[dict[str, Any]] | None = None,
    source_catalog: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resolve a confirmed strategy and reject model-authored execution parameters."""

    materialized = [dict(row) for row in rows]
    key = str(confirmed.get("key") or "").strip()
    value = str(confirmed.get("value") or "").strip()
    definition = confirmed.get("definition")
    if definition is None and key == "revenue_refund_policy":
        # Compatibility for old project knowledge: derive from current rows, never from
        # model-selected fields. If the current data does not prove a strategy, fail closed.
        definition = build_revenue_refund_option_strategies(materialized).get(value)
    strategy = validate_business_rule_strategy_definition(
        definition,
        expected_key=key,
        expected_value=value,
    )
    applies_to = strategy.get("applies_to")
    if isinstance(applies_to, (dict, list)):
        if source_catalog is None:
            raise ValueError("无法核对这条已确认口径绑定的当前数据源结构")
        bindings = applies_to if isinstance(applies_to, list) else [applies_to]
        for binding in bindings:
            _resolve_stable_source_binding(
                binding,
                source_refs=source_refs or [],
                source_catalog=source_catalog,
            )
    action = strategy["action"]
    action_kind = str(action["kind"])
    required_columns = (
        metric_formula_columns(action)
        if action_kind == "metric_formula"
        else (str(action["column"]),)
    )
    missing_columns = [
        column
        for column in required_columns
        if not materialized or not any(column in row for row in materialized)
    ]
    if missing_columns:
        raise ValueError("当前结果缺少已确认策略要求的字段: " + "、".join(missing_columns))
    action_column = required_columns[0]
    if action_kind == "value_filter":
        expected_values = sorted(_normalized_value(item) for item in action["values"])
        proposed = sorted(
            _normalized_value(item) for item in (proposed_values or []) if str(item).strip()
        )
        has_model_override = any(
            (
                bool(proposed_column),
                proposed_operator is not None,
                bool(proposed),
            )
        )
        if has_model_override and (
            proposed_column != action_column
            or proposed_operator != action["operator"]
            or proposed != expected_values
        ):
            raise ValueError("调用参数与已确认策略不一致，不能由模型改写筛选条件")
        current_values = {
            _normalized_value(value)
            for value in _stable_observed_values(materialized, action_column)
        }
        known_values = {_normalized_value(value) for value in action["observed_values"]}
        if not current_values:
            raise ValueError("退款字段没有可核对的实际值")
        if not current_values.issubset(known_values):
            raise ValueError("退款字段出现未确认的新值，需要重新核对业务口径")
    elif any(
        (
            bool(proposed_column),
            proposed_operator is not None,
            bool(list(proposed_values or [])),
        )
    ):
        raise ValueError("该已确认策略不接受模型提供筛选参数")
    return strategy


def apply_value_filter(
    rows: Iterable[dict[str, Any]],
    *,
    rule_key: str,
    rule_value: str,
    column: str,
    operator: FilterOperator,
    values: Iterable[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Apply an exact normalized include/exclude rule without mutating input rows.

    The returned evidence is designed to be appended to an analysis tool history and
    captured by a golden regression contract. It records both row counts and canonical
    hashes, so a later run cannot satisfy the contract by merely retaining the rule text.
    """

    key = rule_key.strip()
    selected_rule_value = rule_value.strip()
    selected_column = column.strip()
    if not key or not selected_rule_value or not selected_column:
        raise ValueError("规则标识、规则值和字段名不能为空")
    if operator not in {"include", "exclude"}:
        raise ValueError(f"不支持的筛选方式: {operator}")

    materialized = [dict(row) for row in rows]
    if materialized and not any(selected_column in row for row in materialized):
        raise ValueError(f"筛选字段不存在: {selected_column}")

    normalized_values = sorted({_normalized_value(value) for value in values if str(value).strip()})
    if not normalized_values:
        raise ValueError("筛选值不能为空")
    accepted = set(normalized_values)

    output: list[dict[str, Any]] = []
    matched_rows = 0
    missing_value_rows = 0
    for row in materialized:
        raw_value = row.get(selected_column)
        if raw_value is None or str(raw_value).strip() == "":
            missing_value_rows += 1
        matches = _normalized_value(raw_value) in accepted
        if matches:
            matched_rows += 1
        keep = matches if operator == "include" else not matches
        if keep:
            output.append(dict(row))

    before_rows = len(materialized)
    after_rows = len(output)
    evidence = {
        "kind": "business_rule_application",
        "rule_key": key,
        "rule_value": selected_rule_value,
        "column": selected_column,
        "operator": operator,
        "values": normalized_values,
        "before_rows": before_rows,
        "after_rows": after_rows,
        "excluded_rows": before_rows - after_rows,
        "matched_rows": matched_rows,
        "missing_value_rows": missing_value_rows,
        "input_hash": _rows_hash(materialized),
        "output_hash": _rows_hash(output),
    }
    return output, evidence
