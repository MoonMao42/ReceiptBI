"""Independent semantic validation jobs stay revision-bound and model-free."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pandas as pd
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.api.v1 import projects as projects_api
from app.db.tables import (
    AnalysisRun,
    Base,
    Connection,
    Project,
    ProjectDataSource,
    SemanticEntry,
    SemanticEntryRevision,
    SemanticValidationJob,
    SemanticValidationJobItem,
)
from app.services import semantic_validation
from app.services.database import QueryResult
from app.services.result_filters import stable_schema_signature
from app.services.semantic_revisions import append_semantic_revision
from app.services.semantic_validation import (
    queue_semantic_validation_job,
    recover_semantic_validation_jobs,
    retry_semantic_validation_job,
    run_semantic_validation_job,
)


def _binding(
    *,
    logical_name: str,
    source_kind: str,
    table: str,
    column: str,
    canonical_type: str,
    signature: str,
) -> dict:
    return {
        "source_logical_name": logical_name,
        "source_kind": source_kind,
        "table_or_view": table,
        "action_column": column,
        "canonical_type": canonical_type,
        "schema_signature": signature,
    }


async def _candidate(
    db: AsyncSession,
    *,
    project_id,
    key: str,
    entry_type: str,
    definition: dict,
) -> SemanticEntry:
    entry = SemanticEntry(
        project_id=project_id,
        key=key,
        value=definition.get("business_name") or key,
        entry_type=entry_type,
        state="candidate",
        confidence=0.7,
        definition=definition,
        validity="unverified",
        execution_state="needs_validation",
        execution_details={"version": 1, "status": "needs_validation"},
        evidence=[],
        source="inferred",
    )
    db.add(entry)
    await db.flush()
    await append_semantic_revision(
        db,
        entry,
        mutation_kind="candidate_created",
        actor_source="inferred",
        expected_active_revision_id=None,
    )
    return entry


@pytest.mark.asyncio
async def test_queue_api_returns_job_without_chat_prompt_or_analysis_run(
    client,
    db_session: AsyncSession,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    working = tmp_path / "sales.parquet"
    pd.DataFrame({"amount": [10.0, 20.0]}).to_parquet(working, index=False)
    columns = [{"name": "amount", "dtype": "float64"}]
    signature = stable_schema_signature(columns)
    project = Project(name="独立验证 API")
    db_session.add(project)
    await db_session.flush()
    source = ProjectDataSource(
        project_id=project.id,
        kind="file",
        name="销售文件",
        format="parquet",
        working_uri=str(working),
        status="ready",
        profile_data={
            "logical_name": "销售文件",
            "is_current": True,
            "schema": {"columns": columns},
            "preanalysis": {"candidate_roles": []},
        },
    )
    db_session.add(source)
    entry = await _candidate(
        db_session,
        project_id=project.id,
        key="recommendation:metric:amount",
        entry_type="metric",
        definition={
            "version": 1,
            "kind": "aggregate_metric",
            "operation": "sum",
            "source": _binding(
                logical_name="销售文件",
                source_kind="file",
                table="销售文件",
                column="amount",
                canonical_type="number",
                signature=signature,
            ),
            "null_policy": "ignore",
            "business_name": "销售额",
            "example_questions": [],
        },
    )
    await db_session.commit()

    async def leave_queued(*_args, **_kwargs):
        return None

    monkeypatch.setattr(projects_api, "run_semantic_validation_job", leave_queued)
    before_runs = int(await db_session.scalar(select(func.count()).select_from(AnalysisRun)) or 0)
    response = await client.post(
        f"/api/v1/projects/{project.id}/knowledge/batch",
        json={
            "action": "queue_validation",
            "items": [
                {
                    "entry_id": str(entry.id),
                    "expected_active_revision_id": str(entry.active_revision_id),
                }
            ],
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["validation_job_id"]
    assert data["validation_status"] == "queued"
    assert "validation_prompt" not in data
    assert "validation_selection" not in data
    assert data["items"][0]["allowed_actions"] == []
    assert (
        int(await db_session.scalar(select(func.count()).select_from(AnalysisRun)) or 0)
        == before_runs
    )

    job_response = await client.get(
        f"/api/v1/projects/{project.id}/knowledge/validation-jobs/{data['validation_job_id']}"
    )
    assert job_response.status_code == 200
    assert job_response.json()["data"]["progress"] == {
        "total": 1,
        "queued": 1,
        "running": 0,
        "verified": 0,
        "blocked": 0,
        "failed": 0,
    }


@pytest.mark.asyncio
async def test_validation_response_hides_worker_diagnostics(
    db_session: AsyncSession,
):
    project = Project(name="公开验证结果")
    db_session.add(project)
    await db_session.flush()
    entry = await _candidate(
        db_session,
        project_id=project.id,
        key="recommendation:metric:public-response",
        entry_type="metric",
        definition={"version": 1, "kind": "aggregate_metric", "business_name": "销售额"},
    )
    job = await queue_semantic_validation_job(
        db_session,
        project_id=project.id,
        entries=[entry],
        reason=None,
    )
    item = await db_session.scalar(
        select(SemanticValidationJobItem).where(SemanticValidationJobItem.job_id == job.id)
    )
    assert item is not None
    item.status = "failed"
    item.code = "semantic_validation_query_failed"
    item.facts = {
        "total_rows": 12,
        "error_type": "RuntimeError",
        "_worker_attempt": 2,
    }
    item.details = {
        "version": 1,
        "code": "semantic_validation_query_failed",
        "message": "验证没有完成。",
        "lease_owner": "worker-secret",
        "traceback": "private stack",
    }
    await db_session.flush()

    response = await semantic_validation.semantic_validation_job_response(
        db_session,
        job,
    )

    assert response.items[0].facts == {"total_rows": 12}
    assert response.items[0].details == {
        "version": 1,
        "code": "semantic_validation_query_failed",
        "message": "验证没有完成。",
    }


@pytest.mark.asyncio
async def test_validation_job_verifies_metric_and_blocks_empty_dimension(
    db_session: AsyncSession,
    tmp_path,
):
    working = tmp_path / "mixed.parquet"
    pd.DataFrame({"amount": [10.0, 20.0], "empty_group": [None, None]}).to_parquet(
        working, index=False
    )
    columns = [
        {"name": "amount", "dtype": "float64"},
        {"name": "empty_group", "dtype": "object"},
    ]
    signature = stable_schema_signature(columns)
    project = Project(name="逐项验证")
    db_session.add(project)
    await db_session.flush()
    db_session.add(
        ProjectDataSource(
            project_id=project.id,
            kind="file",
            name="经营文件",
            format="parquet",
            working_uri=str(working),
            status="ready",
            profile_data={
                "logical_name": "经营文件",
                "is_current": True,
                "schema": {"columns": columns},
            },
        )
    )
    metric = await _candidate(
        db_session,
        project_id=project.id,
        key="recommendation:metric:amount",
        entry_type="metric",
        definition={
            "version": 1,
            "kind": "aggregate_metric",
            "operation": "sum",
            "source": _binding(
                logical_name="经营文件",
                source_kind="file",
                table="经营文件",
                column="amount",
                canonical_type="number",
                signature=signature,
            ),
            "null_policy": "ignore",
            "business_name": "销售额",
            "example_questions": [],
        },
    )
    dimension = await _candidate(
        db_session,
        project_id=project.id,
        key="recommendation:dimension:empty",
        entry_type="dimension",
        definition={
            "version": 1,
            "kind": "dimension",
            "role": "category",
            "source": _binding(
                logical_name="经营文件",
                source_kind="file",
                table="经营文件",
                column="empty_group",
                canonical_type="text",
                signature=signature,
            ),
            "business_name": "空分组",
            "example_questions": [],
        },
    )
    await db_session.flush()
    job = await queue_semantic_validation_job(
        db_session,
        project_id=project.id,
        entries=[metric, dimension],
        reason=None,
    )
    job_id = job.id
    metric_id = metric.id
    dimension_id = dimension.id
    await db_session.commit()

    factory = async_sessionmaker(
        db_session.bind,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    await run_semantic_validation_job(job_id, factory)

    db_session.expire_all()
    stored_job = await db_session.get(SemanticValidationJob, job_id)
    assert stored_job is not None and stored_job.status == "completed"
    item_result = await db_session.execute(
        select(SemanticValidationJobItem).where(SemanticValidationJobItem.job_id == job_id)
    )
    items = {item.semantic_entry_id: item for item in item_result.scalars()}
    assert items[metric_id].status == "verified"
    assert items[metric_id].code == "semantic_validation_verified"
    assert items[metric_id].facts["aggregate_value"] == 30.0
    assert items[dimension_id].status == "blocked"
    assert items[dimension_id].code == "dimension_probe_has_no_values"


@pytest.mark.asyncio
async def test_validation_job_blocks_revision_drift_without_overwriting_new_head(
    db_session: AsyncSession,
    tmp_path,
):
    working = tmp_path / "drift.parquet"
    pd.DataFrame({"amount": [3.0]}).to_parquet(working, index=False)
    columns = [{"name": "amount", "dtype": "float64"}]
    signature = stable_schema_signature(columns)
    project = Project(name="修订漂移")
    db_session.add(project)
    await db_session.flush()
    db_session.add(
        ProjectDataSource(
            project_id=project.id,
            kind="file",
            name="漂移文件",
            format="parquet",
            working_uri=str(working),
            status="ready",
            profile_data={
                "logical_name": "漂移文件",
                "is_current": True,
                "schema": {"columns": columns},
            },
        )
    )
    entry = await _candidate(
        db_session,
        project_id=project.id,
        key="recommendation:metric:drift",
        entry_type="metric",
        definition={
            "version": 1,
            "kind": "aggregate_metric",
            "operation": "sum",
            "source": _binding(
                logical_name="漂移文件",
                source_kind="file",
                table="漂移文件",
                column="amount",
                canonical_type="number",
                signature=signature,
            ),
            "null_policy": "ignore",
            "business_name": "原指标",
            "example_questions": [],
        },
    )
    job = await queue_semantic_validation_job(
        db_session,
        project_id=project.id,
        entries=[entry],
        reason=None,
    )
    job_id = job.id
    entry_id = entry.id
    queued_revision_id = entry.active_revision_id
    entry.value = "用户更新后的指标"
    await append_semantic_revision(
        db_session,
        entry,
        mutation_kind="updated",
        actor_source="user",
        expected_active_revision_id=queued_revision_id,
    )
    new_revision_id = entry.active_revision_id
    await db_session.commit()

    factory = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)
    await run_semantic_validation_job(job_id, factory)

    db_session.expire_all()
    stored = await db_session.get(SemanticEntry, entry_id)
    item = await db_session.scalar(
        select(SemanticValidationJobItem).where(SemanticValidationJobItem.job_id == job_id)
    )
    assert stored is not None
    assert stored.active_revision_id == new_revision_id
    assert stored.value == "用户更新后的指标"
    assert item is not None and item.status == "blocked"
    assert item.code == "semantic_revision_drift"


@pytest.mark.asyncio
async def test_online_validation_timeout_is_blocked_with_stable_code(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    columns = [{"name": "amount", "type": "NUMERIC"}]
    signature = stable_schema_signature(columns)
    project = Project(name="在线超时")
    connection = Connection(
        name="慢数据库",
        driver="postgresql",
        host="db.example.test",
        database_name="warehouse",
    )
    db_session.add_all([project, connection])
    await db_session.flush()
    db_session.add(
        ProjectDataSource(
            project_id=project.id,
            connection_id=connection.id,
            kind="connection",
            name="慢数据库",
            status="ready",
            profile_data={
                "logical_name": "慢数据库",
                "is_current": True,
                "tables": [{"name": "orders", "columns": columns}],
            },
        )
    )
    entry = await _candidate(
        db_session,
        project_id=project.id,
        key="recommendation:metric:slow",
        entry_type="metric",
        definition={
            "version": 1,
            "kind": "aggregate_metric",
            "operation": "sum",
            "source": _binding(
                logical_name="慢数据库",
                source_kind="connection",
                table="orders",
                column="amount",
                canonical_type="number",
                signature=signature,
            ),
            "null_policy": "ignore",
            "business_name": "销售额",
            "example_questions": [],
        },
    )
    job = await queue_semantic_validation_job(
        db_session,
        project_id=project.id,
        entries=[entry],
        reason=None,
    )
    job_id = job.id
    await db_session.commit()

    class Adapter:
        @staticmethod
        def quote_identifier(value):
            return f'"{value}"'

    class SlowManager:
        _adapter = Adapter()

        @staticmethod
        def execute_query(*_args, **_kwargs):
            time.sleep(0.1)
            return QueryResult(data=[{"total_rows": 1}], rows_count=1)

    monkeypatch.setattr(
        semantic_validation,
        "create_database_manager",
        lambda _config: SlowManager(),
    )
    monkeypatch.setattr(semantic_validation, "VALIDATION_TIMEOUT_SECONDS", 0.01)
    factory = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)
    await run_semantic_validation_job(job_id, factory)

    db_session.expire_all()
    item = await db_session.scalar(
        select(SemanticValidationJobItem).where(SemanticValidationJobItem.job_id == job_id)
    )
    assert item is not None and item.status == "blocked"
    assert item.code == "semantic_validation_timeout"
    assert item.facts == {"timeout_seconds": 0.01}


@pytest.mark.asyncio
async def test_startup_recovery_requeues_only_interrupted_validation_items(
    db_session: AsyncSession,
):
    project = Project(name="验证恢复")
    db_session.add(project)
    await db_session.flush()
    first = await _candidate(
        db_session,
        project_id=project.id,
        key="recommendation:metric:recovered",
        entry_type="metric",
        definition={"version": 1, "kind": "aggregate_metric", "business_name": "恢复项"},
    )
    second = await _candidate(
        db_session,
        project_id=project.id,
        key="recommendation:metric:preserved",
        entry_type="metric",
        definition={"version": 1, "kind": "aggregate_metric", "business_name": "保留项"},
    )
    job = await queue_semantic_validation_job(
        db_session,
        project_id=project.id,
        entries=[first, second],
        reason=None,
    )
    await db_session.flush()
    items = list(
        (
            await db_session.execute(
                select(SemanticValidationJobItem)
                .where(SemanticValidationJobItem.job_id == job.id)
                .order_by(
                    SemanticValidationJobItem.created_at,
                    SemanticValidationJobItem.id,
                )
            )
        ).scalars()
    )
    job.status = "running"
    job.details = {
        **dict(job.details or {}),
        "lease_owner": "dead-worker",
        "lease_expires_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
    }
    items[0].status = "running"
    items[0].started_at = datetime.now(UTC)
    items[1].status = "blocked"
    items[1].code = "semantic_definition_unsupported"
    items[1].completed_at = datetime.now(UTC)
    await db_session.commit()

    recovered = await recover_semantic_validation_jobs(db_session)
    await db_session.commit()

    assert recovered == [job.id]
    assert job.status == "queued"
    assert job.details["code"] == "semantic_validation_recovered"
    assert job.details["lease_owner"] is None
    assert items[0].status == "queued"
    assert items[0].started_at is None
    assert items[1].status == "blocked"
    assert items[1].code == "semantic_definition_unsupported"


@pytest.mark.asyncio
async def test_startup_recovery_keeps_a_live_validation_lease(
    db_session: AsyncSession,
):
    project = Project(name="验证租约仍健康")
    db_session.add(project)
    await db_session.flush()
    entry = await _candidate(
        db_session,
        project_id=project.id,
        key="recommendation:metric:live-lease",
        entry_type="metric",
        definition={"version": 1, "kind": "aggregate_metric", "business_name": "健康项"},
    )
    job = await queue_semantic_validation_job(
        db_session,
        project_id=project.id,
        entries=[entry],
        reason=None,
    )
    await db_session.flush()
    item = await db_session.scalar(
        select(SemanticValidationJobItem).where(SemanticValidationJobItem.job_id == job.id)
    )
    assert item is not None
    started_at = datetime.now(UTC)
    job.status = "running"
    job.details = {
        **dict(job.details or {}),
        "lease_owner": "active-worker",
        "lease_expires_at": (started_at + timedelta(seconds=30)).isoformat(),
    }
    item.status = "running"
    item.started_at = started_at
    await db_session.commit()

    recovered = await recover_semantic_validation_jobs(db_session)
    await db_session.commit()

    assert recovered == []
    assert job.status == "running"
    assert job.details["lease_owner"] == "active-worker"
    assert item.status == "running"
    assert item.started_at == started_at


@pytest.mark.asyncio
async def test_validation_job_claim_is_compare_and_set(
    db_session: AsyncSession,
):
    project = Project(name="验证抢占")
    db_session.add(project)
    await db_session.flush()
    entry = await _candidate(
        db_session,
        project_id=project.id,
        key="recommendation:metric:claim",
        entry_type="metric",
        definition={"version": 1, "kind": "aggregate_metric", "business_name": "抢占项"},
    )
    job = await queue_semantic_validation_job(
        db_session,
        project_id=project.id,
        entries=[entry],
        reason=None,
    )
    job_id = job.id
    await db_session.commit()
    factory = async_sessionmaker(
        db_session.bind,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    first = await semantic_validation._claim_validation_job(
        factory,
        job_id=job_id,
        worker_id="worker-a",
    )
    second = await semantic_validation._claim_validation_job(
        factory,
        job_id=job_id,
        worker_id="worker-b",
    )

    assert first is not None and len(first) == 1
    assert second is None
    db_session.expire_all()
    stored = await db_session.get(SemanticValidationJob, job_id)
    assert stored is not None and stored.status == "running"
    assert stored.details["lease_owner"] == "worker-a"


@pytest.mark.asyncio
async def test_retry_reclaims_expired_active_job_without_losing_progress(
    db_session: AsyncSession,
):
    project = Project(name="过期验证重试")
    db_session.add(project)
    await db_session.flush()
    entry = await _candidate(
        db_session,
        project_id=project.id,
        key="recommendation:metric:stale",
        entry_type="metric",
        definition={"version": 1, "kind": "aggregate_metric", "business_name": "过期项"},
    )
    job = await queue_semantic_validation_job(
        db_session,
        project_id=project.id,
        entries=[entry],
        reason=None,
    )
    await db_session.flush()
    item = (
        await db_session.execute(
            select(SemanticValidationJobItem).where(SemanticValidationJobItem.job_id == job.id)
        )
    ).scalar_one()
    job.status = "running"
    job.details = {
        **dict(job.details or {}),
        "lease_owner": "dead-worker",
        "lease_expires_at": (datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
    }
    item.status = "running"
    item.started_at = datetime.now(UTC)
    await db_session.commit()

    with pytest.raises(
        semantic_validation.SemanticValidationQueueError,
        match="验证仍在执行",
    ) as active_error:
        await retry_semantic_validation_job(
            db_session,
            project_id=project.id,
            job_id=job.id,
        )
    assert active_error.value.code == "semantic_validation_job_active"
    assert active_error.value.details == {}
    job.details = {
        **dict(job.details or {}),
        "lease_expires_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
    }
    await db_session.commit()

    retried = await retry_semantic_validation_job(
        db_session,
        project_id=project.id,
        job_id=job.id,
    )
    await db_session.commit()

    assert retried.id == job.id
    assert retried.status == "queued"
    assert retried.details["lease_owner"] is None
    assert item.status == "queued"
    assert item.started_at is None


@pytest.mark.asyncio
async def test_retry_endpoint_creates_one_new_revision_pinned_job_for_failed_items(
    client,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    project = Project(name="失败验证重试")
    db_session.add(project)
    await db_session.flush()
    entry = await _candidate(
        db_session,
        project_id=project.id,
        key="recommendation:metric:retry",
        entry_type="metric",
        definition={"version": 1, "kind": "aggregate_metric", "business_name": "重试项"},
    )
    job = await queue_semantic_validation_job(
        db_session,
        project_id=project.id,
        entries=[entry],
        reason=None,
    )
    project_id = project.id
    original_job_id = job.id
    await db_session.commit()

    async def fail_validation(*_args, **_kwargs):
        raise RuntimeError("temporary source failure")

    monkeypatch.setattr(semantic_validation, "_validate_entry", fail_validation)
    factory = async_sessionmaker(
        db_session.bind,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    await run_semantic_validation_job(original_job_id, factory)
    db_session.expire_all()
    failed_item = (
        await db_session.execute(
            select(SemanticValidationJobItem).where(
                SemanticValidationJobItem.job_id == original_job_id
            )
        )
    ).scalar_one()
    assert failed_item.status == "failed"
    failed_revision_id = failed_item.semantic_revision_id
    failed_definition_hash = failed_item.definition_hash
    failed_response = await client.get(
        f"/api/v1/projects/{project_id}/knowledge/validation-jobs/{original_job_id}"
    )
    assert failed_response.status_code == 200, failed_response.text
    assert failed_response.json()["data"]["items"][0]["facts"] == {}
    assert "RuntimeError" not in failed_response.text
    assert "temporary source failure" not in failed_response.text

    async def leave_queued(*_args, **_kwargs):
        return None

    monkeypatch.setattr(projects_api, "run_semantic_validation_job", leave_queued)
    response = await client.post(
        f"/api/v1/projects/{project_id}/knowledge/validation-jobs/{original_job_id}/retry"
    )

    assert response.status_code == 202, response.text
    payload = response.json()["data"]
    assert payload["id"] != str(original_job_id)
    assert payload["status"] == "queued"
    assert payload["progress"]["queued"] == 1
    retry_job_id = payload["id"]

    db_session.expire_all()
    original_job = await db_session.get(SemanticValidationJob, original_job_id)
    retry_item = (
        await db_session.execute(
            select(SemanticValidationJobItem).where(
                SemanticValidationJobItem.job_id == UUID(retry_job_id)
            )
        )
    ).scalar_one()
    assert original_job is not None
    assert original_job.details["retry_job_id"] == retry_job_id
    assert retry_item.semantic_revision_id != failed_revision_id
    assert retry_item.definition_hash == failed_definition_hash

    duplicate = await client.post(
        f"/api/v1/projects/{project_id}/knowledge/validation-jobs/{original_job_id}/retry"
    )
    assert duplicate.status_code == 202, duplicate.text
    assert duplicate.json()["data"]["id"] == retry_job_id


@pytest.mark.asyncio
async def test_terminal_retry_is_idempotent_across_sqlite_sessions(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'semantic-retry.db'}",
        connect_args={"timeout": 1},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    try:
        async with factory() as setup_db:
            project = Project(name="并发验证重试")
            setup_db.add(project)
            await setup_db.flush()
            entry = await _candidate(
                setup_db,
                project_id=project.id,
                key="recommendation:metric:concurrent-retry",
                entry_type="metric",
                definition={
                    "version": 1,
                    "kind": "aggregate_metric",
                    "business_name": "并发项",
                },
            )
            job = await queue_semantic_validation_job(
                setup_db,
                project_id=project.id,
                entries=[entry],
                reason=None,
            )
            item = await setup_db.scalar(
                select(SemanticValidationJobItem).where(SemanticValidationJobItem.job_id == job.id)
            )
            assert item is not None
            job.status = "completed"
            job.completed_at = datetime.now(UTC)
            item.status = "failed"
            item.code = "semantic_validation_query_failed"
            item.completed_at = datetime.now(UTC)
            project_id = project.id
            original_job_id = job.id
            await setup_db.commit()

        original_queue = semantic_validation.queue_semantic_validation_job
        arrivals = 0
        both_ready = asyncio.Event()

        async def synchronized_queue(*args, **kwargs):
            nonlocal arrivals
            arrivals += 1
            if arrivals == 2:
                both_ready.set()
            await asyncio.wait_for(both_ready.wait(), timeout=2)
            return await original_queue(*args, **kwargs)

        monkeypatch.setattr(
            semantic_validation,
            "queue_semantic_validation_job",
            synchronized_queue,
        )

        async def invoke_retry() -> UUID:
            async with factory() as retry_db:
                retry_job = await retry_semantic_validation_job(
                    retry_db,
                    project_id=project_id,
                    job_id=original_job_id,
                )
                await retry_db.commit()
                return retry_job.id

        retry_ids = await asyncio.gather(invoke_retry(), invoke_retry())
        expected_retry_id = semantic_validation._retry_validation_job_id(original_job_id)
        assert retry_ids == [expected_retry_id, expected_retry_id]

        async with factory() as verify_db:
            retry_job_count = int(
                await verify_db.scalar(
                    select(func.count())
                    .select_from(SemanticValidationJob)
                    .where(SemanticValidationJob.requested_by == "retry")
                )
                or 0
            )
            retry_item_count = int(
                await verify_db.scalar(
                    select(func.count())
                    .select_from(SemanticValidationJobItem)
                    .where(SemanticValidationJobItem.job_id == expected_retry_id)
                )
                or 0
            )
            revision_count = int(
                await verify_db.scalar(select(func.count()).select_from(SemanticEntryRevision)) or 0
            )
        assert retry_job_count == 1
        assert retry_item_count == 1
        assert revision_count == 3
    finally:
        await engine.dispose()
