"""Project-level Standing Brief API."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import projects
from app.db import get_db
from app.db.tables import AnalysisRun, Conversation, Message, Project
from app.models import (
    APIResponse,
    StandingAnalysisCreate,
    StandingAnalysisResponse,
    StandingAnalysisUpdate,
    StandingInFlightClaim,
    StandingPrepareRequest,
    StandingPrepareResponse,
)
from app.services.golden_regression import find_matching_contract, normalize_query_key
from app.services.standing_analysis import build_validated_result_snapshot
from app.services.standing_workspace import (
    MAX_STANDING_ANALYSES,
    StandingWorkspaceCorruptError,
    StandingWorkspaceError,
    baseline_ref,
    canonical_hash,
    evaluate_standing_input,
    load_analysis_playbooks,
    load_standing_analyses,
    persist_snapshot_artifact,
    read_complete_result_artifact,
    read_snapshot_artifact,
    save_standing_analyses,
    standing_analysis_id,
    validate_playbook_baseline_evidence,
)

router = APIRouter(prefix="/projects/{project_id}/standing-analyses", tags=["standing analyses"])


def _storage_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, StandingWorkspaceCorruptError):
        return HTTPException(status_code=500, detail=str(exc))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


async def _locked_project(db: AsyncSession, project_id: UUID) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id).with_for_update())
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
    return project


def _definitions(project: Project) -> list[StandingAnalysisResponse]:
    try:
        return load_standing_analyses(project)
    except StandingWorkspaceCorruptError as exc:
        raise _storage_http_error(exc) from exc


def _definition_or_404(
    definitions: list[StandingAnalysisResponse],
    standing_id: str,
) -> tuple[int, StandingAnalysisResponse]:
    for index, item in enumerate(definitions):
        if item.id == standing_id:
            return index, item
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="持续分析不存在")


def _active_claim(claim: StandingInFlightClaim | None, now: datetime) -> bool:
    if claim is None:
        return False
    expires_at = claim.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at > now


def _run_keeps_expired_claim(run: AnalysisRun) -> bool:
    """Do not replace a run that is executing or waiting for user action."""

    if run.state == "waiting_confirmation":
        return True
    if run.state in {"understanding", "investigating"} and run.stage != "prepared":
        return True
    return run.state == "needs_attention" and bool((run.checkpoint or {}).get("resumable"))


def _prepare_response_for_claim(
    definition: StandingAnalysisResponse,
    *,
    outcome: str,
) -> StandingPrepareResponse:
    claim = definition.in_flight
    if claim is None:  # pragma: no cover - guarded by the caller and Pydantic model
        raise RuntimeError("missing standing-analysis claim")
    return StandingPrepareResponse(
        outcome=outcome,
        standing_analysis=definition,
        run_id=claim.analysis_run_id,
        conversation_id=claim.conversation_id,
        user_message_id=claim.user_message_id,
        input_token=claim.input_token,
    )


def _validate_materiality_metrics(materiality, numeric_columns: list[str]) -> None:
    available = set(numeric_columns)
    missing = sorted({rule.metric for rule in materiality.rules if rule.metric not in available})
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="变化判断指标不在可信结果中：" + "、".join(missing),
        )


@router.get("", response_model=APIResponse[list[StandingAnalysisResponse]])
async def list_standing_analyses(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[StandingAnalysisResponse]]:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
    definitions = sorted(_definitions(project), key=lambda item: item.updated_at, reverse=True)
    return APIResponse.ok(data=definitions)


@router.post("", response_model=APIResponse[StandingAnalysisResponse])
async def create_standing_analysis(
    project_id: UUID,
    payload: StandingAnalysisCreate,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[StandingAnalysisResponse]:
    project = await _locked_project(db, project_id)
    definitions = _definitions(project)

    run_result = await db.execute(
        select(AnalysisRun).where(
            AnalysisRun.id == payload.analysis_run_id,
            AnalysisRun.project_id == project_id,
        )
    )
    run = run_result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="调查记录不存在")
    if run.state != "completed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="只能持续跟踪已完成的调查")

    tool_history = list((run.checkpoint or {}).get("tool_history") or [])
    validation, final_step = projects._final_validation(tool_history)
    validation_profile = dict(validation.get("profile") or {})
    result_name = str(final_step.get("result_name") or "").strip()

    try:
        playbooks = load_analysis_playbooks(project)
    except StandingWorkspaceCorruptError as exc:
        raise _storage_http_error(exc) from exc
    query_key = normalize_query_key(run.query)
    matching_playbooks = [
        item for item in playbooks if normalize_query_key(item.query) == query_key
    ]
    if len(matching_playbooks) != 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="需要先为这次调查保存唯一的可复用分析方法",
        )
    playbook = matching_playbooks[0]
    if not playbook.source_roles:
        raise HTTPException(status_code=422, detail="可复用分析没有绑定数据来源")
    try:
        validate_playbook_baseline_evidence(playbook, tool_history, validation)
    except StandingWorkspaceError as exc:
        raise _storage_http_error(exc) from exc

    evidence = [f"validation:{result_name}"[:160]]
    golden = find_matching_contract(
        list((project.extra_data or {}).get("golden_scenarios") or []),
        run.query,
    )
    if golden is not None:
        contract_id = str(golden.get("id") or "")
        validation_index = max(
            index for index, item in enumerate(tool_history) if item is validation
        )
        passed_after_validation = any(
            index > validation_index
            and item.get("kind") == "golden_regression_validation"
            and item.get("status") == "passed"
            and str(item.get("contract_id") or "") == contract_id
            and str(item.get("result_name") or "") == result_name
            for index, item in enumerate(tool_history)
        )
        if not passed_after_validation:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="这次结果尚未通过项目中已确认的回归检查",
            )
        evidence.append(f"golden:{contract_id}"[:160])

    standing_id = standing_analysis_id(project_id, playbook.id)
    input_state = await evaluate_standing_input(
        db,
        project=project,
        standing_id=standing_id,
        playbook_id=playbook.id,
        expected_playbook_shape_hash=playbook.shape_hash,
        baseline_run=run,
    )
    if input_state.attention_reason or input_state.token is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=input_state.attention_reason or "当前项目状态无法建立持续分析",
        )
    try:
        complete_result = await read_complete_result_artifact(
            db,
            project_id=project_id,
            run=run,
            result_name=result_name,
            validation_profile=validation_profile,
        )
        snapshot = build_validated_result_snapshot(
            analysis_run_id=run.id,
            result_name=result_name,
            input_token=input_state.token,
            rows=complete_result.rows,
            key_columns=complete_result.key_columns,
            numeric_columns=complete_result.numeric_columns,
            truncated=False,
            expected_columns=complete_result.columns,
        )
        _validate_materiality_metrics(payload.materiality, snapshot.numeric_columns)
    except (StandingWorkspaceError, ValidationError, ValueError) as exc:
        raise _storage_http_error(exc) from exc

    existing = next((item for item in definitions if item.id == standing_id), None)
    imported_shell = (
        existing is not None and existing.baseline is None and existing.state == "paused"
    )
    if existing is not None:
        if existing.baseline is not None and existing.baseline.snapshot_id == snapshot.snapshot_id:
            return APIResponse.ok(data=existing, message="持续分析已经建立")
        if not imported_shell:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="这项持续分析已经有不同的可信基线",
            )
    if existing is None and len(definitions) >= MAX_STANDING_ANALYSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"每个项目最多保存 {MAX_STANDING_ANALYSES} 个持续分析",
        )

    snapshot_artifact = await persist_snapshot_artifact(
        db,
        project_id=project_id,
        run=run,
        standing_id=standing_id,
        playbook_id=playbook.id,
        snapshot=snapshot,
    )
    now = datetime.now(UTC)
    definition = StandingAnalysisResponse(
        id=standing_id,
        project_id=project_id,
        name=(payload.name or (existing.name if imported_shell else None) or playbook.name)[:160],
        query=run.query,
        playbook_id=playbook.id,
        playbook_shape_hash=playbook.shape_hash,
        watched_source_roles=[item.logical_name for item in playbook.source_roles],
        overdue_after_seconds=(
            payload.overdue_after_seconds
            or (existing.overdue_after_seconds if imported_shell else 86400)
        ),
        materiality=payload.materiality,
        baseline=baseline_ref(
            snapshot=snapshot,
            artifact=snapshot_artifact,
            evidence=evidence,
            accepted_at=now,
        ),
        last_evaluated_token=input_state.token,
        last_run_id=run.id,
        created_at=existing.created_at if imported_shell else now,
        updated_at=now,
    )
    if imported_shell and existing is not None:
        definitions[definitions.index(existing)] = definition
    else:
        definitions.append(definition)
    try:
        save_standing_analyses(project, definitions)
    except (StandingWorkspaceCorruptError, StandingWorkspaceError, ValidationError) as exc:
        raise _storage_http_error(exc) from exc
    await db.commit()
    return APIResponse.ok(data=definition, message="已开始持续关注这项分析")


@router.patch("/{standing_id}", response_model=APIResponse[StandingAnalysisResponse])
async def update_standing_analysis(
    project_id: UUID,
    standing_id: str,
    payload: StandingAnalysisUpdate,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[StandingAnalysisResponse]:
    project = await _locked_project(db, project_id)
    definitions = _definitions(project)
    index, current = _definition_or_404(definitions, standing_id)
    values = payload.model_dump(exclude_unset=True)
    if current.in_flight is not None and values.get("materiality") is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="变化判断规则需要等当前调查结束后再修改",
        )
    if payload.materiality is not None and current.baseline is not None:
        try:
            snapshot = await read_snapshot_artifact(
                db,
                project_id=project_id,
                baseline=current.baseline,
            )
        except (StandingWorkspaceError, StandingWorkspaceCorruptError) as exc:
            raise _storage_http_error(exc) from exc
        _validate_materiality_metrics(payload.materiality, snapshot.numeric_columns)
    update: dict[str, object] = {"updated_at": datetime.now(UTC)}
    for key in ("name", "materiality", "overdue_after_seconds"):
        if values.get(key) is not None:
            update[key] = values[key]
    if payload.state == "paused":
        claim = current.in_flight
        if claim is not None:
            claimed_run_result = await db.execute(
                select(AnalysisRun).where(
                    AnalysisRun.id == claim.analysis_run_id,
                    AnalysisRun.project_id == project_id,
                )
            )
            claimed_run = claimed_run_result.scalar_one_or_none()
            if (
                claimed_run is not None
                and claimed_run.state == "understanding"
                and claimed_run.stage == "prepared"
            ):
                claimed_run.state = "needs_attention"
                claimed_run.stage = "needs_attention"
                claimed_run.error = "持续分析已暂停"
                claimed_run.checkpoint = {
                    **(claimed_run.checkpoint or {}),
                    "resumable": False,
                    "reason": "standing_analysis_paused",
                }
        update.update(
            state="paused",
            attention_reason=None,
            attention_reason_code=None,
            attention_reason_params={},
            in_flight=None,
        )
    elif payload.state == "active":
        if current.baseline is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="需要先用一份已完成且校验过的结果重新建立基线",
            )
        update.update(
            state="active",
            attention_reason=None,
            attention_reason_code=None,
            attention_reason_params={},
        )
    updated = current.model_copy(update=update)
    # model_copy does not revalidate updates in Pydantic v2.
    updated = StandingAnalysisResponse.model_validate(updated.model_dump())
    definitions[index] = updated
    save_standing_analyses(project, definitions)
    await db.commit()
    return APIResponse.ok(data=updated, message="持续分析已更新")


@router.post(
    "/{standing_id}/prepare-run",
    response_model=APIResponse[StandingPrepareResponse],
)
async def prepare_standing_run(
    project_id: UUID,
    standing_id: str,
    payload: StandingPrepareRequest,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[StandingPrepareResponse]:
    project = await _locked_project(db, project_id)
    definitions = _definitions(project)
    index, definition = _definition_or_404(definitions, standing_id)
    if definition.state == "paused":
        return APIResponse.ok(
            data=StandingPrepareResponse(outcome="paused", standing_analysis=definition)
        )
    if definition.state == "needs_attention":
        return APIResponse.ok(
            data=StandingPrepareResponse(
                outcome="needs_attention",
                standing_analysis=definition,
                attention_reason=definition.attention_reason,
                attention_reason_code=definition.attention_reason_code,
                attention_reason_params=definition.attention_reason_params,
            )
        )
    if payload.force and payload.request_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="强制重跑必须提供 request_id",
        )

    request_idempotency_key = (
        canonical_hash(
            {
                "standing_analysis_id": definition.id,
                "trigger": payload.trigger,
                "request_id": str(payload.request_id),
                "input_token": None,
            }
        )
        if payload.request_id is not None
        else None
    )
    if (
        request_idempotency_key is not None
        and definition.last_run_id is not None
        and definition.last_brief_artifact_id is not None
    ):
        previous_run = await db.get(AnalysisRun, definition.last_run_id)
        previous_claim = (
            (previous_run.checkpoint or {}).get("standing_analysis")
            if previous_run is not None
            else None
        )
        if (
            previous_run is not None
            and previous_run.project_id == project_id
            and previous_run.state == "completed"
            and isinstance(previous_claim, dict)
            and str(previous_claim.get("idempotency_key") or "") == request_idempotency_key
        ):
            return APIResponse.ok(
                data=StandingPrepareResponse(
                    outcome="already_completed",
                    standing_analysis=definition,
                    run_id=previous_run.id,
                    input_token=str(previous_claim.get("input_token") or ""),
                    brief_artifact_id=definition.last_brief_artifact_id,
                )
            )

    input_state = await evaluate_standing_input(
        db,
        project=project,
        standing_id=definition.id,
        playbook_id=definition.playbook_id,
        expected_playbook_shape_hash=definition.playbook_shape_hash,
    )
    now = datetime.now(UTC)
    if input_state.attention_reason or input_state.token is None:
        attention = (input_state.attention_reason or "当前项目状态需要处理")[:1000]
        updated = definition.model_copy(
            update={
                "state": "needs_attention",
                "attention_reason": attention,
                "attention_reason_code": (
                    input_state.attention_reason_code or "standing_project_input_unavailable"
                ),
                "attention_reason_params": input_state.attention_reason_params or {},
                "in_flight": None,
                "updated_at": now,
            }
        )
        updated = StandingAnalysisResponse.model_validate(updated.model_dump())
        definitions[index] = updated
        save_standing_analyses(project, definitions)
        await db.commit()
        return APIResponse.ok(
            data=StandingPrepareResponse(
                outcome="needs_attention",
                standing_analysis=updated,
                attention_reason=attention,
                attention_reason_code=updated.attention_reason_code,
                attention_reason_params=updated.attention_reason_params,
            )
        )
    token = input_state.token
    accepted_at = definition.baseline.accepted_at if definition.baseline else None
    if accepted_at is not None and accepted_at.tzinfo is None:
        accepted_at = accepted_at.replace(tzinfo=UTC)
    overdue = bool(
        payload.trigger == "app_start_overdue"
        and accepted_at is not None
        and now >= accepted_at + timedelta(seconds=definition.overdue_after_seconds)
    )
    idempotency_key = request_idempotency_key or canonical_hash(
        {
            "standing_analysis_id": definition.id,
            "trigger": payload.trigger,
            "request_id": None,
            "input_token": token,
            "evaluation_anchor": accepted_at.isoformat() if overdue and accepted_at else None,
        }
    )
    if definition.in_flight is not None:
        claim = definition.in_flight
        claimed_run_result = await db.execute(
            select(AnalysisRun).where(
                AnalysisRun.id == claim.analysis_run_id,
                AnalysisRun.project_id == project_id,
            )
        )
        claimed_run = claimed_run_result.scalar_one_or_none()
        if claimed_run is None:
            attention = "持续分析的执行记录已缺失，需要重新建立运行状态"
            updated = StandingAnalysisResponse.model_validate(
                definition.model_copy(
                    update={
                        "state": "needs_attention",
                        "attention_reason": attention,
                        "attention_reason_code": "standing_in_flight_run_missing",
                        "attention_reason_params": {},
                        "in_flight": None,
                        "updated_at": now,
                    }
                ).model_dump()
            )
            definitions[index] = updated
            save_standing_analyses(project, definitions)
            await db.commit()
            return APIResponse.ok(
                data=StandingPrepareResponse(
                    outcome="needs_attention",
                    standing_analysis=updated,
                    attention_reason=attention,
                    attention_reason_code=updated.attention_reason_code,
                    attention_reason_params=updated.attention_reason_params,
                )
            )
        if _active_claim(claim, now) or _run_keeps_expired_claim(claimed_run):
            return APIResponse.ok(
                data=_prepare_response_for_claim(definition, outcome="already_running")
            )
        if claimed_run.state not in {"completed", "needs_attention"}:
            claimed_run.state = "needs_attention"
            claimed_run.stage = "needs_attention"
            claimed_run.error = "持续分析执行权已过期"
            claimed_run.checkpoint = {
                **(claimed_run.checkpoint or {}),
                "resumable": False,
                "reason": "standing_claim_expired",
            }

    if (
        not payload.force
        and not overdue
        and token
        in {
            definition.last_evaluated_token,
            definition.baseline.input_token if definition.baseline else None,
        }
    ):
        if definition.in_flight is not None:
            definition = StandingAnalysisResponse.model_validate(
                definition.model_copy(update={"in_flight": None, "updated_at": now}).model_dump()
            )
            definitions[index] = definition
            save_standing_analyses(project, definitions)
            await db.commit()
        return APIResponse.ok(
            data=StandingPrepareResponse(
                outcome="no_change",
                standing_analysis=definition,
                input_token=token,
            )
        )

    conversation = Conversation(
        title=definition.name,
        status="active",
        extra_data={
            "project_id": str(project_id),
            "standing_analysis_id": definition.id,
        },
    )
    db.add(conversation)
    await db.flush()
    user_message = Message(
        conversation_id=conversation.id,
        role="user",
        content=definition.query,
        extra_data={
            "project_id": str(project_id),
            "standing_analysis_id": definition.id,
            "standing_trigger": payload.trigger,
            "input_token": token,
        },
    )
    db.add(user_message)
    await db.flush()
    run = AnalysisRun(
        project_id=project_id,
        conversation_id=conversation.id,
        query=definition.query,
        state="understanding",
        stage="prepared",
        checkpoint={
            "standing_analysis": {
                "id": definition.id,
                "input_token": token,
                "idempotency_key": idempotency_key,
                "playbook_id": definition.playbook_id,
                "playbook_shape_hash": definition.playbook_shape_hash,
                "baseline_snapshot_id": (
                    definition.baseline.snapshot_id if definition.baseline else None
                ),
                "trigger": payload.trigger,
            },
            "resumable": True,
            "reason": "standing_analysis_prepared",
        },
    )
    db.add(run)
    await db.flush()
    claim = StandingInFlightClaim(
        input_token=token,
        idempotency_key=idempotency_key,
        analysis_run_id=run.id,
        conversation_id=conversation.id,
        user_message_id=user_message.id,
        trigger=payload.trigger,
        claimed_at=now,
        expires_at=now + timedelta(hours=1),
    )
    updated = StandingAnalysisResponse.model_validate(
        definition.model_copy(update={"in_flight": claim, "updated_at": now}).model_dump()
    )
    definitions[index] = updated
    save_standing_analyses(project, definitions)
    await db.commit()
    return APIResponse.ok(
        data=_prepare_response_for_claim(updated, outcome="prepared"),
        message="持续分析已准备好",
    )


__all__ = ["router"]
