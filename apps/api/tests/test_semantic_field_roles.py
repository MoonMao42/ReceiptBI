from __future__ import annotations

from pathlib import Path

import pytest

from app.services.data_preflight import run_preflight
from app.services.semantic_field_roles import (
    field_name_tokens,
    has_identifier_semantics,
    has_monetary_semantics,
    has_quantitative_semantics,
    has_refund_semantics,
    has_time_semantics,
    infer_semantic_field_role,
    suggested_metric_operation,
)


def test_name_matching_uses_tokens_instead_of_substrings() -> None:
    assert field_name_tokens("sales_amount") == ("sales", "amount")
    assert field_name_tokens("otherAccountRepCode") == ("other", "account", "rep", "code")

    assert has_monetary_semantics("sales") is True
    assert has_monetary_semantics("sales_amount") is True
    assert has_monetary_semantics("paid_amount") is True
    assert has_monetary_semantics("实付金额") is True
    assert has_monetary_semantics("account_rep_name") is False
    assert has_monetary_semantics("wholesale_region") is False
    assert has_monetary_semantics("presales_owner") is False
    assert has_refund_semantics("退款状态") is True


def test_role_inference_requires_type_evidence_for_measures() -> None:
    assert (
        infer_semantic_field_role("account_rep_name", is_numeric=False, is_datetime=False)
        == "dimension"
    )
    assert (
        infer_semantic_field_role("account_rep_id", is_numeric=True, is_datetime=False)
        == "identifier"
    )
    assert (
        infer_semantic_field_role("other_account_rep_code", is_numeric=False, is_datetime=False)
        == "identifier"
    )
    assert infer_semantic_field_role("paid_amount", is_numeric=True, is_datetime=False) == "measure"
    assert (
        infer_semantic_field_role("paid_amount", is_numeric=False, is_datetime=False) == "dimension"
    )
    assert infer_semantic_field_role("active", is_numeric=False, is_datetime=False) == "dimension"
    assert (
        infer_semantic_field_role("numeric_value", is_numeric=True, is_datetime=False)
        == "dimension"
    )


@pytest.mark.parametrize(
    "field_name",
    [
        "quantity",
        "item_qty",
        "order_count",
        "sales_amount",
        "revenue",
        "unit_price",
        "unit_cost",
        "gross_profit",
        "refund_amount",
        "paid_amount",
        "conversion_rate",
        "销量",
    ],
)
def test_explicit_quantitative_numeric_fields_remain_measures(field_name: str) -> None:
    assert has_quantitative_semantics(field_name) is True
    assert infer_semantic_field_role(field_name, is_numeric=True, is_datetime=False) == "measure"


@pytest.mark.parametrize(
    "field_name",
    [
        "rank",
        "order_status",
        "sequence",
        "latitude",
        "longitude",
        "account_balance",
        "inventory_quantity",
        "stock_count",
        "headcount",
        "employee_head_count",
        "sales_rank",
    ],
)
def test_non_additive_numeric_fields_are_not_default_measures(field_name: str) -> None:
    assert has_quantitative_semantics(field_name) is False
    assert infer_semantic_field_role(field_name, is_numeric=True, is_datetime=False) == "dimension"


def test_identifier_and_time_markers_do_not_match_inside_words() -> None:
    assert has_identifier_semantics("customer_id") is True
    assert has_identifier_semantics("account_name") is False
    assert has_identifier_semantics("paid_amount") is False
    assert has_time_semantics("order_date") is True
    assert has_time_semantics("created_at") is True
    assert has_time_semantics("last_updated_at") is True
    assert has_time_semantics("created_by") is False
    assert has_time_semantics("updated_by") is False
    assert has_time_semantics("runtime_status") is False
    assert has_time_semantics("candidate_name") is False
    assert infer_semantic_field_role("updated_by", is_numeric=False, is_datetime=True) == "time"


def test_metric_operation_uses_complete_tokens() -> None:
    assert suggested_metric_operation("average_order_value") == "avg"
    assert suggested_metric_operation("refund_rate") == "avg"
    assert suggested_metric_operation("prorated_amount") == "sum"
    assert suggested_metric_operation("sales_amount") == "sum"
    assert suggested_metric_operation("退款率") == "avg"
    assert suggested_metric_operation("税率编码") == "sum"


def test_file_preflight_keeps_account_reps_as_dimensions_or_identifiers(tmp_path: Path) -> None:
    source = tmp_path / "account_reps.csv"
    source.write_text(
        "account_rep_name,account_rep_id,account_rep_code,paid_amount,active,refund_status\n"
        "Alice,101,S-101,12.5,true,none\n"
        "Bob,102,S-102,20.0,false,refunded\n"
        "Cara,103,S-103,18.0,true,none\n",
        encoding="utf-8",
    )

    result = run_preflight(source, tmp_path / "working")
    roles = {
        item["column"]: item["role"]
        for item in result.source_snapshot["preanalysis"]["candidate_roles"]
    }

    assert roles == {
        "account_rep_name": "dimension",
        "account_rep_id": "identifier",
        "account_rep_code": "identifier",
        "paid_amount": "measure",
        "active": "dimension",
        "refund_status": "dimension",
    }
    assert {item["column"] for item in result.inferred_schema["candidate_grain"]} == {
        "account_rep_id",
        "account_rep_code",
    }
