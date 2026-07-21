"""Pure standing-analysis domain tests; no database, model, or network involved."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.models.workspace import (
    StandingAnalysisCreate,
    StandingAnalysisResponse,
    StandingAnalysisUpdate,
    StandingInFlightClaim,
    StandingMaterialityPolicy,
    StandingMaterialityRule,
    StandingPrepareRequest,
    StandingPrepareResponse,
)
from app.services.standing_analysis import (
    build_validated_result_snapshot,
    canonical_input_token,
    compare_validated_result_snapshots,
)

STANDING_ID = "standing_0123456789abcdefabcd"
PLAYBOOK_ID = "pb_0123456789abcdefabcd"
PLAYBOOK_SHAPE_HASH = "a" * 64
NOW = datetime(2026, 7, 17, tzinfo=UTC)


def _token(version: str) -> str:
    return canonical_input_token(
        standing_analysis_id=STANDING_ID,
        playbook_id=PLAYBOOK_ID,
        playbook_shape_hash=PLAYBOOK_SHAPE_HASH,
        source_fingerprints={"orders": version},
        semantic_versions={"revenue_policy": "confirmed-v1"},
        recipe_fingerprints={"orders": "clean-v1"},
    )


def _snapshot(
    *,
    run: int,
    version: str,
    rows: list[dict[str, object]],
    expected_shape_hash: str | None = None,
    expected_columns: list[str] | None = None,
):
    return build_validated_result_snapshot(
        analysis_run_id=UUID(int=run),
        result_name="regional_revenue",
        input_token=_token(version),
        rows=rows,
        key_columns=["region"],
        numeric_columns=["revenue"],
        truncated=False,
        expected_columns=expected_columns,
        expected_shape_hash=expected_shape_hash,
    )


def _policy(
    *,
    threshold: float,
    change_kind: str = "absolute",
    scope: str = "either",
) -> StandingMaterialityPolicy:
    return StandingMaterialityPolicy(
        rules=[
            StandingMaterialityRule(
                id="rule_revenue",
                metric="revenue",
                scope=scope,
                change_kind=change_kind,
                threshold=threshold,
            )
        ]
    )


def _standing_response(
    *,
    state: str = "active",
    claim: StandingInFlightClaim | None = None,
    attention_reason: str | None = None,
) -> StandingAnalysisResponse:
    return StandingAnalysisResponse(
        id=STANDING_ID,
        project_id=UUID(int=20),
        name="区域收入变化",
        query="持续观察区域收入变化",
        playbook_id=PLAYBOOK_ID,
        playbook_shape_hash=PLAYBOOK_SHAPE_HASH,
        watched_source_roles=["orders"],
        state=state,
        materiality=_policy(threshold=5),
        in_flight=claim,
        attention_reason=attention_reason,
        created_at=NOW,
        updated_at=NOW,
    )


def test_canonical_input_token_ignores_mapping_order_but_binds_every_version():
    first = canonical_input_token(
        standing_analysis_id=STANDING_ID,
        playbook_id=PLAYBOOK_ID,
        playbook_shape_hash=PLAYBOOK_SHAPE_HASH,
        source_fingerprints={"stores": "stores-v1", "orders": "orders-v1"},
        semantic_versions={"store_join": "v2", "revenue_policy": "v1"},
        recipe_fingerprints={"stores": "clean-b", "orders": "clean-a"},
    )
    reordered = canonical_input_token(
        standing_analysis_id=STANDING_ID,
        playbook_id=PLAYBOOK_ID,
        playbook_shape_hash=PLAYBOOK_SHAPE_HASH,
        source_fingerprints={"orders": "orders-v1", "stores": "stores-v1"},
        semantic_versions={"revenue_policy": "v1", "store_join": "v2"},
        recipe_fingerprints={"orders": "clean-a", "stores": "clean-b"},
    )
    changed = canonical_input_token(
        standing_analysis_id=STANDING_ID,
        playbook_id=PLAYBOOK_ID,
        playbook_shape_hash=PLAYBOOK_SHAPE_HASH,
        source_fingerprints={"orders": "orders-v2", "stores": "stores-v1"},
        semantic_versions={"revenue_policy": "v1", "store_join": "v2"},
        recipe_fingerprints={"orders": "clean-a", "stores": "clean-b"},
    )

    assert first == reordered
    assert len(first) == 64
    assert first != changed


def test_canonical_input_token_changes_when_same_playbook_id_gets_a_new_shape():
    original = canonical_input_token(
        standing_analysis_id=STANDING_ID,
        playbook_id=PLAYBOOK_ID,
        playbook_shape_hash="a" * 64,
        source_fingerprints={"orders": "orders-v1"},
    )
    overwritten_shape = canonical_input_token(
        standing_analysis_id=STANDING_ID,
        playbook_id=PLAYBOOK_ID,
        playbook_shape_hash="b" * 64,
        source_fingerprints={"orders": "orders-v1"},
    )

    assert original != overwritten_shape


def test_snapshot_rejects_a_change_matrix_too_large_for_the_desktop_runtime():
    metrics = [f"metric_{index}" for index in range(100)]
    rows = [
        {"region": f"region_{row_index}", **{metric: row_index for metric in metrics}}
        for row_index in range(501)
    ]

    with pytest.raises(ValueError, match="too many numeric cells"):
        build_validated_result_snapshot(
            analysis_run_id=UUID(int=99),
            result_name="large_result",
            input_token=_token("large"),
            rows=rows,
            key_columns=["region"],
            numeric_columns=metrics,
            truncated=False,
            expected_columns=["region", *metrics],
        )


def test_zero_baseline_percent_is_undefined_and_never_infinite():
    baseline = _snapshot(run=1, version="july", rows=[{"region": "华东", "revenue": 0}])
    current = _snapshot(run=2, version="august", rows=[{"region": "华东", "revenue": 25}])

    brief = compare_validated_result_snapshots(
        baseline,
        current,
        _policy(threshold=0.01, change_kind="percent"),
    )

    overall = brief.overall[0]
    assert overall.before == 0
    assert overall.delta == 25
    assert overall.baseline_zero is True
    assert overall.percent_change is None
    assert brief.status == "no_material_change"


def test_keyed_cell_changes_are_detected_when_overall_total_is_unchanged():
    baseline = _snapshot(
        run=1,
        version="july",
        rows=[{"region": "华东", "revenue": 10}, {"region": "华南", "revenue": 20}],
    )
    current = _snapshot(
        run=2,
        version="august",
        rows=[{"region": "华东", "revenue": 15}, {"region": "华南", "revenue": 15}],
    )
    policy = StandingMaterialityPolicy(
        rules=[
            StandingMaterialityRule(
                id="rule_overall_large",
                metric="revenue",
                scope="overall",
                change_kind="absolute",
                threshold=100,
            ),
            StandingMaterialityRule(
                id="rule_region_move",
                metric="revenue",
                scope="by_key",
                change_kind="absolute",
                threshold=5,
            ),
        ]
    )

    brief = compare_validated_result_snapshots(baseline, current, policy)

    assert brief.overall[0].delta == 0
    assert [item.changes[0].delta for item in brief.by_key] == [5, -5]
    assert brief.status == "material_change"
    assert brief.matched_rule_ids == ["rule_region_move"]


def test_below_threshold_still_returns_a_no_material_change_brief():
    baseline = _snapshot(run=1, version="july", rows=[{"region": "华东", "revenue": 10}])
    current = _snapshot(run=2, version="august", rows=[{"region": "华东", "revenue": 11}])

    brief = compare_validated_result_snapshots(baseline, current, _policy(threshold=5))

    assert brief.status == "no_material_change"
    assert brief.matched_rule_ids == []
    assert brief.by_key[0].changes[0].delta == 1
    assert brief.top_drivers[0].change.delta == 1


def test_top_driver_order_and_snapshot_ids_are_stable_across_row_order():
    baseline_rows = [{"region": "B", "revenue": 10}, {"region": "A", "revenue": 10}]
    current_rows = [{"region": "B", "revenue": 5}, {"region": "A", "revenue": 15}]
    baseline = _snapshot(run=1, version="july", rows=baseline_rows)
    current = _snapshot(run=2, version="august", rows=current_rows)
    baseline_reordered = _snapshot(run=1, version="july", rows=list(reversed(baseline_rows)))
    current_reordered = _snapshot(run=2, version="august", rows=list(reversed(current_rows)))

    brief = compare_validated_result_snapshots(baseline, current, _policy(threshold=1))
    reordered_brief = compare_validated_result_snapshots(
        baseline_reordered,
        current_reordered,
        _policy(threshold=1),
    )

    assert baseline.snapshot_id == baseline_reordered.snapshot_id
    assert current.snapshot_id == current_reordered.snapshot_id
    assert brief.brief_id == reordered_brief.brief_id
    assert [driver.key["region"] for driver in brief.top_drivers] == ["A", "B"]
    assert [driver.rank for driver in brief.top_drivers] == [1, 2]


def test_snapshot_rejects_missing_or_non_unique_keys_and_truncated_results():
    common = {
        "analysis_run_id": UUID(int=1),
        "result_name": "regional_revenue",
        "input_token": _token("july"),
        "numeric_columns": ["revenue"],
        "truncated": False,
    }
    with pytest.raises(ValueError, match="key_columns"):
        build_validated_result_snapshot(
            **common,
            key_columns=[],
            rows=[{"region": "华东", "revenue": 10}],
        )
    with pytest.raises(ValidationError, match="uniquely identify"):
        build_validated_result_snapshot(
            **common,
            key_columns=["region"],
            rows=[
                {"region": "华东", "revenue": 10},
                {"region": "华东", "revenue": 12},
            ],
        )
    with pytest.raises(ValueError, match="non-truncated"):
        build_validated_result_snapshot(
            **{**common, "truncated": True},
            key_columns=["region"],
            rows=[{"region": "华东", "revenue": 10}],
        )


def test_snapshot_rejects_shape_drift_before_comparison():
    baseline = _snapshot(run=1, version="july", rows=[{"region": "华东", "revenue": 10}])

    with pytest.raises(ValueError, match="shape drift"):
        _snapshot(
            run=2,
            version="august",
            rows=[{"region": "华东", "revenue": 12, "orders": 2}],
            expected_columns=["region", "revenue", "orders"],
            expected_shape_hash=baseline.shape_hash,
        )


def test_standing_contracts_forbid_unknown_fields():
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        StandingMaterialityRule(
            id="rule_revenue",
            metric="revenue",
            change_kind="absolute",
            threshold=5,
            model_decides=True,
        )


def test_create_and_update_contracts_keep_playbook_and_baseline_server_authoritative():
    request = StandingAnalysisCreate(
        analysis_run_id=UUID(int=1),
        name="每月区域收入",
        materiality=_policy(threshold=5),
    )
    assert request.analysis_run_id == UUID(int=1)
    assert StandingAnalysisUpdate(state="paused").state == "paused"
    with pytest.raises(ValidationError, match="at least one"):
        StandingAnalysisUpdate()
    with pytest.raises(ValidationError, match="at least one"):
        StandingAnalysisUpdate(name=None)
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        StandingAnalysisCreate(
            analysis_run_id=UUID(int=1),
            materiality=_policy(threshold=5),
            playbook_id=PLAYBOOK_ID,
        )


def test_prepare_request_does_not_accept_client_created_chat_identity():
    request = StandingPrepareRequest(trigger="app_start_overdue", force=False)
    assert request.request_id is None
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        StandingPrepareRequest(
            trigger="manual",
            conversation_id=UUID(int=3),
        )


def test_prepared_response_binds_atomic_claim_and_only_stores_brief_reference():
    claim = StandingInFlightClaim(
        input_token="c" * 64,
        idempotency_key="d" * 64,
        analysis_run_id=UUID(int=2),
        conversation_id=UUID(int=3),
        user_message_id=UUID(int=4),
        trigger="manual",
        claimed_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )
    response = StandingPrepareResponse(
        outcome="prepared",
        standing_analysis=_standing_response(claim=claim),
        run_id=claim.analysis_run_id,
        conversation_id=claim.conversation_id,
        user_message_id=claim.user_message_id,
        input_token=claim.input_token,
    )

    assert response.outcome == "prepared"
    assert "last_brief" not in response.standing_analysis.model_dump()
    assert response.standing_analysis.last_brief_artifact_id is None
    with pytest.raises(ValidationError, match="must match the in-flight claim"):
        StandingPrepareResponse(
            outcome="prepared",
            standing_analysis=_standing_response(claim=claim),
            run_id=UUID(int=99),
            conversation_id=claim.conversation_id,
            user_message_id=claim.user_message_id,
            input_token=claim.input_token,
        )


def test_prepare_terminal_outcomes_enforce_state_specific_references():
    token = "e" * 64
    no_change = StandingPrepareResponse(
        outcome="no_change",
        standing_analysis=_standing_response(),
        input_token=token,
    )
    paused = StandingPrepareResponse(
        outcome="paused",
        standing_analysis=_standing_response(state="paused"),
    )
    attention = StandingPrepareResponse(
        outcome="needs_attention",
        standing_analysis=_standing_response(
            state="needs_attention",
            attention_reason="检测到结果结构漂移",
        ),
        attention_reason="检测到结果结构漂移",
    )

    assert no_change.outcome == "no_change"
    assert paused.outcome == "paused"
    assert attention.attention_reason == "检测到结果结构漂移"
    with pytest.raises(ValidationError, match="run, input, and brief"):
        StandingPrepareResponse(
            outcome="already_completed",
            standing_analysis=_standing_response(),
            input_token=token,
        )
