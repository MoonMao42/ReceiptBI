"""System-owned report-correction completion receipts."""

import pytest

from app.services.correction_completion import (
    CorrectionCompletionError,
    build_correction_application_receipt,
)


def _required(*, executable: bool = True) -> dict:
    return {
        "id": "correction-1",
        "source_run_id": "run-old",
        "semantic_entry_id": "semantic-1",
        "target_key": "revenue_refund_policy",
        "text": "退款订单不计入收入",
        "definition_hash": "definition-current",
        "executable": executable,
    }


def _filter_history() -> list[dict]:
    return [
        {
            "kind": "structured_query",
            "result_name": "orders",
        },
        {
            "kind": "business_rule_application",
            "semantic_entry_id": "semantic-1",
            "definition_hash": "definition-current",
            "rule_key": "revenue_refund_policy",
            "rule_value": "退款订单不计入收入",
            "action_kind": "value_filter",
            "source_result": "orders",
            "result_name": "orders_without_refunds",
            "before_rows": 10,
            "after_rows": 8,
            "excluded_rows": 2,
            "input_hash": "input",
            "output_hash": "filtered",
            "source_refs": [{"source_logical_name": "orders"}],
        },
        {
            "kind": "aggregate",
            "source_result": "orders_without_refunds",
            "result_name": "monthly_revenue",
        },
        {
            "kind": "validation",
            "result_name": "monthly_revenue",
            "result_hash": "final",
            "profile": {"columns": ["monthly_revenue"]},
        },
    ]


def test_verified_receipt_requires_current_rule_to_reach_final_result():
    receipt = build_correction_application_receipt(
        _required(),
        _filter_history(),
        final_result="monthly_revenue",
    )

    assert receipt is not None
    assert receipt["status"] == "verified"
    assert receipt["summary_code"] == "correction_verified"
    assert receipt["application_result_name"] == "orders_without_refunds"
    assert receipt["final_result_name"] == "monthly_revenue"
    assert receipt["definition_hash"] == "definition-current"
    assert receipt["excluded_rows"] == 2


def test_unrelated_application_cannot_complete_a_correction():
    history = _filter_history()
    history[1]["definition_hash"] = "definition-old"

    with pytest.raises(CorrectionCompletionError, match="尚未真正应用"):
        build_correction_application_receipt(
            _required(),
            history,
            final_result="monthly_revenue",
        )


def test_metric_definition_must_be_consumed_by_final_aggregate():
    history = _filter_history()
    history[1].update(
        {
            "action_kind": "metric_column",
            "column": "paid_amount",
            "result_name": "orders_with_metric_policy",
        }
    )
    history[2].update(
        {
            "source_result": "orders_with_metric_policy",
            "operation": "sum",
            "value_column": "paid_amount",
            "output_column": "monthly_revenue",
            "required_metric_column": "paid_amount",
            "metric_input_column": "paid_amount",
            "metric_output_column": "monthly_revenue",
            "required_metric_definition_hash": "definition-current",
            "metric_policy_satisfied": False,
        }
    )

    with pytest.raises(CorrectionCompletionError, match="没有用于最终汇总"):
        build_correction_application_receipt(
            _required(),
            history,
            final_result="monthly_revenue",
        )

    history[2]["metric_policy_satisfied"] = True
    receipt = build_correction_application_receipt(
        _required(),
        history,
        final_result="monthly_revenue",
    )
    assert receipt is not None
    assert "required_metric_used_by_final_aggregate" in receipt["checks"]


def test_metric_formula_requires_derived_rows_and_matching_final_aggregate():
    history = _filter_history()
    history[1].update(
        {
            "action_kind": "metric_formula",
            "column": "net_revenue",
            "result_name": "orders_with_net_revenue",
            "before_rows": 10,
            "after_rows": 10,
            "excluded_rows": 0,
            "input_hash": "raw-orders",
            "output_hash": "derived-orders",
            "formula_hash": "f" * 64,
        }
    )
    history[2].update(
        {
            "source_result": "orders_with_net_revenue",
            "operation": "sum",
            "value_column": "net_revenue",
            "output_column": "monthly_revenue",
            "required_metric_column": "net_revenue",
            "metric_input_column": "net_revenue",
            "metric_output_column": "monthly_revenue",
            "required_metric_definition_hash": "definition-current",
            "metric_policy_satisfied": True,
            "numeric_backend": "decimal",
            "decimal_aggregate_evidence": {"kind": "decimal_aggregate"},
        }
    )

    receipt = build_correction_application_receipt(
        _required(),
        history,
        final_result="monthly_revenue",
    )
    assert receipt is not None
    assert receipt["status"] == "verified"
    assert receipt["formula_hash"] == "f" * 64

    counted = [
        *history[:-1],
        {
            "kind": "aggregate",
            "source_result": "monthly_revenue",
            "result_name": "row_count_only",
            "operation": "count",
            "output_column": "monthly_revenue",
            "required_metric_column": "net_revenue",
            "required_metric_definition_hash": "definition-current",
            "metric_policy_satisfied": True,
            "metric_input_column": None,
            "metric_output_column": "monthly_revenue",
        },
        {
            "kind": "validation",
            "result_name": "row_count_only",
            "result_hash": "counted",
            "profile": {"columns": ["monthly_revenue"]},
        },
    ]
    with pytest.raises(CorrectionCompletionError, match="没有用于最终汇总"):
        build_correction_application_receipt(
            _required(),
            counted,
            final_result="row_count_only",
        )

    history[2]["required_metric_definition_hash"] = "definition-old"
    with pytest.raises(CorrectionCompletionError, match="没有用于最终汇总"):
        build_correction_application_receipt(
            _required(),
            history,
            final_result="monthly_revenue",
        )

    history[2]["required_metric_definition_hash"] = "definition-current"
    history[2]["numeric_backend"] = "pandas"
    with pytest.raises(CorrectionCompletionError, match="Decimal"):
        build_correction_application_receipt(
            _required(),
            history,
            final_result="monthly_revenue",
        )


def test_definition_only_correction_is_truthful_not_fake_verified():
    receipt = build_correction_application_receipt(
        _required(executable=False),
        [],
        final_result=None,
    )

    assert receipt is not None
    assert receipt["status"] == "definition_only"
    assert receipt["summary_code"] == "correction_definition_only"
    assert receipt["checks"] == ["business_definition_recorded"]


def _relationship_required() -> dict:
    return {
        "id": "correction-relationship",
        "source_run_id": "run-old",
        "semantic_entry_id": "semantic-relationship",
        "target_key": "relationship:orders:stores",
        "text": "订单和门店应按 store_id 关联",
        "correction_type": "relationship_rule",
        "definition_hash": "d" * 64,
        "executable": True,
    }


def _relationship_history() -> list[dict]:
    input_hashes = {"orders": "a" * 64, "stores": "b" * 64}
    profile = {
        "left_key": "store_id",
        "right_key": "store_id",
        "left_match_rate": 1,
        "right_match_rate": 1,
        "cardinality": "many_to_one",
        "expansion_ratio": 1,
        "truncated": False,
    }
    relationship_identity = {
        "relationship_key": "relationship:orders:stores",
        "candidate_relationship_key": "relationship:orders:stores",
        "definition_hash": "d" * 64,
        "left_result": "orders",
        "right_result": "stores",
        "input_hashes": input_hashes,
        "profile": profile,
        "evidence_origin": "system",
        "evidence_scope": "full_relation",
        "completeness": "complete",
        "reusable_proof_eligible": True,
        "source_refs": [
            {
                "source_id": "orders-source",
                "table_or_view": "orders",
                "query_scope": "full",
            },
            {
                "source_id": "stores-source",
                "table_or_view": "stores",
                "query_scope": "full",
            },
        ],
    }
    return [
        {"kind": "structured_query", "result_name": "orders"},
        {"kind": "structured_query", "result_name": "stores"},
        {"kind": "relationship_validation", **relationship_identity},
        {
            "kind": "join",
            **relationship_identity,
            "result_name": "joined_orders",
            "result_hash": "c" * 64,
        },
        {
            "kind": "aggregate",
            "source_result": "joined_orders",
            "result_name": "store_sales",
        },
        {
            "kind": "validation",
            "result_name": "store_sales",
            "result_hash": "e" * 64,
            "profile": {"columns": ["store", "sales"]},
        },
    ]


def test_relationship_correction_requires_validated_join_to_reach_final_result():
    receipt = build_correction_application_receipt(
        _relationship_required(),
        _relationship_history(),
        final_result="store_sales",
    )

    assert receipt is not None
    assert receipt["status"] == "verified"
    assert receipt["summary_code"] == "correction_relationship_verified"
    assert receipt["action_kind"] == "relationship"
    assert receipt["application_result_name"] == "joined_orders"
    assert receipt["result_hash"] == "c" * 64
    assert receipt["checks"] == [
        "current_relationship_definition_tested",
        "relationship_validation_passed",
        "full_relation_reusable_proof",
        "join_reaches_final_result",
        "final_result_revalidated_after_join",
    ]


def test_relationship_correction_rejects_join_on_an_unused_side_branch():
    history = _relationship_history()
    history.insert(
        -1,
        {
            "kind": "aggregate",
            "source_result": "orders",
            "result_name": "store_sales_without_join",
        },
    )
    history[-1]["result_name"] = "store_sales_without_join"

    with pytest.raises(CorrectionCompletionError, match="尚未真正生成最终结果"):
        build_correction_application_receipt(
            _relationship_required(),
            history,
            final_result="store_sales_without_join",
        )


def test_relationship_correction_rejects_missing_or_late_validation_evidence():
    history = _relationship_history()
    history[2]["definition_hash"] = "old-definition"
    with pytest.raises(CorrectionCompletionError, match="没有通过当前数据"):
        build_correction_application_receipt(
            _relationship_required(),
            history,
            final_result="store_sales",
        )

    history = _relationship_history()
    final_validation = history.pop()
    history.insert(3, final_validation)
    with pytest.raises(CorrectionCompletionError, match="应用关联修正后重新核对"):
        build_correction_application_receipt(
            _relationship_required(),
            history,
            final_result="store_sales",
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("evidence_scope", "current_result"),
        ("completeness", "partial"),
        ("reusable_proof_eligible", False),
        ("evidence_origin", None),
    ],
)
def test_relationship_correction_rejects_non_reusable_current_result_evidence(
    field: str,
    value: object,
):
    history = _relationship_history()
    history[2][field] = value
    history[3][field] = value

    with pytest.raises(CorrectionCompletionError, match="当前结果|没有通过当前数据"):
        build_correction_application_receipt(
            _relationship_required(),
            history,
            final_result="store_sales",
        )


@pytest.mark.parametrize("invalid_evidence", ["truncated", "same_endpoint", "filtered_ref"])
def test_relationship_correction_rejects_incomplete_relationship_proof(
    invalid_evidence: str,
):
    history = _relationship_history()
    for item in history[2:4]:
        if invalid_evidence == "truncated":
            item["profile"]["truncated"] = True
        elif invalid_evidence == "same_endpoint":
            item["source_refs"][1] = dict(item["source_refs"][0])
        else:
            item["source_refs"][1]["query_scope"] = "filtered"

    with pytest.raises(CorrectionCompletionError, match="当前结果|没有通过当前数据"):
        build_correction_application_receipt(
            _relationship_required(),
            history,
            final_result="store_sales",
        )
