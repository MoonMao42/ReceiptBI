"""Stable business decision slots do not depend on a model choosing one spelling."""

import pytest

from app.services.business_decision_slots import (
    REVENUE_REFUND_POLICY,
    canonicalize_decision_key,
    infer_decision_slot,
)


@pytest.mark.parametrize(
    "key",
    ["revenue_refund_policy", "refund_policy", "refund_handling"],
)
def test_explicit_refund_aliases_share_one_system_key(key: str):
    assert canonicalize_decision_key(key) == REVENUE_REFUND_POLICY


@pytest.mark.parametrize(
    "question",
    [
        "计算收入时，退款订单需要扣除吗？",
        "退款金额要不要计入营收？",
        "Should refunded orders be excluded from revenue?",
    ],
)
def test_material_refund_revenue_wording_maps_to_the_known_slot(question: str):
    assert infer_decision_slot(question) == REVENUE_REFUND_POLICY


@pytest.mark.parametrize(
    "question",
    [
        "哪些订单符合退款资格？",
        "退款通常需要多久到账？",
        "本月退款率为什么上升？",
        "Should this customer receive a refund?",
    ],
)
def test_unrelated_refund_questions_are_not_merged(question: str):
    assert infer_decision_slot(question) is None
    assert (
        canonicalize_decision_key("refund_question", question=question)
        == "refund_question"
    )


def test_unknown_keys_are_preserved_instead_of_fuzzily_rewritten():
    assert canonicalize_decision_key("refund_window_policy") == "refund_window_policy"
    scoped = "excel_sheet_selection:9bb7cb74-77e7-4f51-b4b1-8b0fe1712d15"
    assert canonicalize_decision_key(scoped) == scoped
    assert canonicalize_decision_key(REVENUE_REFUND_POLICY) == REVENUE_REFUND_POLICY
