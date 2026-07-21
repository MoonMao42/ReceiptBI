"""Golden metric rules must be consumed on the branch that becomes the final result."""

from copy import deepcopy

import pytest

from app.models.workspace import GoldenScenarioRuleApplicationContract
from app.services.golden_regression import build_golden_contract, evaluate_golden_contract


def _history() -> list[dict]:
    return [
        {
            "kind": "structured_query",
            "result_name": "orders",
        },
        {
            "kind": "business_rule_application",
            "rule_key": "metric:net_revenue",
            "rule_value": "净收入按实付金额减退款金额计算",
            "action_kind": "metric_formula",
            "column": "net_revenue",
            "operator": None,
            "values": [],
            "source_result": "orders",
            "result_name": "orders_with_net_revenue",
            "before_rows": 2,
            "after_rows": 2,
            "excluded_rows": 0,
            "input_hash": "a" * 64,
            "output_hash": "b" * 64,
            "definition_hash": "c" * 64,
            "formula_hash": "f" * 64,
        },
        {
            "kind": "aggregate",
            "source_result": "orders_with_net_revenue",
            "result_name": "revenue_summary",
            "operation": "sum",
            "value_column": "net_revenue",
            "output_column": "net_revenue",
            "required_metric_column": "net_revenue",
            "metric_input_column": "net_revenue",
            "metric_output_column": "net_revenue",
            "required_metric_definition_hash": "c" * 64,
            "metric_policy_satisfied": True,
            "numeric_backend": "decimal",
            "decimal_aggregate_evidence": {"kind": "decimal_aggregate"},
        },
        {
            "kind": "validation",
            "result_name": "revenue_summary",
            "result_hash": "d" * 64,
            "profile": {
                "columns": ["month", "net_revenue"],
                "keys": {"month": {}},
                "numeric": {"net_revenue": {}},
                "truncated": False,
            },
        },
    ]


def test_formula_metric_requires_aggregate_on_final_result_lineage():
    rows = [{"month": "2026-07", "net_revenue": "18.000000000000"}]
    history = _history()
    contract = build_golden_contract(
        query="按月计算净收入",
        confirmed_knowledge=[
            {"key": "metric:net_revenue", "value": "净收入按实付金额减退款金额计算"}
        ],
        sources=[],
        tool_history=history,
        result_rows=rows,
    )
    assert contract is not None
    GoldenScenarioRuleApplicationContract.model_validate(
        contract["required_rule_applications"][0]
    )
    assert contract["required_rule_applications"][0]["metric_consumed"] is True
    assert contract["required_rule_applications"][0]["formula_hash"] == "f" * 64
    assert (
        evaluate_golden_contract(
            contract,
            confirmed_knowledge=[
                {
                    "key": "metric:net_revenue",
                    "value": "净收入按实付金额减退款金额计算",
                }
            ],
            sources=[],
            tool_history=history,
            result_rows=rows,
        )
        == []
    )

    unrelated = deepcopy(history)
    unrelated[2]["source_result"] = "orders"
    failures = evaluate_golden_contract(
        contract,
        confirmed_knowledge=[
            {"key": "metric:net_revenue", "value": "净收入按实付金额减退款金额计算"}
        ],
        sources=[],
        tool_history=unrelated,
        result_rows=rows,
    )
    assert any("没有用于本次最终汇总" in failure for failure in failures)


@pytest.mark.parametrize("operation", ["count", "nunique"])
def test_destructive_aggregate_cannot_reuse_metric_output_alias(operation: str):
    history = _history()
    rows = [{"month": "2026-07", "net_revenue": "18"}]
    contract = build_golden_contract(
        query="按月计算净收入",
        confirmed_knowledge=[
            {"key": "metric:net_revenue", "value": "净收入按实付金额减退款金额计算"}
        ],
        sources=[],
        tool_history=history,
        result_rows=rows,
    )
    assert contract is not None
    destructive = deepcopy(history[:-1])
    destructive.extend(
        [
            {
                "kind": "aggregate",
                "source_result": "revenue_summary",
                "result_name": "overwritten_metric",
                "operation": operation,
                "value_column": "net_revenue" if operation == "nunique" else None,
                "output_column": "net_revenue",
                "required_metric_column": "net_revenue",
                "required_metric_definition_hash": "c" * 64,
                "metric_policy_satisfied": True,
                "metric_input_column": "net_revenue",
                "metric_output_column": "net_revenue",
                "numeric_backend": "decimal",
                "decimal_aggregate_evidence": {"kind": "decimal_aggregate"},
            },
            {
                "kind": "validation",
                "result_name": "overwritten_metric",
                "result_hash": "e" * 64,
                "profile": {
                    "columns": ["net_revenue"],
                    "keys": {},
                    "numeric": {"net_revenue": {}},
                    "truncated": False,
                },
            },
        ]
    )

    failures = evaluate_golden_contract(
        contract,
        confirmed_knowledge=[
            {"key": "metric:net_revenue", "value": "净收入按实付金额减退款金额计算"}
        ],
        sources=[],
        tool_history=destructive,
        result_rows=[{"net_revenue": 1}],
    )

    assert any("没有用于本次最终汇总" in failure for failure in failures)

    counted = deepcopy(history[:-1])
    counted.extend(
        [
            {
                "kind": "aggregate",
                "source_result": "revenue_summary",
                "result_name": "row_count_only",
                "operation": "count",
                "output_column": "net_revenue",
                "required_metric_column": "net_revenue",
                "required_metric_definition_hash": "c" * 64,
                "metric_policy_satisfied": True,
                "metric_input_column": None,
                "metric_output_column": "net_revenue",
            },
            {
                "kind": "validation",
                "result_name": "row_count_only",
                "result_hash": "e" * 64,
                "profile": {
                    "columns": ["net_revenue"],
                    "keys": {},
                    "numeric": {"net_revenue": {}},
                    "truncated": False,
                },
            },
        ]
    )
    failures = evaluate_golden_contract(
        contract,
        confirmed_knowledge=[
            {"key": "metric:net_revenue", "value": "净收入按实付金额减退款金额计算"}
        ],
        sources=[],
        tool_history=counted,
        result_rows=[{"net_revenue": 1}],
    )
    assert any("没有用于本次最终汇总" in failure for failure in failures)

    wrong_backend = deepcopy(history)
    wrong_backend[2]["numeric_backend"] = "pandas"
    failures = evaluate_golden_contract(
        contract,
        confirmed_knowledge=[
            {"key": "metric:net_revenue", "value": "净收入按实付金额减退款金额计算"}
        ],
        sources=[],
        tool_history=wrong_backend,
        result_rows=rows,
    )
    assert any("没有用于本次最终汇总" in failure for failure in failures)
