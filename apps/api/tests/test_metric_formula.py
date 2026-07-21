"""Contracts for the safe Decimal metric-formula core."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.metric_formula import (
    MAX_FORMULA_COLUMNS,
    MAX_FORMULA_DEPTH,
    aggregate_decimal_column,
    aggregate_decimal_metric,
    apply_metric_formula,
    canonical_decimal_string,
    evaluate_metric_expression,
    metric_formula_columns,
    parse_explicit_metric_formula,
    validate_metric_expression,
    validate_metric_formula_action,
)


def _action(expression: dict, *, output_column: str = "net_amount") -> dict:
    return {
        "kind": "metric_formula",
        "output_column": output_column,
        "expression": expression,
        "evaluation_order": "row_then_aggregate",
        "null_policy": "propagate",
        "divide_by_zero": "error",
    }


def test_decimal_contract_is_canonical_and_strict():
    assert canonical_decimal_string(Decimal("-0.000")) == "0"
    assert canonical_decimal_string("001.2300") == "1.23"
    assert canonical_decimal_string("1e2") == "100"

    with pytest.raises(ValueError, match="规范十进制字符串"):
        validate_metric_expression({"op": "decimal", "value": "1.00"})
    with pytest.raises(ValueError, match="额外字段"):
        validate_metric_expression({"op": "decimal", "value": "1", "unit": "CNY"})
    with pytest.raises(ValueError, match="字段不完整"):
        validate_metric_expression({"op": "add", "left": {"op": "decimal", "value": "1"}})
    with pytest.raises(ValueError, match="安全幅度"):
        canonical_decimal_string("1e28")
    with pytest.raises(ValueError, match="最多支持 18 位小数"):
        canonical_decimal_string("0.0000000000000000001")


def test_formula_contract_enforces_limits_and_row_then_aggregate():
    expression: dict = {"op": "column", "name": "amount"}
    for _ in range(MAX_FORMULA_DEPTH):
        expression = {"op": "negate", "operand": expression}
    with pytest.raises(ValueError, match="最多支持 8 层"):
        validate_metric_expression(expression)

    column_nodes = [
        {"op": "column", "name": f"c{index}"}
        for index in range(MAX_FORMULA_COLUMNS + 1)
    ]
    while len(column_nodes) > 1:
        next_level = []
        for index in range(0, len(column_nodes), 2):
            if index + 1 == len(column_nodes):
                next_level.append(column_nodes[index])
            else:
                next_level.append(
                    {
                        "op": "add",
                        "left": column_nodes[index],
                        "right": column_nodes[index + 1],
                    }
                )
        column_nodes = next_level
    columns_expression = column_nodes[0]
    with pytest.raises(ValueError, match="最多引用 8 个字段"):
        validate_metric_expression(columns_expression)

    wrong_order = _action({"op": "column", "name": "amount"})
    wrong_order["evaluation_order"] = "aggregate_then_row"
    with pytest.raises(ValueError, match="先逐行计算"):
        validate_metric_formula_action(wrong_order)
    with pytest.raises(ValueError, match="额外字段"):
        validate_metric_formula_action({**_action({"op": "column", "name": "amount"}), "code": "x"})


def test_explicit_parser_preserves_precedence_and_rejects_prose_or_collisions():
    action = parse_explicit_metric_formula(
        "net_amount = gross_amount - refund_amount * 1.25",
        known_numeric_columns=["gross_amount", "refund_amount"],
        existing_columns=["gross_amount", "refund_amount"],
    )
    assert action is not None
    assert action["evaluation_order"] == "row_then_aggregate"
    assert metric_formula_columns(action) == ("gross_amount", "refund_amount")
    assert evaluate_metric_expression(
        action["expression"],
        {"gross_amount": "100", "refund_amount": "8"},
        null_policy="propagate",
        divide_by_zero="error",
    ) == Decimal("90.00")

    assert (
        parse_explicit_metric_formula(
            "请按 gross_amount 减 refund_amount 算净收入",
            known_numeric_columns=["gross_amount", "refund_amount"],
            existing_columns=["gross_amount", "refund_amount"],
        )
        is None
    )
    assert (
        parse_explicit_metric_formula(
            "gross_amount = gross_amount - refund_amount",
            known_numeric_columns=["gross_amount", "refund_amount"],
            existing_columns=["gross_amount", "refund_amount"],
        )
        is None
    )
    assert (
        parse_explicit_metric_formula(
            "net_amount = gross_amount - unknown_amount",
            known_numeric_columns=["gross_amount", "refund_amount"],
            existing_columns=["gross_amount", "refund_amount", "unknown_amount"],
        )
        is None
    )


def test_interpreter_applies_null_and_divide_by_zero_policies_without_eval():
    subtract = {
        "op": "subtract",
        "left": {"op": "column", "name": "gross"},
        "right": {"op": "column", "name": "refund"},
    }
    assert (
        evaluate_metric_expression(
            subtract,
            {"gross": None, "refund": "2"},
            null_policy="propagate",
            divide_by_zero="error",
        )
        is None
    )
    assert evaluate_metric_expression(
        subtract,
        {"gross": None, "refund": "2"},
        null_policy="zero",
        divide_by_zero="error",
    ) == Decimal("-2")
    with pytest.raises(ValueError, match="包含空值"):
        evaluate_metric_expression(
            subtract,
            {"gross": None, "refund": "2"},
            null_policy="error",
            divide_by_zero="error",
        )

    divide = {
        "op": "divide",
        "left": {"op": "column", "name": "gross"},
        "right": {"op": "column", "name": "orders"},
    }
    assert (
        evaluate_metric_expression(
            divide,
            {"gross": "10", "orders": 0},
            null_policy="propagate",
            divide_by_zero="null",
        )
        is None
    )
    with pytest.raises(ValueError, match="除零"):
        evaluate_metric_expression(
            divide,
            {"gross": "10", "orders": 0},
            null_policy="propagate",
            divide_by_zero="error",
        )

    assert canonical_decimal_string(
        evaluate_metric_expression(
            {
                "op": "divide",
                "left": {"op": "decimal", "value": "1"},
                "right": {"op": "decimal", "value": "3"},
            },
            {},
            null_policy="propagate",
            divide_by_zero="error",
        )
    ) == "0.333333333333333333"
    with pytest.raises(ValueError, match="安全幅度"):
        evaluate_metric_expression(
            {
                "op": "multiply",
                "left": {"op": "column", "name": "amount"},
                "right": {"op": "decimal", "value": "2"},
            },
            {"amount": "9000000000000000000000000000"},
            null_policy="propagate",
            divide_by_zero="error",
        )


def test_apply_formula_preserves_rows_and_emits_replayable_evidence():
    action = _action(
        {
            "op": "subtract",
            "left": {"op": "column", "name": "gross"},
            "right": {"op": "column", "name": "refund"},
        }
    )
    rows = [
        {"order": "a", "gross": "10.50", "refund": "0.5"},
        {"order": "b", "gross": "20", "refund": None},
    ]
    output, evidence = apply_metric_formula(
        rows,
        rule_key="net_revenue",
        rule_value="net_amount = gross - refund",
        action=action,
    )
    assert rows[0].get("net_amount") is None
    assert output == [
        {**rows[0], "net_amount": "10"},
        {**rows[1], "net_amount": None},
    ]
    assert evidence["before_rows"] == evidence["after_rows"] == 2
    assert evidence["column"] == "net_amount"
    assert evidence["operator"] is None
    assert evidence["values"] == []
    assert evidence["excluded_rows"] == 0
    assert evidence["computed_rows"] == 1
    assert evidence["null_rows"] == 1
    assert len(evidence["formula_hash"]) == 64
    assert len(evidence["input_hash"]) == len(evidence["output_hash"]) == 64
    assert evidence["input_hash"] != evidence["output_hash"]

    with pytest.raises(ValueError, match="输出字段已存在"):
        apply_metric_formula(
            [{"gross": 1, "refund": 0, "net_amount": 1}],
            rule_key="net_revenue",
            rule_value="net_amount = gross - refund",
            action=action,
        )


def test_decimal_aggregation_is_deterministic_and_explicit_about_nulls():
    rows = [{"net": "0.1"}, {"net": "0.2"}, {"net": None}]
    propagated, propagated_evidence = aggregate_decimal_column(
        rows,
        column="net",
        operation="sum",
        null_policy="propagate",
    )
    assert propagated is None
    assert propagated_evidence["null_rows"] == 1

    total, evidence = aggregate_decimal_column(
        rows,
        column="net",
        operation="sum",
        null_policy="zero",
    )
    average, _ = aggregate_decimal_column(
        rows,
        column="net",
        operation="average",
        null_policy="zero",
    )
    assert total == "0.3"
    assert average == "0.1"
    assert evidence["input_rows"] == evidence["value_rows"] == 3
    assert len(evidence["input_hash"]) == 64

    with pytest.raises(ValueError, match="包含空值"):
        aggregate_decimal_column(
            rows,
            column="net",
            operation="sum",
            null_policy="error",
        )


def test_grouped_decimal_aggregation_has_stable_order_strings_and_limit_evidence():
    rows = [
        {"category": "b", "net": "0.2"},
        {"category": "a", "net": "0.1"},
        {"category": "a", "net": "0.2"},
    ]
    output, evidence = aggregate_decimal_metric(
        rows,
        value_column="net",
        operation="sum",
        group_by=["category"],
        output_column="net_total",
        limit=1,
        null_policy="zero",
    )
    assert output == [{"category": "a", "net_total": "0.3"}]
    assert evidence["total_groups"] == 2
    assert evidence["returned_groups"] == 1
    assert evidence["truncated"] is True
    assert len(evidence["input_hash"]) == len(evidence["output_hash"]) == 64

    means, _ = aggregate_decimal_metric(
        rows,
        value_column="net",
        operation="mean",
        group_by=["category"],
        output_column="net_mean",
        null_policy="zero",
    )
    assert means == [
        {"category": "a", "net_mean": "0.15"},
        {"category": "b", "net_mean": "0.2"},
    ]
