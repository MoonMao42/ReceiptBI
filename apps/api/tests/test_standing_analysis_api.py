"""Standing Brief API tests; no model, network, or build involved."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.tables import AnalysisRun, ArtifactRecord, Project, ProjectDataSource
from app.models.workspace import (
    AnalysisPlaybookReadStep,
    AnalysisPlaybookResponse,
    AnalysisPlaybookSourceRole,
    AnalysisPlaybookValidationStep,
    AnalysisPlaybookValidationSummary,
)
from app.services.golden_regression import normalize_query_key
from app.services.standing_workspace import canonical_hash


def _materiality() -> dict:
    return {
        "version": 1,
        "match": "any",
        "percent_unit": "ratio",
        "top_driver_limit": 10,
        "rules": [
            {
                "id": "rule_revenue",
                "metric": "revenue",
                "scope": "either",
                "direction": "any",
                "change_kind": "absolute",
                "threshold": 10,
            }
        ],
    }


async def _seed_baseline(
    db: AsyncSession,
    *,
    sampled: bool = False,
) -> tuple[Project, ProjectDataSource, AnalysisRun]:
    query = "持续观察区域收入"
    project = Project(name="持续分析项目")
    db.add(project)
    await db.flush()
    columns = [
        {"name": "region", "type": "VARCHAR"},
        {"name": "revenue", "type": "DOUBLE"},
    ]
    source = ProjectDataSource(
        project_id=project.id,
        kind="file",
        name="orders.csv",
        format="csv",
        working_uri="/tmp/orders.parquet",
        fingerprint="1" * 64,
        status="ready",
        profile_data={
            "logical_name": "orders",
            "version": 1,
            "is_current": True,
            "schema": {"columns": columns},
        },
    )
    db.add(source)
    await db.flush()
    schema_signature = canonical_hash(
        sorted(
            [{"name": item["name"], "type": item["type"]} for item in columns],
            key=lambda item: (item["name"], item["type"]),
        )
    )
    now = datetime.now(UTC)
    playbook = AnalysisPlaybookResponse(
        id="pb_0123456789abcdefabcd",
        name="区域收入变化",
        query=query,
        source_roles=[
            AnalysisPlaybookSourceRole(
                logical_name="orders",
                source_kind="file",
                columns=[
                    {
                        "name": "region",
                        "data_type": "VARCHAR",
                        "canonical_type": "text",
                    },
                    {
                        "name": "revenue",
                        "data_type": "DOUBLE",
                        "canonical_type": "number",
                    },
                ],
                schema_signature=schema_signature,
            )
        ],
        steps=[
            AnalysisPlaybookReadStep(
                order=1,
                kind="read_data",
                summary="读取订单",
                output_result="result_1",
                source_roles=["orders"],
                required_columns=["region", "revenue"],
            ),
            AnalysisPlaybookValidationStep(
                order=2,
                kind="validate_result",
                summary="校验区域收入",
                input_results=["result_1"],
                key_columns=["region"],
                numeric_columns=["revenue"],
            ),
        ],
        validation=AnalysisPlaybookValidationSummary(
            input_result="result_1",
            columns=["region", "revenue"],
            key_columns=["region"],
            numeric_columns=["revenue"],
        ),
        shape_hash="a" * 64,
        created_at=now,
        updated_at=now,
    )
    project.extra_data = {"analysis_playbooks": [playbook.model_dump(mode="json")]}
    rows = [
        {"region": "华东", "revenue": 100},
        {"region": "华南", "revenue": 80},
    ]
    tool_history = [
        {
            "kind": "file_sql",
            "purpose": "汇总区域收入",
            "result_name": "regional_revenue",
        },
        {
            "kind": "validation",
            "purpose": "核对区域收入",
            "result_name": "regional_revenue",
            "profile": {
                "columns": ["region", "revenue"],
                "keys": {"region": {"unique": 2}},
                "numeric": {"revenue": {"count": 2}},
                "materialized_rows": 2,
                "truncated": False,
                "source_refs": [
                    {
                        "source_logical_name": "orders",
                        "source_kind": "file",
                    }
                ],
            },
        },
    ]
    run = AnalysisRun(
        project_id=project.id,
        query=query,
        state="completed",
        stage="completed",
        report={"title": "区域收入变化"},
        checkpoint={"tool_history": tool_history},
    )
    db.add(run)
    await db.flush()
    db.add(
        ArtifactRecord(
            project_id=project.id,
            analysis_run_id=run.id,
            kind="table",
            title="区域收入",
            payload={"rows": rows, "rows_count": len(rows), "sampled": sampled},
            technical_details={"result_name": "regional_revenue"},
        )
    )
    await db.commit()
    return project, source, run


async def _seed_system_capture_baseline(
    db: AsyncSession,
) -> tuple[Project, ProjectDataSource, AnalysisRun]:
    query = "持续观察区域收入"
    project = Project(name="类型化持续分析项目")
    db.add(project)
    await db.flush()
    source = ProjectDataSource(
        project_id=project.id,
        kind="file",
        name="orders.csv",
        format="csv",
        working_uri="/tmp/orders.parquet",
        fingerprint="1" * 64,
        status="ready",
        profile_data={
            "logical_name": "orders",
            "version": 1,
            "is_current": True,
            "schema": {
                "columns": [
                    {"name": "region", "type": "VARCHAR"},
                    {"name": "revenue", "type": "DOUBLE"},
                ]
            },
        },
    )
    db.add(source)
    await db.flush()
    source_ref = {
        "source_id": str(source.id),
        "source_logical_name": "orders",
        "source_kind": "file",
        "table_or_view": "orders",
        "query_scope": "aggregated",
    }
    rows = [
        {"region": "华东", "revenue": 100},
        {"region": "华南", "revenue": 80},
    ]
    tool_history = [
        {
            "kind": "structured_query",
            "source_kind": "file",
            "source_id": str(source.id),
            "source_refs": [source_ref],
            "purpose": "按区域汇总收入",
            "query_plan": {
                "source_id": str(source.id),
                "table": "orders",
                "table_or_view": "orders",
                "query_scope": "aggregated",
                "dimensions": ["region"],
                "metrics": [
                    {"operation": "sum", "column": "revenue", "alias": "revenue"}
                ],
                "filters": [],
                "sort": [{"field": "revenue", "direction": "desc"}],
                "limit": 100,
                "is_aggregate": True,
            },
            "compiled_sql": "SELECT region, SUM(revenue) AS revenue FROM orders GROUP BY region",
            "result_name": "regional_revenue",
            "rows": len(rows),
            "truncated": False,
            "result_completeness": "complete",
        },
        {
            "kind": "validation",
            "purpose": "核对区域收入",
            "result_name": "regional_revenue",
            "profile": {
                "materialized_rows": len(rows),
                "columns": ["region", "revenue"],
                "keys": {"region": {"unique": len(rows)}},
                "numeric": {"revenue": {"count": len(rows)}},
                "truncated": False,
                "source_refs": [source_ref],
            },
        },
    ]
    run = AnalysisRun(
        project_id=project.id,
        query=query,
        state="completed",
        stage="completed",
        report={"title": "区域收入变化"},
        checkpoint={"tool_history": tool_history, "resumable": False},
    )
    db.add(run)
    await db.flush()
    db.add(
        ArtifactRecord(
            project_id=project.id,
            analysis_run_id=run.id,
            kind="table",
            title="区域收入",
            payload={"rows": rows, "rows_count": len(rows), "sampled": False},
            technical_details={"result_name": "regional_revenue"},
        )
    )
    await db.commit()
    return project, source, run


async def _create(client: AsyncClient, project: Project, run: AnalysisRun):
    return await client.post(
        f"/api/v1/projects/{project.id}/standing-analyses",
        json={"analysis_run_id": str(run.id), "materiality": _materiality()},
    )


async def _seed_imported_run(
    db: AsyncSession,
    *,
    project: Project,
) -> AnalysisRun:
    source = ProjectDataSource(
        project_id=project.id,
        kind="file",
        name="orders-next.csv",
        format="csv",
        working_uri="/tmp/orders-next.parquet",
        fingerprint="2" * 64,
        status="ready",
        profile_data={
            "logical_name": "orders",
            "version": 1,
            "is_current": True,
            "schema": {
                "columns": [
                    {"name": "region", "type": "VARCHAR"},
                    {"name": "revenue", "type": "DOUBLE"},
                ]
            },
        },
    )
    db.add(source)
    await db.flush()
    rows = [
        {"region": "华东", "revenue": 120},
        {"region": "华南", "revenue": 90},
    ]
    run = AnalysisRun(
        project_id=project.id,
        query="持续观察区域收入",
        state="completed",
        stage="completed",
        report={"title": "区域收入变化"},
        checkpoint={
            "tool_history": [
                {
                    "kind": "file_sql",
                    "purpose": "汇总区域收入",
                    "result_name": "regional_revenue",
                },
                {
                    "kind": "validation",
                    "purpose": "核对区域收入",
                    "result_name": "regional_revenue",
                    "profile": {
                        "columns": ["region", "revenue"],
                        "keys": {"region": {"unique": 2}},
                        "numeric": {"revenue": {"count": 2}},
                        "materialized_rows": 2,
                        "truncated": False,
                        "source_refs": [
                            {
                                "source_logical_name": "orders",
                                "source_kind": "file",
                            }
                        ],
                    },
                },
            ]
        },
    )
    db.add(run)
    await db.flush()
    db.add(
        ArtifactRecord(
            project_id=project.id,
            analysis_run_id=run.id,
            kind="table",
            title="区域收入",
            payload={"rows": rows, "rows_count": 2, "sampled": False},
            technical_details={"result_name": "regional_revenue"},
        )
    )
    await db.commit()
    return run


@pytest.mark.asyncio
async def test_create_is_idempotent_and_project_isolated(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project, _, run = await _seed_baseline(db_session)
    created = await _create(client, project, run)
    assert created.status_code == 200, created.text
    definition = created.json()["data"]
    assert definition["baseline"]["analysis_run_id"] == str(run.id)
    assert definition["watched_source_roles"] == ["orders"]

    duplicate = await _create(client, project, run)
    assert duplicate.status_code == 200
    assert duplicate.json()["data"]["baseline"] == definition["baseline"]

    other = Project(name="另一个项目")
    db_session.add(other)
    await db_session.commit()
    isolated = await _create(client, other, run)
    assert isolated.status_code == 404

    listed = await client.get(f"/api/v1/projects/{project.id}/standing-analyses")
    assert [item["id"] for item in listed.json()["data"]] == [definition["id"]]


@pytest.mark.asyncio
async def test_create_accepts_the_typed_run_that_was_just_saved_as_a_system_playbook(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project, _, run = await _seed_system_capture_baseline(db_session)
    captured = await client.post(
        f"/api/v1/projects/{project.id}/analysis-playbooks",
        json={"analysis_run_id": str(run.id)},
    )
    assert captured.status_code == 200, captured.text
    assert captured.json()["data"]["execution_mode"] == "system_structured_query"

    created = await _create(client, project, run)

    assert created.status_code == 200, created.text
    assert created.json()["data"]["baseline"]["analysis_run_id"] == str(run.id)


@pytest.mark.asyncio
async def test_create_rejects_a_typed_baseline_that_no_longer_matches_the_saved_plan(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project, _, run = await _seed_system_capture_baseline(db_session)
    captured = await client.post(
        f"/api/v1/projects/{project.id}/analysis-playbooks",
        json={"analysis_run_id": str(run.id)},
    )
    assert captured.status_code == 200, captured.text

    checkpoint = deepcopy(run.checkpoint)
    checkpoint["tool_history"][0]["query_plan"]["limit"] = 99
    run.checkpoint = checkpoint
    await db_session.commit()

    rejected = await _create(client, project, run)

    assert rejected.status_code == 422
    assert "没有重新执行" in rejected.json()["detail"]


@pytest.mark.asyncio
async def test_create_rejects_sampled_table(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project, _, run = await _seed_baseline(db_session, sampled=True)
    response = await _create(client, project, run)
    assert response.status_code == 422
    assert "未抽样" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_rejects_a_result_after_its_source_has_changed(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project, source, run = await _seed_baseline(db_session)
    source.fingerprint = "2" * 64
    source.profile_data = {**source.profile_data, "version": 2}
    await db_session.commit()

    response = await _create(client, project, run)

    assert response.status_code == 409
    assert "调查完成后已经变化" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_rejects_a_materiality_metric_outside_the_result(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project, _, run = await _seed_baseline(db_session)
    materiality = _materiality()
    materiality["rules"][0]["metric"] = "revnue"

    response = await client.post(
        f"/api/v1/projects/{project.id}/standing-analyses",
        json={"analysis_run_id": str(run.id), "materiality": materiality},
    )

    assert response.status_code == 422
    assert "revnue" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_requires_the_matching_golden_pass_marker(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project, _, run = await _seed_baseline(db_session)
    extra_data = dict(project.extra_data or {})
    extra_data["golden_scenarios"] = [
        {
            "version": 1,
            "id": "0123456789abcdefabcd",
            "query_key": normalize_query_key(run.query),
        }
    ]
    project.extra_data = extra_data
    await db_session.commit()

    rejected = await _create(client, project, run)
    assert rejected.status_code == 422
    history = list(run.checkpoint["tool_history"])
    stale_marker = {
        "kind": "golden_regression_validation",
        "status": "passed",
        "contract_id": "0123456789abcdefabcd",
        "result_name": "regional_revenue",
    }
    run.checkpoint = {**run.checkpoint, "tool_history": [stale_marker, *history]}
    await db_session.commit()
    still_rejected = await _create(client, project, run)
    assert still_rejected.status_code == 422

    history.append(stale_marker)
    run.checkpoint = {**run.checkpoint, "tool_history": history}
    await db_session.commit()
    accepted = await _create(client, project, run)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["data"]["baseline"]["validation_evidence"] == [
        "validation:regional_revenue",
        "golden:0123456789abcdefabcd",
    ]


@pytest.mark.asyncio
async def test_prepare_same_token_is_quiet_and_force_is_idempotent(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project, _, run = await _seed_baseline(db_session)
    definition = (await _create(client, project, run)).json()["data"]
    url = f"/api/v1/projects/{project.id}/standing-analyses/{definition['id']}/prepare-run"

    quiet = await client.post(url, json={"trigger": "app_start_overdue"})
    assert quiet.status_code == 200, quiet.text
    assert quiet.json()["data"]["outcome"] == "no_change"
    run_count = await db_session.scalar(select(func.count()).select_from(AnalysisRun))
    assert run_count == 1

    request_id = uuid4()
    first = await client.post(
        url,
        json={"trigger": "manual", "force": True, "request_id": str(request_id)},
    )
    second = await client.post(
        url,
        json={"trigger": "manual", "force": True, "request_id": str(request_id)},
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["data"]["outcome"] == "prepared"
    assert second.json()["data"]["outcome"] == "already_running"
    assert first.json()["data"]["run_id"] == second.json()["data"]["run_id"]
    run_count = await db_session.scalar(select(func.count()).select_from(AnalysisRun))
    assert run_count == 2


@pytest.mark.asyncio
async def test_overdue_app_open_prepares_a_rerun_even_when_the_input_token_is_unchanged(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project, _, run = await _seed_baseline(db_session)
    definition = (await _create(client, project, run)).json()["data"]
    await db_session.refresh(project)
    extra_data = dict(project.extra_data or {})
    standing = dict(extra_data["standing_analyses"][0])
    baseline = dict(standing["baseline"])
    baseline["accepted_at"] = (datetime.now(UTC) - timedelta(minutes=6)).isoformat()
    standing["baseline"] = baseline
    standing["overdue_after_seconds"] = 300
    extra_data["standing_analyses"] = [standing]
    project.extra_data = extra_data
    await db_session.commit()

    response = await client.post(
        f"/api/v1/projects/{project.id}/standing-analyses/{definition['id']}/prepare-run",
        json={"trigger": "app_start_overdue"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["outcome"] == "prepared"
    assert response.json()["data"]["input_token"] == definition["baseline"]["input_token"]


@pytest.mark.asyncio
async def test_active_patch_keeps_the_current_claim_and_rejects_rule_changes(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project, _, run = await _seed_baseline(db_session)
    definition = (await _create(client, project, run)).json()["data"]
    base = f"/api/v1/projects/{project.id}/standing-analyses/{definition['id']}"
    prepared = await client.post(
        f"{base}/prepare-run",
        json={"trigger": "manual", "force": True, "request_id": str(uuid4())},
    )
    claim = prepared.json()["data"]["standing_analysis"]["in_flight"]

    kept = await client.patch(base, json={"state": "active", "name": "区域收入提醒"})
    blocked = await client.patch(base, json={"materiality": _materiality()})

    assert kept.status_code == 200, kept.text
    assert kept.json()["data"]["in_flight"] == claim
    assert blocked.status_code == 409


@pytest.mark.asyncio
async def test_pending_replacement_and_playbook_shape_drift_stop_before_run(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project, source, run = await _seed_baseline(db_session)
    definition = (await _create(client, project, run)).json()["data"]
    baseline = definition["baseline"]
    pending = ProjectDataSource(
        project_id=project.id,
        kind="file",
        name="orders-august.csv",
        format="csv",
        status="needs_confirmation",
        profile_data={
            "logical_name": "orders",
            "version": 2,
            "is_current": False,
            "replacement_of": str(source.id),
            "activation_state": "pending_confirmation",
            "schema": source.profile_data["schema"],
        },
    )
    db_session.add(pending)
    await db_session.commit()
    url = f"/api/v1/projects/{project.id}/standing-analyses/{definition['id']}/prepare-run"
    attention = await client.post(url, json={"trigger": "source_version"})
    assert attention.status_code == 200, attention.text
    attention_data = attention.json()["data"]
    assert attention_data["outcome"] == "needs_attention"
    assert attention_data["attention_reason_code"] == "standing_source_pending_confirmation"
    assert attention_data["attention_reason_params"] == {"source": "orders"}
    assert attention_data["standing_analysis"]["attention_reason_code"] == (
        "standing_source_pending_confirmation"
    )
    assert attention_data["standing_analysis"]["baseline"] == baseline
    repeated = (await client.post(url, json={"trigger": "manual"})).json()["data"]
    assert repeated["attention_reason_code"] == "standing_source_pending_confirmation"
    assert repeated["attention_reason_params"] == {"source": "orders"}
    run_count = await db_session.scalar(select(func.count()).select_from(AnalysisRun))
    assert run_count == 1


@pytest.mark.asyncio
async def test_playbook_shape_drift_stops_without_moving_baseline(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project, _, run = await _seed_baseline(db_session)
    definition = (await _create(client, project, run)).json()["data"]
    baseline = definition["baseline"]
    extra_data = dict(project.extra_data or {})
    playbook = dict(extra_data["analysis_playbooks"][0])
    playbook["shape_hash"] = "b" * 64
    extra_data["analysis_playbooks"] = [playbook]
    project.extra_data = extra_data
    await db_session.commit()

    url = f"/api/v1/projects/{project.id}/standing-analyses/{definition['id']}/prepare-run"
    response = await client.post(url, json={"trigger": "app_start_overdue"})
    assert response.status_code == 200, response.text
    prepared = response.json()["data"]
    assert prepared["outcome"] == "needs_attention"
    assert prepared["attention_reason_code"] == "standing_playbook_changed"
    assert prepared["attention_reason_params"] == {}
    assert prepared["standing_analysis"]["baseline"] == baseline
    run_count = await db_session.scalar(select(func.count()).select_from(AnalysisRun))
    assert run_count == 1


@pytest.mark.asyncio
async def test_pause_returns_without_creating_a_run(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project, _, run = await _seed_baseline(db_session)
    definition = (await _create(client, project, run)).json()["data"]
    base = f"/api/v1/projects/{project.id}/standing-analyses/{definition['id']}"
    paused = await client.patch(base, json={"state": "paused"})
    assert paused.status_code == 200, paused.text
    prepared = await client.post(f"{base}/prepare-run", json={"trigger": "manual"})
    assert prepared.json()["data"]["outcome"] == "paused"
    run_count = await db_session.scalar(select(func.count()).select_from(AnalysisRun))
    assert run_count == 1


@pytest.mark.asyncio
async def test_pause_retires_an_unstarted_prepared_claim(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project, _, run = await _seed_baseline(db_session)
    definition = (await _create(client, project, run)).json()["data"]
    base = f"/api/v1/projects/{project.id}/standing-analyses/{definition['id']}"
    prepared = await client.post(
        f"{base}/prepare-run",
        json={"trigger": "manual", "force": True, "request_id": str(uuid4())},
    )
    claimed_run_id = UUID(prepared.json()["data"]["run_id"])

    paused = await client.patch(base, json={"state": "paused"})
    assert paused.status_code == 200, paused.text
    assert paused.json()["data"]["in_flight"] is None
    claimed_run = await db_session.get(AnalysisRun, claimed_run_id)
    assert claimed_run is not None
    assert claimed_run.state == "needs_attention"
    assert claimed_run.stage == "needs_attention"
    assert claimed_run.checkpoint["reason"] == "standing_analysis_paused"
    assert claimed_run.checkpoint["resumable"] is False


@pytest.mark.asyncio
async def test_bundle_scrubs_snapshot_rows_and_imports_a_paused_definition(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project, _, run = await _seed_baseline(db_session)
    await _create(client, project, run)

    exported = await client.get(f"/api/v1/projects/{project.id}/export")
    assert exported.status_code == 200, exported.text
    bundle = exported.json()["data"]
    portable = bundle["standing_analyses"][0]
    assert portable["state"] == "paused"
    assert portable["baseline"] is None
    assert portable["in_flight"] is None
    assert portable["last_evaluated_token"] is None
    assert "rows" not in str(portable)

    imported = await client.post("/api/v1/projects/import", json=bundle)
    assert imported.status_code == 200, imported.text
    imported_id = imported.json()["data"]["id"]
    definitions = await client.get(f"/api/v1/projects/{imported_id}/standing-analyses")
    assert definitions.status_code == 200, definitions.text
    restored = definitions.json()["data"][0]
    assert restored["project_id"] == imported_id
    assert restored["state"] == "paused"
    assert restored["baseline"] is None

    imported_project = await db_session.get(Project, UUID(imported_id))
    assert imported_project is not None
    next_run = await _seed_imported_run(db_session, project=imported_project)
    rehydrated = await _create(client, imported_project, next_run)
    assert rehydrated.status_code == 200, rehydrated.text
    active = rehydrated.json()["data"]
    assert active["id"] == restored["id"]
    assert active["state"] == "active"
    assert active["baseline"]["analysis_run_id"] == str(next_run.id)
    relisted = await client.get(f"/api/v1/projects/{imported_id}/standing-analyses")
    assert len(relisted.json()["data"]) == 1
