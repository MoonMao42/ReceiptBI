"""Finalize a prepared standing analysis inside the normal result transaction."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.tables import AnalysisRun, ArtifactRecord, Project
from app.models.workspace import StandingAnalysisResponse
from app.services.golden_regression import find_matching_contract
from app.services.standing_analysis import (
    build_validated_result_snapshot,
    compare_validated_result_snapshots,
)
from app.services.standing_workspace import (
    StandingWorkspaceCorruptError,
    baseline_ref,
    evaluate_standing_input,
    load_analysis_playbooks,
    load_standing_analyses,
    read_snapshot_artifact,
    save_standing_analyses,
    validate_playbook_execution_evidence,
)


class StandingCompletionError(ValueError):
    """The candidate result cannot safely replace the prior standing baseline."""


class StandingStaleRunError(StandingCompletionError):
    """A superseded run must not mutate the current standing-analysis definition."""


def _standing_checkpoint(run: AnalysisRun) -> dict[str, Any] | None:
    value = (run.checkpoint or {}).get("standing_analysis")
    return dict(value) if isinstance(value, dict) else None


def _final_validation(tool_history: list[dict[str, Any]]) -> dict[str, Any]:
    indexed_validation = next(
        (
            (index, item)
            for index, item in reversed(list(enumerate(tool_history)))
            if item.get("kind") == "validation" and isinstance(item.get("profile"), dict)
        ),
        None,
    )
    if indexed_validation is None:
        raise StandingCompletionError("持续分析的最终结果没有通过校验")
    validation_index, validation = indexed_validation
    if not str(validation.get("result_name") or "").strip():
        raise StandingCompletionError("持续分析的最终结果没有通过校验")
    profile = validation["profile"]
    if bool(profile.get("truncated")):
        raise StandingCompletionError("持续分析的最终结果被截断")
    indexed_data_step = next(
        (
            (index, item)
            for index, item in reversed(list(enumerate(tool_history)))
            if item.get("kind")
            in {
                "structured_query",
                "sql",
                "file_sql",
                "join",
                "aggregate",
                "business_rule_application",
            }
            and item.get("result_name")
        ),
        None,
    )
    if indexed_data_step is None:
        raise StandingCompletionError("最终校验没有绑定最后一个业务结果")
    data_step_index, data_step = indexed_data_step
    if validation_index < data_step_index or str(data_step.get("result_name")) != str(
        validation.get("result_name")
    ):
        raise StandingCompletionError("最终校验没有绑定最后一个业务结果")
    for item in tool_history[validation_index + 1 :]:
        if item.get("kind") != "python":
            continue
        if not (
            item.get("generated")
            and item.get("chart_type")
            and str(item.get("result_name") or "") == str(validation.get("result_name") or "")
        ):
            raise StandingCompletionError("最终校验后又执行了未校验的数据处理")
    return validation


def _replace_definition(
    project: Project,
    definitions: list[StandingAnalysisResponse],
    index: int,
    definition: StandingAnalysisResponse,
) -> None:
    definitions[index] = StandingAnalysisResponse.model_validate(definition.model_dump())
    save_standing_analyses(project, definitions)


def _assert_claim_ownership(
    definition: StandingAnalysisResponse,
    run: AnalysisRun,
    checkpoint: dict[str, Any],
) -> None:
    claim = definition.in_flight
    if claim is None:
        raise StandingStaleRunError("这次持续分析已不再拥有当前执行权")
    if (
        claim.analysis_run_id != run.id
        or claim.conversation_id != run.conversation_id
        or claim.input_token != str(checkpoint.get("input_token") or "")
        or claim.idempotency_key != str(checkpoint.get("idempotency_key") or "")
    ):
        raise StandingStaleRunError("这次持续分析已被更新的运行替代")
    expected_baseline = str(checkpoint.get("baseline_snapshot_id") or "")
    current_baseline = definition.baseline.snapshot_id if definition.baseline else ""
    if not expected_baseline or expected_baseline != current_baseline:
        raise StandingStaleRunError("可信基线已经由另一轮持续分析更新")


async def _definition_for_run(
    db: AsyncSession,
    run: AnalysisRun,
) -> tuple[Project, list[StandingAnalysisResponse], int, StandingAnalysisResponse] | None:
    checkpoint = _standing_checkpoint(run)
    if checkpoint is None:
        return None
    standing_id = str(checkpoint.get("id") or checkpoint.get("standing_analysis_id") or "")
    if not standing_id:
        raise StandingCompletionError("持续分析检查点缺少定义标识")
    project = await db.get(Project, run.project_id, with_for_update=True)
    if project is None:
        raise StandingCompletionError("持续分析所属项目不存在")
    try:
        definitions = load_standing_analyses(project)
    except StandingWorkspaceCorruptError as exc:
        raise StandingCompletionError(str(exc)) from exc
    for index, definition in enumerate(definitions):
        if definition.id == standing_id:
            return project, definitions, index, definition
    raise StandingCompletionError("持续分析定义不存在")


async def mark_standing_run_needs_attention(
    db: AsyncSession,
    run: AnalysisRun,
    reason: str,
) -> bool:
    """Preserve the trusted baseline while making a failed run actionable."""

    resolved = await _definition_for_run(db, run)
    if resolved is None:
        return False
    project, definitions, index, definition = resolved
    checkpoint = _standing_checkpoint(run) or {}
    try:
        _assert_claim_ownership(definition, run, checkpoint)
    except StandingStaleRunError:
        return False
    if definition.state == "paused":
        return True
    updated = StandingAnalysisResponse.model_validate(
        definition.model_copy(
            update={
                "state": "needs_attention",
                "attention_reason": (reason.strip() or "这次持续分析需要处理")[:1000],
                "in_flight": None,
                "updated_at": datetime.now(UTC),
            }
        ).model_dump()
    )
    _replace_definition(project, definitions, index, updated)
    return True


async def _finalize_standing_run_impl(
    db: AsyncSession,
    run: AnalysisRun,
    result_data: dict[str, Any],
) -> bool:
    """Create a deterministic brief and advance the baseline only after every gate passes."""

    resolved = await _definition_for_run(db, run)
    if resolved is None:
        return False
    project, definitions, index, definition = resolved
    checkpoint = _standing_checkpoint(run) or {}
    _assert_claim_ownership(definition, run, checkpoint)
    report = result_data.get("report") or {}
    state = str(result_data.get("analysis_state") or run.state)
    if state != "completed" or report.get("status") != "completed":
        if report.get("status") in {"waiting_confirmation", "needs_data"}:
            # The same run will continue after the user answers or adds data. Keep its claim so
            # a newer run cannot silently replace it and later race the baseline forward.
            return True
        raise StandingCompletionError("这次持续分析尚未形成可接受的完整结果")
    if definition.state == "paused":
        raise StandingCompletionError("持续分析已暂停，不能更新可信基线")
    if definition.baseline is None:
        raise StandingCompletionError("持续分析缺少可信基线")

    claimed_token = str(checkpoint.get("input_token") or "")
    input_state = await evaluate_standing_input(
        db,
        project=project,
        standing_id=definition.id,
        playbook_id=definition.playbook_id,
        expected_playbook_shape_hash=definition.playbook_shape_hash,
    )
    if input_state.attention_reason or input_state.token is None:
        raise StandingCompletionError(
            input_state.attention_reason or "完成调查时项目输入已发生变化"
        )
    if not claimed_token or input_state.token != claimed_token:
        raise StandingCompletionError("调查期间数据或业务定义已变化，旧基线保持不变")

    tool_history = list(result_data.get("tool_history") or [])
    validation = _final_validation(tool_history)
    matching_playbooks = [
        item for item in load_analysis_playbooks(project) if item.id == definition.playbook_id
    ]
    if len(matching_playbooks) != 1:
        raise StandingCompletionError("持续分析绑定的方法不存在或不唯一")
    playbook = matching_playbooks[0]
    if playbook.shape_hash != definition.playbook_shape_hash:
        raise StandingCompletionError("持续分析绑定的方法已经变化")
    validate_playbook_execution_evidence(playbook, tool_history, validation)
    result_name = str(validation.get("result_name") or "")
    if str(result_data.get("result_name") or "") != result_name:
        raise StandingCompletionError("交付结果不是最终校验过的结果")
    profile = dict(validation.get("profile") or {})
    columns = [str(item) for item in profile.get("columns") or []]
    keys = [str(item) for item in (profile.get("keys") or {})]
    numeric = [str(item) for item in (profile.get("numeric") or {})]
    rows = result_data.get("data")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise StandingCompletionError("持续分析没有完整的结构化结果")
    rows_count = result_data.get("rows_count")
    if rows_count is None:
        rows_count = len(rows)
    if int(rows_count) != len(rows):
        raise StandingCompletionError("持续分析结果行数不完整")
    materialized_rows = profile.get("materialized_rows")
    if materialized_rows is not None and int(materialized_rows) != len(rows):
        raise StandingCompletionError("最终校验记录数与交付结果不一致")

    golden = find_matching_contract(
        list((project.extra_data or {}).get("golden_scenarios") or []),
        run.query,
    )
    evidence = [f"validation:{result_name}"[:160]]
    bound_golden_ids = {
        item.removeprefix("golden:")
        for item in definition.baseline.validation_evidence
        if item.startswith("golden:")
    }
    if bound_golden_ids and (golden is None or str(golden.get("id") or "") not in bound_golden_ids):
        raise StandingCompletionError("可信基线绑定的项目回归检查已缺失或变化")
    if golden is not None:
        contract_id = str(golden.get("id") or "")
        validation_index = max(
            index for index, item in enumerate(tool_history) if item is validation
        )
        marker_indices = [
            index
            for index, item in enumerate(tool_history)
            if item.get("kind") == "golden_regression_validation"
            and item.get("status") == "passed"
            and str(item.get("contract_id") or "") == contract_id
            and str(item.get("result_name") or "") == result_name
        ]
        if not any(index > validation_index for index in marker_indices):
            raise StandingCompletionError("本次结果没有通过项目回归检查")
        evidence.append(f"golden:{contract_id}"[:160])

    baseline_snapshot = await read_snapshot_artifact(
        db,
        project_id=run.project_id,
        baseline=definition.baseline,
    )
    current_snapshot = build_validated_result_snapshot(
        analysis_run_id=run.id,
        result_name=result_name,
        input_token=input_state.token,
        rows=rows,
        key_columns=keys,
        numeric_columns=numeric,
        truncated=False,
        expected_columns=columns,
        expected_shape_hash=definition.baseline.shape_hash,
    )
    brief = compare_validated_result_snapshots(
        baseline_snapshot,
        current_snapshot,
        definition.materiality,
    )
    snapshot_artifact = ArtifactRecord(
        project_id=run.project_id,
        analysis_run_id=run.id,
        kind="result_snapshot",
        title="持续分析结果快照",
        payload=current_snapshot.model_dump(mode="json"),
        technical_details={
            "standing_analysis_id": definition.id,
            "playbook_id": definition.playbook_id,
            "validation_state": "validated",
        },
    )
    brief_artifact = ArtifactRecord(
        project_id=run.project_id,
        analysis_run_id=run.id,
        kind="change_brief",
        title="变化简报",
        payload=brief.model_dump(mode="json"),
        technical_details={
            "standing_analysis_id": definition.id,
            "outcome": brief.status,
            "notify_user": brief.status == "material_change",
        },
    )
    db.add_all([snapshot_artifact, brief_artifact])
    await db.flush()
    now = datetime.now(UTC)
    updated = StandingAnalysisResponse.model_validate(
        definition.model_copy(
            update={
                "state": "active",
                "attention_reason": None,
                "in_flight": None,
                "baseline": baseline_ref(
                    snapshot=current_snapshot,
                    artifact=snapshot_artifact,
                    evidence=evidence,
                    accepted_at=now,
                ),
                "last_evaluated_token": input_state.token,
                "last_run_id": run.id,
                "last_brief_artifact_id": brief_artifact.id,
                "updated_at": now,
            }
        ).model_dump()
    )
    _replace_definition(project, definitions, index, updated)
    return True


async def finalize_standing_run(
    db: AsyncSession,
    run: AnalysisRun,
    result_data: dict[str, Any],
) -> bool:
    """Convert all expected standing-contract failures into one recoverable boundary."""

    try:
        return await _finalize_standing_run_impl(db, run, result_data)
    except StandingCompletionError:
        raise
    except (StandingWorkspaceCorruptError, ValueError) as exc:
        raise StandingCompletionError(str(exc) or "持续分析结果未通过可信基线检查") from exc


__all__ = [
    "StandingCompletionError",
    "StandingStaleRunError",
    "finalize_standing_run",
    "mark_standing_run_needs_attention",
]
