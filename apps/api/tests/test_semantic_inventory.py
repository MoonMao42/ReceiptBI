"""Durable database-wide semantic inventory behavior."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.tables import (
    AppSettings,
    Connection,
    Project,
    ProjectDataSource,
    SemanticEntry,
    SemanticInventoryJob,
    SemanticInventoryJobItem,
)
from app.models.workspace import SemanticInventoryJobRequest
from app.services import semantic_inventory as inventory
from app.services.database_adapters import BoundedRelationIndex
from app.services.semantic_inventory import (
    SemanticInventoryError,
    create_semantic_inventory_job,
    recover_semantic_inventory_jobs,
    request_semantic_inventory_cancel,
    retry_semantic_inventory_job,
    run_semantic_inventory_job,
    semantic_inventory_job_items_response,
    semantic_inventory_job_response,
)
from app.services.semantic_recommendations import SemanticRecommendationBatch


def _relations(count: int) -> list[dict[str, object]]:
    return [
        {
            "schema": "main",
            "name": f"table_{index:03d}",
            "kind": "table",
            "comment": f"业务表 {index:03d}",
        }
        for index in range(count)
    ]


@pytest.mark.asyncio
async def test_relation_discovery_pages_beyond_512_without_row_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relations = _relations(613)
    after_values: list[str | None] = []

    class _DirectoryManager:
        def get_bounded_relation_index(
            self,
            *,
            max_relations: int,
            after: str | None = None,
        ) -> BoundedRelationIndex:
            after_values.append(after)
            start = 0
            if after is not None:
                start = next(
                    index
                    for index, relation in enumerate(relations)
                    if relation["name"] == after
                ) + 1
            page = relations[start : start + max_relations]
            truncated = start + len(page) < len(relations)
            return BoundedRelationIndex(
                relations=[dict(item) for item in page],
                truncated=truncated,
                unread_relations_at_least=int(truncated),
            )

    monkeypatch.setattr(
        inventory,
        "create_database_manager",
        lambda _config: _DirectoryManager(),
    )
    connection = Connection(
        name="large-directory",
        driver="sqlite",
        database_name=":memory:",
        extra_options={},
    )

    snapshot = await inventory._materialize_relation_index(connection)

    assert snapshot["complete"] is True
    assert snapshot["relations_loaded"] == 613
    assert snapshot["relations_total"] == 613
    assert after_values == [None, "table_499"]


async def _database_source(
    db: AsyncSession,
    *,
    relations: list[dict[str, object]],
    self_analysis_enabled: bool = True,
    preprocessing_enabled: bool = True,
) -> tuple[Project, ProjectDataSource]:
    db.add(
        AppSettings(
            id=1,
            self_analysis_enabled=self_analysis_enabled,
            preprocessing_enabled=preprocessing_enabled,
        )
    )
    project = Project(name="清单测试")
    db.add(project)
    await db.flush()
    connection = Connection(
        name="本地仓库",
        driver="sqlite",
        database_name=":memory:",
        extra_options={},
    )
    db.add(connection)
    await db.flush()
    source = ProjectDataSource(
        project_id=project.id,
        connection_id=connection.id,
        kind="connection",
        name="经营数据库",
        status="ready",
        profile_data={
            "logical_name": "经营仓库",
            "is_current": True,
            "tables": [],
            "preanalysis": {
                "relation_index": {
                    "relations": relations,
                    "relations_loaded": len(relations),
                    "relations_total": len(relations),
                    "relations_total_at_least": len(relations),
                    "complete": True,
                    "truncated": False,
                    "unread_relations_at_least": 0,
                }
            },
        },
    )
    db.add(source)
    await db.commit()
    return project, source


@pytest.mark.asyncio
async def test_structure_job_captures_every_indexed_table_without_global_limit(
    async_engine,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relations = _relations(613)
    project, source = await _database_source(db_session, relations=relations)
    discovery_calls = 0

    async def _fresh_index(_connection, *, heartbeat=None):
        nonlocal discovery_calls
        discovery_calls += 1
        if heartbeat is not None:
            await heartbeat()
        return {
            "relations": relations,
            "relations_loaded": 613,
            "relations_total": 613,
            "relations_total_at_least": 613,
            "complete": True,
            "truncated": False,
            "unread_relations_at_least": 0,
        }

    monkeypatch.setattr(inventory, "_materialize_relation_index", _fresh_index)

    job = await create_semantic_inventory_job(
        db_session,
        project_id=project.id,
        source_id=source.id,
        request=SemanticInventoryJobRequest(locale="zh", depth="structure"),
    )
    await db_session.commit()
    response = await semantic_inventory_job_response(db_session, job)

    assert discovery_calls == 0
    assert response.progress.total == 0
    assert response.status == "queued"

    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    worker_id = "inventory-test-worker"
    assert await inventory._claim_job(
        factory,
        job_id=job.id,
        worker_id=worker_id,
    ) == []
    item_ids = await inventory._prepare_job_items(
        factory,
        job_id=job.id,
        worker_id=worker_id,
    )
    async with factory() as check:
        prepared = await check.get(SemanticInventoryJob, job.id)
        assert prepared is not None
        prepared_response = await semantic_inventory_job_response(check, prepared)
        first_page = await semantic_inventory_job_items_response(
            check,
            prepared,
            limit=100,
        )
        last_page = await semantic_inventory_job_items_response(
            check,
            prepared,
            limit=20,
            after_ordinal=599,
        )

    assert discovery_calls == 1
    assert len(item_ids) == 613
    assert prepared_response.progress.total == 613
    assert prepared_response.progress.queued == 613
    assert prepared_response.tables == []
    assert prepared_response.items == []
    assert first_page.items[0].table == "main.table_000"
    assert first_page.has_more is True
    assert first_page.next_after_ordinal == 99
    assert last_page.items[-1].table == "main.table_612"
    assert last_page.has_more is False


@pytest.mark.asyncio
async def test_sampled_job_respects_preprocessing_setting(
    db_session: AsyncSession,
) -> None:
    project, source = await _database_source(
        db_session,
        relations=_relations(1),
        preprocessing_enabled=False,
    )

    with pytest.raises(SemanticInventoryError) as caught:
        await create_semantic_inventory_job(
            db_session,
            project_id=project.id,
            source_id=source.id,
            request=SemanticInventoryJobRequest(
                locale="zh",
                depth="sampled",
                tables=["main.table_000"],
            ),
        )

    assert caught.value.code == "semantic_inventory_preprocessing_disabled"
    assert caught.value.status_code == 403
    assert "设置" in str(caught.value)


@pytest.mark.asyncio
async def test_bare_table_name_fails_when_captured_index_is_ambiguous(
    async_engine,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relations = [
        {"schema": "sales", "name": "orders", "kind": "table"},
        {"schema": "archive", "name": "orders", "kind": "table"},
    ]
    project, source = await _database_source(
        db_session,
        relations=relations,
    )

    async def _fresh_index(_connection, *, heartbeat=None):
        if heartbeat is not None:
            await heartbeat()
        return {
            "relations": relations,
            "complete": True,
            "truncated": False,
        }

    monkeypatch.setattr(inventory, "_materialize_relation_index", _fresh_index)
    job = await create_semantic_inventory_job(
        db_session,
        project_id=project.id,
        source_id=source.id,
        request=SemanticInventoryJobRequest(
            locale="zh",
            depth="structure",
            tables=["orders"],
        ),
    )
    await db_session.commit()
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    worker_id = "ambiguous-test-worker"
    await inventory._claim_job(factory, job_id=job.id, worker_id=worker_id)
    with pytest.raises(SemanticInventoryError) as caught:
        await inventory._prepare_job_items(
            factory,
            job_id=job.id,
            worker_id=worker_id,
        )

    assert caught.value.code == "semantic_inventory_table_ambiguous"


@pytest.mark.asyncio
async def test_recovery_requeues_abandoned_running_item(
    db_session: AsyncSession,
) -> None:
    project, source = await _database_source(db_session, relations=_relations(1))
    job = await create_semantic_inventory_job(
        db_session,
        project_id=project.id,
        source_id=source.id,
        request=SemanticInventoryJobRequest(
            locale="zh",
            depth="structure",
            tables=["main.table_000"],
        ),
    )
    await db_session.flush()
    item = (
        await db_session.execute(
            select(SemanticInventoryJobItem).where(
                SemanticInventoryJobItem.job_id == job.id
            )
        )
    ).scalar_one()
    job.tables = ["main.table_000"]
    job.details = {**dict(job.details or {}), "inventory_prepared": True}
    job.status = "running"
    job.lease_owner = "dead-worker"
    job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    item.status = "running"
    item.attempt_count = 1
    item.started_at = datetime.now(UTC)
    await db_session.commit()

    recovered = await recover_semantic_inventory_jobs(db_session)
    await db_session.commit()

    assert recovered == [job.id]
    assert job.status == "queued"
    assert job.lease_owner is None
    assert item.status == "queued"
    assert item.started_at is None


@pytest.mark.asyncio
async def test_structure_runner_reads_columns_but_never_samples_rows(
    async_engine,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, source = await _database_source(db_session, relations=_relations(1))
    job = await create_semantic_inventory_job(
        db_session,
        project_id=project.id,
        source_id=source.id,
        request=SemanticInventoryJobRequest(
            locale="zh",
            depth="structure",
            tables=["main.table_000"],
        ),
    )
    await db_session.commit()
    calls = {"structure": 0, "sample": 0}
    recommendation_calls: list[dict[str, object]] = []

    class _Manager:
        def get_bounded_relation_schema(self, table_name: str, *, max_columns: int):
            calls["structure"] += 1
            assert table_name == "table_000"
            assert max_columns > 0
            return {
                "name": table_name,
                "columns": [{"name": "published_at", "type": "timestamp"}],
                "kind": "table",
            }

        def sample_table(self, *_args, **_kwargs):
            calls["sample"] += 1
            raise AssertionError("structure inventory must not read business rows")

    async def _recommend(*_args, batch_id=None, **kwargs):
        recommendation_calls.append(dict(kwargs))
        return SemanticRecommendationBatch(
            batch_id=batch_id or uuid4(),
            generated_by="preflight",
            items=[],
        )

    monkeypatch.setattr(inventory, "create_database_manager", lambda _config: _Manager())
    monkeypatch.setattr(inventory, "generate_semantic_recommendations", _recommend)
    async def _no_enhancer(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        inventory,
        "build_semantic_recommendation_enhancer",
        _no_enhancer,
    )

    async def _fresh_index(_connection, *, heartbeat=None):
        if heartbeat is not None:
            await heartbeat()
        return {
            "relations": _relations(1),
            "relations_loaded": 1,
            "relations_total": 1,
            "relations_total_at_least": 1,
            "complete": True,
            "truncated": False,
            "unread_relations_at_least": 0,
        }

    monkeypatch.setattr(inventory, "_materialize_relation_index", _fresh_index)
    factory = async_sessionmaker(async_engine, expire_on_commit=False)

    await run_semantic_inventory_job(job.id, factory)

    async with factory() as check:
        stored_job = await check.get(SemanticInventoryJob, job.id)
        stored_source = await check.get(ProjectDataSource, source.id)
        stored_item = (
            await check.execute(
                select(SemanticInventoryJobItem).where(
                    SemanticInventoryJobItem.job_id == job.id
                )
            )
        ).scalar_one()
    assert calls == {"structure": 2, "sample": 0}
    assert stored_job is not None and stored_job.status == "completed"
    assert stored_item.status == "succeeded"
    assert stored_source is not None
    assert stored_source.profile_data["tables"][0]["columns"][0]["name"] == "published_at"
    assert recommendation_calls == [
        {
            "locale": "zh",
            "limit": 242,
            "enhancer": None,
            "mode": "structure",
            "include_source_presentation": False,
        },
        {
            "locale": "zh",
            "limit": 1,
            "enhancer": None,
            "mode": "presentation",
            "include_source_presentation": True,
            "include_table_presentations": False,
        },
    ]


@pytest.mark.asyncio
async def test_scheduler_retains_task_until_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = asyncio.Event()

    async def _run(_job_id, _session_factory=None):
        await release.wait()

    monkeypatch.setattr(inventory, "run_semantic_inventory_job", _run)
    task = inventory.schedule_semantic_inventory_job(uuid4())
    assert task in inventory._scheduled_tasks
    release.set()
    await task
    await asyncio.sleep(0)
    assert task not in inventory._scheduled_tasks


@pytest.mark.asyncio
async def test_structure_inventory_keeps_one_source_candidate_and_safe_field_labels(
    async_engine,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relations = _relations(2)
    project, source = await _database_source(db_session, relations=relations)
    job = await create_semantic_inventory_job(
        db_session,
        project_id=project.id,
        source_id=source.id,
        request=SemanticInventoryJobRequest(
            locale="zh",
            depth="structure",
            tables=["main.table_000", "main.table_001"],
        ),
    )
    await db_session.commit()

    class _Manager:
        def get_bounded_relation_schema(self, table_name: str, *, max_columns: int):
            assert max_columns > 0
            return {
                "name": table_name,
                "kind": "table",
                "columns": [
                    {"name": "published_at", "type": "timestamp"},
                    {"name": "amount", "type": "numeric"},
                ],
            }

    async def _fresh_index(_connection, *, heartbeat=None):
        if heartbeat is not None:
            await heartbeat()
        return {
            "relations": relations,
            "relations_loaded": 2,
            "relations_total": 2,
            "relations_total_at_least": 2,
            "complete": True,
            "truncated": False,
            "unread_relations_at_least": 0,
        }

    enhancer_calls = 0

    async def _no_enhancer(*_args, **_kwargs):
        nonlocal enhancer_calls
        enhancer_calls += 1
        return None

    monkeypatch.setattr(inventory, "create_database_manager", lambda _config: _Manager())
    monkeypatch.setattr(inventory, "_materialize_relation_index", _fresh_index)
    monkeypatch.setattr(
        inventory,
        "build_semantic_recommendation_enhancer",
        _no_enhancer,
    )
    factory = async_sessionmaker(async_engine, expire_on_commit=False)

    await run_semantic_inventory_job(job.id, factory)

    async with factory() as check:
        stored_job = await check.get(SemanticInventoryJob, job.id)
        entries = list(
            (
                await check.execute(
                    select(SemanticEntry).where(SemanticEntry.project_id == project.id)
                )
            ).scalars()
        )
    source_presentations = [
        entry
        for entry in entries
        if entry.entry_type == "scope_presentation"
        and (entry.definition or {}).get("scope_kind") == "source"
    ]
    table_presentations = [
        entry
        for entry in entries
        if entry.entry_type == "scope_presentation"
        and (entry.definition or {}).get("scope_kind") == "table"
    ]
    listing_dimensions = [
        entry
        for entry in entries
        if entry.entry_type == "dimension"
        and (entry.definition or {}).get("source", {}).get("action_column")
        == "published_at"
    ]

    assert stored_job is not None and stored_job.status == "completed"
    assert enhancer_calls == 3
    assert len(source_presentations) == 1
    assert len(table_presentations) == 2
    assert len(listing_dimensions) == 2
    assert all(entry.entry_type != "metric" for entry in entries)
    assert all(entry.entry_type != "relationship" for entry in entries)


@pytest.mark.asyncio
async def test_sampled_profile_keeps_qualified_table_names_inside_source_profile(
    db_session: AsyncSession,
) -> None:
    _project, source = await _database_source(db_session, relations=_relations(1))

    inventory._merge_table_profile(
        source,
        relation=_relations(1)[0],
        catalog_entry={
            "name": "table_000",
            "schema": "main",
            "kind": "table",
            "columns": [{"name": "amount", "type": "numeric"}],
        },
        portrait={
            "table": "table_000",
            "candidate_roles": [{"column": "amount", "role": "measure"}],
            "candidate_grain": [{"columns": ["amount"]}],
        },
    )

    table = source.profile_data["tables"][0]
    preanalysis = source.profile_data["preanalysis"]
    assert table["candidate_roles"][0]["table"] == "main.table_000"
    assert table["candidate_grain"][0]["table"] == "main.table_000"
    assert preanalysis["candidate_roles"][-1]["table"] == "main.table_000"
    assert preanalysis["tables"][-1]["table"] == "main.table_000"


@pytest.mark.asyncio
async def test_source_drift_before_profile_write_fails_closed(
    async_engine,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relations = _relations(1)
    project, source = await _database_source(db_session, relations=relations)
    job = await create_semantic_inventory_job(
        db_session,
        project_id=project.id,
        source_id=source.id,
        request=SemanticInventoryJobRequest(
            locale="zh",
            depth="structure",
            tables=["main.table_000"],
        ),
    )
    await db_session.commit()

    class _Manager:
        def get_bounded_relation_schema(self, table_name: str, *, max_columns: int):
            return {
                "name": table_name,
                "columns": [{"name": "published_at", "type": "timestamp"}],
            }

    async def _fresh_index(_connection, *, heartbeat=None):
        if heartbeat is not None:
            await heartbeat()
        return {
            "relations": relations,
            "complete": True,
            "truncated": False,
        }

    async def _no_enhancer(*_args, **_kwargs):
        return None

    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    original_persist_profile = inventory._persist_profile_result
    drifted = False

    async def _persist_after_drift(*args, **kwargs):
        nonlocal drifted
        if not drifted:
            async with factory() as mutate:
                stored_source = await mutate.get(ProjectDataSource, source.id)
                assert stored_source is not None
                stored_source.fingerprint = "changed-while-running"
                await mutate.commit()
            drifted = True
        return await original_persist_profile(*args, **kwargs)

    monkeypatch.setattr(inventory, "create_database_manager", lambda _config: _Manager())
    monkeypatch.setattr(inventory, "_materialize_relation_index", _fresh_index)
    monkeypatch.setattr(
        inventory,
        "build_semantic_recommendation_enhancer",
        _no_enhancer,
    )
    monkeypatch.setattr(inventory, "_persist_profile_result", _persist_after_drift)

    await run_semantic_inventory_job(job.id, factory)

    async with factory() as check:
        stored_job = await check.get(SemanticInventoryJob, job.id)
        stored_source = await check.get(ProjectDataSource, source.id)
        item = (
            await check.execute(
                select(SemanticInventoryJobItem).where(
                    SemanticInventoryJobItem.job_id == job.id
                )
            )
        ).scalar_one()
    assert stored_job is not None and stored_job.status == "completed_with_errors"
    assert item.status == "failed"
    assert item.code == "semantic_inventory_source_changed"
    assert item.retryable is False
    assert stored_source is not None and stored_source.profile_data["tables"] == []


@pytest.mark.asyncio
async def test_table_contract_drift_during_generation_does_not_persist_candidates(
    async_engine,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relations = _relations(1)
    project, source = await _database_source(db_session, relations=relations)
    job = await create_semantic_inventory_job(
        db_session,
        project_id=project.id,
        source_id=source.id,
        request=SemanticInventoryJobRequest(
            locale="zh",
            depth="structure",
            tables=["main.table_000"],
        ),
    )
    await db_session.commit()
    schema_reads = 0

    class _Manager:
        def get_bounded_relation_schema(self, table_name: str, *, max_columns: int):
            nonlocal schema_reads
            schema_reads += 1
            return {
                "name": table_name,
                "schema": "main",
                "kind": "table",
                "constraint_metadata_status": "available",
                "columns": [
                    {
                        "name": "published_at",
                        "type": "timestamp" if schema_reads == 1 else "text",
                    }
                ],
                "foreign_keys": [],
            }

    async def _fresh_index(_connection, *, heartbeat=None):
        if heartbeat is not None:
            await heartbeat()
        return {"relations": relations, "complete": True, "truncated": False}

    async def _no_enhancer(*_args, **_kwargs):
        return None

    monkeypatch.setattr(inventory, "create_database_manager", lambda _config: _Manager())
    monkeypatch.setattr(inventory, "_materialize_relation_index", _fresh_index)
    monkeypatch.setattr(
        inventory,
        "build_semantic_recommendation_enhancer",
        _no_enhancer,
    )
    factory = async_sessionmaker(async_engine, expire_on_commit=False)

    await run_semantic_inventory_job(job.id, factory)

    async with factory() as check:
        stored_job = await check.get(SemanticInventoryJob, job.id)
        stored_source = await check.get(ProjectDataSource, source.id)
        item = (
            await check.execute(
                select(SemanticInventoryJobItem).where(
                    SemanticInventoryJobItem.job_id == job.id
                )
            )
        ).scalar_one()
        entries = list(
            (
                await check.execute(
                    select(SemanticEntry).where(SemanticEntry.project_id == project.id)
                )
            ).scalars()
        )
    assert schema_reads == 2
    assert stored_job is not None and stored_job.status == "completed_with_errors"
    assert item.status == "failed"
    assert item.code == "semantic_inventory_table_changed"
    assert item.retryable is True
    assert stored_source is not None and stored_source.profile_data["tables"] == []
    assert entries == []


@pytest.mark.asyncio
async def test_cancel_and_retry_keep_durable_item_progress(
    db_session: AsyncSession,
) -> None:
    project, source = await _database_source(db_session, relations=_relations(2))
    cancelled = await create_semantic_inventory_job(
        db_session,
        project_id=project.id,
        source_id=source.id,
        request=SemanticInventoryJobRequest(
            locale="zh",
            depth="structure",
            tables=["main.table_000", "main.table_001"],
        ),
    )
    await db_session.commit()

    await request_semantic_inventory_cancel(
        db_session,
        project_id=project.id,
        source_id=source.id,
        job_id=cancelled.id,
    )
    await db_session.commit()
    cancelled_response = await semantic_inventory_job_response(db_session, cancelled)
    assert cancelled_response.status == "cancelled"
    assert cancelled_response.progress.cancelled == 2

    retry_job = await create_semantic_inventory_job(
        db_session,
        project_id=project.id,
        source_id=source.id,
        request=SemanticInventoryJobRequest(
            locale="zh",
            depth="structure",
            tables=["main.table_000"],
        ),
    )
    await db_session.flush()
    retry_item = (
        await db_session.execute(
            select(SemanticInventoryJobItem).where(
                SemanticInventoryJobItem.job_id == retry_job.id
            )
        )
    ).scalar_one()
    retry_job.status = "completed_with_errors"
    retry_job.completed_at = datetime.now(UTC)
    retry_item.status = "failed"
    retry_item.retryable = True
    retry_item.attempt_count = 1
    retry_item.code = "temporary"
    await db_session.commit()

    retried = await retry_semantic_inventory_job(
        db_session,
        project_id=project.id,
        source_id=source.id,
        job_id=retry_job.id,
    )
    await db_session.commit()

    assert retried.status == "queued"
    assert retry_item.status == "queued"
    assert retry_item.attempt_count == 1
    assert retry_item.code is None


@pytest.mark.asyncio
async def test_cancel_during_directory_discovery_finishes_cancelled(
    async_engine,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, source = await _database_source(db_session, relations=_relations(1))
    job = await create_semantic_inventory_job(
        db_session,
        project_id=project.id,
        source_id=source.id,
        request=SemanticInventoryJobRequest(locale="zh", depth="structure"),
    )
    await db_session.commit()
    factory = async_sessionmaker(async_engine, expire_on_commit=False)

    async def _cancel_during_discovery(_connection, *, heartbeat=None):
        if heartbeat is not None:
            await heartbeat()
        async with factory() as cancel_session:
            stored = await cancel_session.get(SemanticInventoryJob, job.id)
            assert stored is not None
            stored.cancel_requested = True
            await cancel_session.commit()
        return {
            "relations": _relations(1),
            "complete": True,
            "truncated": False,
        }

    monkeypatch.setattr(
        inventory,
        "_materialize_relation_index",
        _cancel_during_discovery,
    )

    await run_semantic_inventory_job(job.id, factory)

    async with factory() as check:
        stored = await check.get(SemanticInventoryJob, job.id)
    assert stored is not None and stored.status == "cancelled"


@pytest.mark.asyncio
async def test_turning_setting_off_stops_before_next_table_and_model_call(
    async_engine,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relations = _relations(2)
    project, source = await _database_source(db_session, relations=relations)
    job = await create_semantic_inventory_job(
        db_session,
        project_id=project.id,
        source_id=source.id,
        request=SemanticInventoryJobRequest(
            locale="zh",
            depth="structure",
            tables=["main.table_000", "main.table_001"],
        ),
    )
    await db_session.commit()
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    schema_calls = 0
    enhancer_calls = 0

    class _Manager:
        def get_bounded_relation_schema(self, table_name: str, *, max_columns: int):
            nonlocal schema_calls
            schema_calls += 1
            return {
                "name": table_name,
                "columns": [{"name": "published_at", "type": "timestamp"}],
            }

    async def _fresh_index(_connection, *, heartbeat=None):
        if heartbeat is not None:
            await heartbeat()
        return {
            "relations": relations,
            "complete": True,
            "truncated": False,
        }

    async def _enhancer(*_args, **_kwargs):
        nonlocal enhancer_calls
        enhancer_calls += 1
        return None

    async def _recommend(*_args, batch_id=None, **_kwargs):
        return SemanticRecommendationBatch(
            batch_id=batch_id or uuid4(),
            generated_by="preflight",
            items=[],
        )

    original_persist_candidates = inventory._persist_item_candidates
    first_finished = False

    async def _persist_then_disable(*args, **kwargs):
        nonlocal first_finished
        await original_persist_candidates(*args, **kwargs)
        if not first_finished:
            async with factory() as settings_session:
                settings = await settings_session.get(AppSettings, 1)
                assert settings is not None
                settings.self_analysis_enabled = False
                await settings_session.commit()
            first_finished = True

    monkeypatch.setattr(inventory, "create_database_manager", lambda _config: _Manager())
    monkeypatch.setattr(inventory, "_materialize_relation_index", _fresh_index)
    monkeypatch.setattr(
        inventory,
        "build_semantic_recommendation_enhancer",
        _enhancer,
    )
    monkeypatch.setattr(inventory, "generate_semantic_recommendations", _recommend)
    monkeypatch.setattr(
        inventory,
        "_persist_item_candidates",
        _persist_then_disable,
    )

    await run_semantic_inventory_job(job.id, factory)

    async with factory() as check:
        stored_job = await check.get(SemanticInventoryJob, job.id)
        items = list(
            (
                await check.execute(
                    select(SemanticInventoryJobItem)
                    .where(SemanticInventoryJobItem.job_id == job.id)
                    .order_by(SemanticInventoryJobItem.ordinal)
                )
            ).scalars()
        )
    assert stored_job is not None and stored_job.status == "cancelled"
    assert [item.status for item in items] == ["succeeded", "cancelled"]
    assert schema_calls == 2
    assert enhancer_calls == 1


@pytest.mark.asyncio
async def test_turning_preprocessing_off_stops_sampled_job_before_next_table(
    async_engine,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relations = _relations(2)
    project, source = await _database_source(db_session, relations=relations)
    job = await create_semantic_inventory_job(
        db_session,
        project_id=project.id,
        source_id=source.id,
        request=SemanticInventoryJobRequest(
            locale="zh",
            depth="sampled",
            tables=["main.table_000", "main.table_001"],
        ),
    )
    await db_session.commit()
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    profile_calls = 0
    enhancer_calls = 0

    def _profile(_manager, relation, *, budget):
        nonlocal profile_calls
        profile_calls += 1
        assert budget.max_tables == 1
        return SimpleNamespace(
            catalog_entry={
                "name": relation["name"],
                "schema": relation.get("schema"),
                "kind": "table",
                "columns": [{"name": "amount", "type": "numeric"}],
                "constraint_metadata_status": "available",
                "foreign_keys": [],
            },
            portrait={
                "table": relation["name"],
                "candidate_roles": [{"column": "amount", "role": "measure"}],
                "candidate_grain": [],
            },
        )

    async def _fresh_index(_connection, *, heartbeat=None):
        if heartbeat is not None:
            await heartbeat()
        return {"relations": relations, "complete": True, "truncated": False}

    async def _enhancer(*_args, **_kwargs):
        nonlocal enhancer_calls
        enhancer_calls += 1
        return None

    async def _recommend(*_args, batch_id=None, **_kwargs):
        return SemanticRecommendationBatch(
            batch_id=batch_id or uuid4(),
            generated_by="preflight",
            items=[],
        )

    original_persist = inventory._persist_item_candidates
    first_finished = False

    async def _persist_then_disable(*args, **kwargs):
        nonlocal first_finished
        await original_persist(*args, **kwargs)
        if first_finished:
            return
        async with factory() as settings_session:
            settings = await settings_session.get(AppSettings, 1)
            assert settings is not None
            settings.preprocessing_enabled = False
            await settings_session.commit()
        first_finished = True

    class _Manager:
        def get_bounded_relation_schema(self, table_name: str, *, max_columns: int):
            assert max_columns == 240
            return {
                "name": table_name,
                "schema": "main",
                "kind": "table",
                "columns": [{"name": "amount", "type": "numeric"}],
                "constraint_metadata_status": "available",
                "foreign_keys": [],
            }

    monkeypatch.setattr(inventory, "create_database_manager", lambda _config: _Manager())
    monkeypatch.setattr(inventory, "profile_selected_database_relation", _profile)
    monkeypatch.setattr(inventory, "_materialize_relation_index", _fresh_index)
    monkeypatch.setattr(
        inventory,
        "build_semantic_recommendation_enhancer",
        _enhancer,
    )
    monkeypatch.setattr(inventory, "generate_semantic_recommendations", _recommend)
    monkeypatch.setattr(
        inventory,
        "_persist_item_candidates",
        _persist_then_disable,
    )

    await run_semantic_inventory_job(job.id, factory)

    async with factory() as check:
        stored_job = await check.get(SemanticInventoryJob, job.id)
        items = list(
            (
                await check.execute(
                    select(SemanticInventoryJobItem)
                    .where(SemanticInventoryJobItem.job_id == job.id)
                    .order_by(SemanticInventoryJobItem.ordinal)
                )
            ).scalars()
        )
    assert stored_job is not None and stored_job.status == "cancelled"
    assert [item.status for item in items] == ["succeeded", "cancelled"]
    assert profile_calls == 1
    assert enhancer_calls == 1


@pytest.mark.asyncio
async def test_unprepared_discovery_failure_can_be_retried_without_items(
    db_session: AsyncSession,
) -> None:
    project, source = await _database_source(db_session, relations=_relations(1))
    job = await create_semantic_inventory_job(
        db_session,
        project_id=project.id,
        source_id=source.id,
        request=SemanticInventoryJobRequest(locale="zh", depth="structure"),
    )
    job.status = "failed"
    job.completed_at = datetime.now(UTC)
    job.relation_index_hash = inventory._relation_index_hash(_relations(1))
    job.details = {
        **dict(job.details or {}),
        "code": "semantic_inventory_directory_unavailable",
        "retryable": True,
        "inventory_prepared": False,
    }
    await db_session.commit()

    retried = await retry_semantic_inventory_job(
        db_session,
        project_id=project.id,
        source_id=source.id,
        job_id=job.id,
    )
    response = await semantic_inventory_job_response(db_session, retried)

    assert retried.status == "queued"
    assert response.progress.total == 0
    assert retried.details["retryable"] is False


@pytest.mark.asyncio
async def test_claim_retries_short_transient_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    async def _flaky_claim(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("temporary lock")
        return []

    async def _no_sleep(_delay):
        return None

    monkeypatch.setattr(inventory, "_claim_job", _flaky_claim)
    monkeypatch.setattr(inventory.asyncio, "sleep", _no_sleep)

    claimed = await inventory._claim_job_with_retry(
        object(),
        job_id=uuid4(),
        worker_id="retry-worker",
    )

    assert claimed == []
    assert attempts == 3


@pytest.mark.asyncio
async def test_summary_response_omits_large_table_and_item_payloads(
    db_session: AsyncSession,
) -> None:
    project, source = await _database_source(db_session, relations=_relations(2))
    job = await create_semantic_inventory_job(
        db_session,
        project_id=project.id,
        source_id=source.id,
        request=SemanticInventoryJobRequest(
            locale="zh",
            depth="structure",
            tables=["main.table_000", "main.table_001"],
        ),
    )
    await db_session.commit()

    response = await semantic_inventory_job_response(
        db_session,
        job,
    )

    assert response.progress.total == 2
    assert response.progress.queued == 2
    assert response.tables == []
    assert response.items == []


@pytest.mark.asyncio
async def test_summary_and_item_pages_stay_bounded_and_find_review_work(
    db_session: AsyncSession,
) -> None:
    project, source = await _database_source(db_session, relations=_relations(5))
    job = await create_semantic_inventory_job(
        db_session,
        project_id=project.id,
        source_id=source.id,
        request=SemanticInventoryJobRequest(
            locale="zh",
            depth="structure",
            tables=[f"main.table_{index:03d}" for index in range(5)],
        ),
    )
    items = list(
        (
            await db_session.execute(
                select(SemanticInventoryJobItem)
                .where(SemanticInventoryJobItem.job_id == job.id)
                .order_by(SemanticInventoryJobItem.ordinal)
            )
        ).scalars()
    )
    items[0].status = "failed"
    items[0].code = "first_failure"
    items[1].status = "succeeded"
    items[1].candidate_count = 2
    items[1].recommendation_batch_id = uuid4()
    items[2].status = "succeeded"
    items[2].candidate_count = 1
    items[3].status = "failed"
    items[3].code = "second_failure"
    items[4].status = "succeeded"
    items[4].candidate_count = 4
    items[4].recommendation_batch_id = uuid4()
    job.details = {
        **dict(job.details or {}),
        "source_recommendation_count": 1,
    }
    await db_session.commit()

    summary = await semantic_inventory_job_response(db_session, job)
    first_review = await semantic_inventory_job_items_response(
        db_session,
        job,
        limit=1,
        reviewable=True,
    )
    second_review = await semantic_inventory_job_items_response(
        db_session,
        job,
        limit=1,
        after_ordinal=first_review.next_after_ordinal,
        reviewable=True,
    )
    exact = await semantic_inventory_job_items_response(
        db_session,
        job,
        table="MAIN.TABLE_004",
    )

    assert summary.candidate_count == 8
    assert summary.reviewable_count == 2
    assert summary.next_review_item is not None
    assert summary.next_review_item.ordinal == 1
    assert [item.ordinal for item in summary.failed_item_preview] == [0, 3]
    assert summary.items == [] and summary.tables == []
    assert [item.ordinal for item in first_review.items] == [1]
    assert first_review.has_more is True
    assert first_review.next_after_ordinal == 1
    assert [item.ordinal for item in second_review.items] == [4]
    assert second_review.has_more is False
    assert [item.ordinal for item in exact.items] == [4]

    with pytest.raises(SemanticInventoryError) as invalid_page:
        await semantic_inventory_job_items_response(db_session, job, limit=101)
    assert invalid_page.value.code == "semantic_inventory_page_invalid"
    with pytest.raises(SemanticInventoryError) as unknown_table:
        await semantic_inventory_job_items_response(
            db_session,
            job,
            table="main.missing",
        )
    assert unknown_table.value.code == "semantic_inventory_table_unknown"

    items[0].table_name = "sales.orders"
    items[1].table_name = "archive.orders"
    await db_session.commit()
    with pytest.raises(SemanticInventoryError) as ambiguous_table:
        await semantic_inventory_job_items_response(
            db_session,
            job,
            table="orders",
        )
    assert ambiguous_table.value.code == "semantic_inventory_table_ambiguous"
    qualified = await semantic_inventory_job_items_response(
        db_session,
        job,
        table="sales.orders",
    )
    assert [item.ordinal for item in qualified.items] == [0]


@pytest.mark.asyncio
async def test_declared_fk_is_rebuilt_and_persisted_once_by_later_job_endpoint(
    async_engine,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relations = [
        {"schema": "main", "name": "orders", "kind": "table"},
        {"schema": "main", "name": "customers", "kind": "table"},
    ]
    project, source = await _database_source(db_session, relations=relations)
    job = await create_semantic_inventory_job(
        db_session,
        project_id=project.id,
        source_id=source.id,
        request=SemanticInventoryJobRequest(
            locale="zh",
            depth="structure",
            tables=["main.orders", "main.customers"],
        ),
    )
    await db_session.commit()

    class _Manager:
        def get_bounded_relation_schema(self, table_name: str, *, max_columns: int):
            assert max_columns == 240
            if table_name == "orders":
                return {
                    "schema": "main",
                    "name": "orders",
                    "kind": "table",
                    "constraint_metadata_status": "available",
                    "columns": [
                        {"name": "id", "type": "integer", "primary_key": True},
                        {"name": "customer_id", "type": "integer"},
                    ],
                    "primary_key": {"name": "pk_orders", "columns": ["id"]},
                    "unique_constraints": [],
                    "foreign_keys": [
                        {
                            "name": "fk_orders_customer",
                            "columns": ["customer_id"],
                            "referenced_schema": "main",
                            "referenced_table": "customers",
                            "referenced_columns": ["id"],
                            "on_update": "NO ACTION",
                            "on_delete": "NO ACTION",
                        }
                    ],
                }
            assert table_name == "customers"
            return {
                "schema": "main",
                "name": "customers",
                "kind": "table",
                "constraint_metadata_status": "available",
                "columns": [
                    {"name": "id", "type": "integer", "primary_key": True},
                    {"name": "name", "type": "text"},
                ],
                "primary_key": {"name": "pk_customers", "columns": ["id"]},
                "unique_constraints": [],
                "foreign_keys": [],
            }

    async def _fresh_index(_connection, *, heartbeat=None):
        if heartbeat is not None:
            await heartbeat()
        return {
            "relations": relations,
            "relations_loaded": 2,
            "relations_total": 2,
            "relations_total_at_least": 2,
            "complete": True,
            "truncated": False,
            "unread_relations_at_least": 0,
        }

    async def _no_enhancer(*_args, **_kwargs):
        return None

    monkeypatch.setattr(inventory, "create_database_manager", lambda _config: _Manager())
    monkeypatch.setattr(inventory, "_materialize_relation_index", _fresh_index)
    monkeypatch.setattr(
        inventory,
        "build_semantic_recommendation_enhancer",
        _no_enhancer,
    )
    factory = async_sessionmaker(async_engine, expire_on_commit=False)

    await run_semantic_inventory_job(job.id, factory)

    async with factory() as check:
        stored_source = await check.get(ProjectDataSource, source.id)
        stored_items = list(
            (
                await check.execute(
                    select(SemanticInventoryJobItem)
                    .where(SemanticInventoryJobItem.job_id == job.id)
                    .order_by(SemanticInventoryJobItem.ordinal)
                )
            ).scalars()
        )
        relationships = list(
            (
                await check.execute(
                    select(SemanticEntry).where(
                        SemanticEntry.project_id == project.id,
                        SemanticEntry.entry_type == "relationship",
                    )
                )
            ).scalars()
        )

    assert stored_source is not None
    evidence = stored_source.profile_data["preanalysis"]["relationship_evidence"]
    assert len(evidence) == 1
    assert evidence[0]["catalog_verified"] is True
    assert evidence[0]["source"]["table"] == "orders"
    assert evidence[0]["target"]["table"] == "customers"
    assert len(relationships) == 1
    definition = relationships[0].definition
    assert definition["left"]["table_or_view"] == "main.orders"
    assert definition["right"]["table_or_view"] == "main.customers"
    assert stored_items[1].candidate_count > stored_items[0].candidate_count


@pytest.mark.asyncio
async def test_retry_requeues_finalization_failure_and_invalidates_old_source_pass(
    db_session: AsyncSession,
) -> None:
    project, source = await _database_source(db_session, relations=_relations(1))
    job = await create_semantic_inventory_job(
        db_session,
        project_id=project.id,
        source_id=source.id,
        request=SemanticInventoryJobRequest(
            locale="zh",
            depth="structure",
            tables=["main.table_000"],
        ),
    )
    item = (
        await db_session.execute(
            select(SemanticInventoryJobItem).where(
                SemanticInventoryJobItem.job_id == job.id
            )
        )
    ).scalar_one()
    item.status = "succeeded"
    item.recommendation_batch_id = uuid4()
    job.status = "failed"
    job.completed_at = datetime.now(UTC)
    job.relation_index_hash = inventory._relation_index_hash(_relations(1))
    job.details = {
        **dict(job.details or {}),
        "inventory_prepared": True,
        "retryable": True,
        "source_recommendation_batch_id": str(uuid4()),
        "source_recommendation_count": 1,
    }
    await db_session.commit()

    retried = await retry_semantic_inventory_job(
        db_session,
        project_id=project.id,
        source_id=source.id,
        job_id=job.id,
    )

    assert retried.status == "queued"
    assert item.status == "succeeded"
    assert "source_recommendation_batch_id" not in retried.details
    assert "source_recommendation_count" not in retried.details


@pytest.mark.asyncio
async def test_source_finalization_failure_retries_without_reprocessing_table(
    async_engine,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relations = _relations(1)
    project, source = await _database_source(db_session, relations=relations)
    job = await create_semantic_inventory_job(
        db_session,
        project_id=project.id,
        source_id=source.id,
        request=SemanticInventoryJobRequest(
            locale="zh",
            depth="structure",
            tables=["main.table_000"],
        ),
    )
    await db_session.commit()
    schema_reads = 0
    finalization_attempts = 0

    class _Manager:
        def get_bounded_relation_schema(self, table_name: str, *, max_columns: int):
            nonlocal schema_reads
            schema_reads += 1
            return {
                "name": table_name,
                "schema": "main",
                "kind": "table",
                "columns": [{"name": "published_at", "type": "timestamp"}],
                "constraint_metadata_status": "available",
                "foreign_keys": [],
            }

    async def _fresh_index(_connection, *, heartbeat=None):
        if heartbeat is not None:
            await heartbeat()
        return {"relations": relations, "complete": True, "truncated": False}

    async def _no_enhancer(*_args, **_kwargs):
        return None

    original_generate = inventory.generate_semantic_recommendations

    async def _fail_first_source_pass(*args, **kwargs):
        nonlocal finalization_attempts
        if kwargs.get("mode") == "presentation":
            finalization_attempts += 1
            if finalization_attempts == 1:
                raise RuntimeError("temporary source presentation failure")
        return await original_generate(*args, **kwargs)

    monkeypatch.setattr(inventory, "create_database_manager", lambda _config: _Manager())
    monkeypatch.setattr(inventory, "_materialize_relation_index", _fresh_index)
    monkeypatch.setattr(
        inventory,
        "build_semantic_recommendation_enhancer",
        _no_enhancer,
    )
    monkeypatch.setattr(
        inventory,
        "generate_semantic_recommendations",
        _fail_first_source_pass,
    )
    factory = async_sessionmaker(async_engine, expire_on_commit=False)

    await run_semantic_inventory_job(job.id, factory)
    async with factory() as first_check:
        failed_job = await first_check.get(SemanticInventoryJob, job.id)
        first_item = (
            await first_check.execute(
                select(SemanticInventoryJobItem).where(
                    SemanticInventoryJobItem.job_id == job.id
                )
            )
        ).scalar_one()
        assert failed_job is not None and failed_job.status == "failed"
        assert failed_job.details["retryable"] is True
        assert first_item.status == "succeeded"
        assert first_item.attempt_count == 1
        retried = await retry_semantic_inventory_job(
            first_check,
            project_id=project.id,
            source_id=source.id,
            job_id=job.id,
        )
        await first_check.commit()
        assert retried.status == "queued"

    await run_semantic_inventory_job(job.id, factory)

    async with factory() as second_check:
        completed_job = await second_check.get(SemanticInventoryJob, job.id)
        completed_item = (
            await second_check.execute(
                select(SemanticInventoryJobItem).where(
                    SemanticInventoryJobItem.job_id == job.id
                )
            )
        ).scalar_one()
        source_presentations = list(
            (
                await second_check.execute(
                    select(SemanticEntry).where(
                        SemanticEntry.project_id == project.id,
                        SemanticEntry.entry_type == "scope_presentation",
                    )
                )
            ).scalars()
        )
    assert completed_job is not None and completed_job.status == "completed"
    assert completed_job.details["source_recommendation_count"] == 1
    assert completed_item.status == "succeeded"
    assert completed_item.attempt_count == 1
    assert schema_reads == 2
    assert finalization_attempts == 2
    assert sum(
        (entry.definition or {}).get("scope_kind") == "source"
        for entry in source_presentations
    ) == 1
