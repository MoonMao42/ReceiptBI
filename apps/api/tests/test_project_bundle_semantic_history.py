"""Versioned project bundles preserve semantic history without sharing identities."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.tables import Project, SemanticEntry, SemanticEntryRevision
from app.services.semantic_revisions import (
    append_semantic_revision,
    deactivate_semantic_entry,
    restore_semantic_revision,
)


@pytest.mark.asyncio
async def test_current_bundle_round_trips_complete_semantic_history_with_new_ids(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="语义历史备份")
    db_session.add(project)
    await db_session.flush()

    correction_id = uuid4()
    active = SemanticEntry(
        project_id=project.id,
        key="metric:revenue",
        value="收入按实付金额",
        entry_type="metric",
        state="confirmed",
        confidence=1,
        execution_state="verified",
        execution_details={
            "version": 1,
            "status": "verified",
            "proof": {"query_hash": "abc123", "row_count": 12},
        },
        evidence=[{"kind": "validation", "artifact_id": "proof-1"}],
        source="user",
    )
    db_session.add(active)
    await db_session.flush()
    first = await append_semantic_revision(
        db_session,
        active,
        mutation_kind="created",
        actor_source="user",
        reason="财务确认实付口径",
    )
    active.value = "收入按开票金额"
    active.execution_state = "definition_only"
    active.execution_details = {"version": 1, "status": "definition_only"}
    second = await append_semantic_revision(
        db_session,
        active,
        mutation_kind="correction_applied",
        actor_source="verified_analysis",
        reason="分析后调整口径",
        source_correction_id=correction_id,
        expected_active_revision_id=first.id,
    )
    restored = await restore_semantic_revision(
        db_session,
        active,
        first,
        expected_active_revision_id=second.id,
        reason="恢复已验证的财务口径",
    )

    inactive = SemanticEntry(
        project_id=project.id,
        key="dimension:temporary_channel",
        value="临时渠道映射",
        entry_type="dimension",
        state="candidate",
        confidence=0.6,
        source="inferred",
    )
    db_session.add(inactive)
    await db_session.flush()
    inactive_first = await append_semantic_revision(
        db_session,
        inactive,
        mutation_kind="candidate_created",
        actor_source="inferred",
        reason="预检推断",
    )
    inactive_last = await deactivate_semantic_entry(
        db_session,
        inactive,
        expected_active_revision_id=inactive_first.id,
        source_correction_id=correction_id,
    )

    base_time = datetime(2026, 7, 18, 8, 0, tzinfo=UTC)
    for offset, revision in enumerate([first, second, restored, inactive_first, inactive_last]):
        revision.created_at = base_time + timedelta(minutes=offset)
    active.created_at = base_time - timedelta(days=1)
    active.updated_at = base_time + timedelta(minutes=3)
    inactive.created_at = base_time - timedelta(hours=1)
    inactive.updated_at = base_time + timedelta(minutes=5)
    await db_session.commit()

    exported = await client.get(f"/api/v1/projects/{project.id}/export")
    assert exported.status_code == 200, exported.text
    bundle = exported.json()["data"]
    assert bundle["version"] == 3
    assert [item["key"] for item in bundle["semantic_entries"]] == ["metric:revenue"]
    assert {item["head"]["key"] for item in bundle["semantic_histories"]} == {
        "metric:revenue",
        "dimension:temporary_channel",
    }

    active_history = next(
        item for item in bundle["semantic_histories"] if item["head"]["key"] == "metric:revenue"
    )
    assert [item["revision_number"] for item in active_history["revisions"]] == [1, 2, 3]
    assert active_history["revisions"][1]["actor_source"] == "verified_analysis"
    assert active_history["revisions"][1]["reason"] == "分析后调整口径"
    assert active_history["revisions"][1]["source_correction_id"] == str(correction_id)
    assert (
        active_history["revisions"][2]["restored_from_revision_id"]
        == active_history["revisions"][0]["id"]
    )
    assert active_history["revisions"][0]["snapshot"]["execution_details"]["proof"] == {
        "query_hash": "abc123",
        "row_count": 12,
    }
    inactive_history = next(
        item
        for item in bundle["semantic_histories"]
        if item["head"]["key"] == "dimension:temporary_channel"
    )
    assert inactive_history["head"]["is_active"] is False

    imported = await client.post("/api/v1/projects/import", json=bundle)
    assert imported.status_code == 200, imported.text
    imported_project_id = UUID(imported.json()["data"]["id"])
    imported_entries_result = await db_session.execute(
        select(SemanticEntry)
        .where(SemanticEntry.project_id == imported_project_id)
        .order_by(SemanticEntry.key)
    )
    imported_entries = list(imported_entries_result.scalars())
    assert len(imported_entries) == 2
    assert all(entry.id not in {active.id, inactive.id} for entry in imported_entries)
    assert all(entry.project_id == imported_project_id for entry in imported_entries)

    imported_active = next(entry for entry in imported_entries if entry.key == "metric:revenue")
    imported_revisions_result = await db_session.execute(
        select(SemanticEntryRevision)
        .where(SemanticEntryRevision.semantic_entry_id == imported_active.id)
        .order_by(SemanticEntryRevision.revision_number)
    )
    imported_revisions = list(imported_revisions_result.scalars())
    assert [revision.mutation_kind for revision in imported_revisions] == [
        "created",
        "correction_applied",
        "restored",
    ]
    assert imported_active.active_revision_id == imported_revisions[-1].id
    assert imported_revisions[1].parent_revision_id == imported_revisions[0].id
    assert imported_revisions[2].parent_revision_id == imported_revisions[1].id
    assert imported_revisions[2].restored_from_revision_id == imported_revisions[0].id
    assert imported_revisions[1].source_correction_id == str(correction_id)
    assert imported_revisions[0].snapshot["execution_details"]["proof"]["row_count"] == 12
    assert imported_revisions[0].id not in {first.id, second.id, restored.id}
    assert imported_active.created_at.replace(tzinfo=None) == active.created_at.replace(tzinfo=None)


@pytest.mark.asyncio
async def test_v1_bundle_still_imports_and_starts_a_local_history(
    client: AsyncClient,
    db_session: AsyncSession,
):
    response = await client.post(
        "/api/v1/projects/import",
        json={
            "version": 1,
            "project": {"name": "旧版备份"},
            "semantic_entries": [
                {
                    "key": "revenue_policy",
                    "value": "收入按实付金额",
                    "entry_type": "business_rule",
                    "state": "locked",
                    "confidence": 1,
                    "source": "imported",
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    project_id = UUID(response.json()["data"]["id"])
    entry_result = await db_session.execute(
        select(SemanticEntry).where(SemanticEntry.project_id == project_id)
    )
    entry = entry_result.scalar_one()
    revision_result = await db_session.execute(
        select(SemanticEntryRevision).where(SemanticEntryRevision.semantic_entry_id == entry.id)
    )
    revision = revision_result.scalar_one()
    assert entry.revision_number == 1
    assert entry.active_revision_id == revision.id
    assert revision.mutation_kind == "imported"
    assert revision.actor_source == "imported"


@pytest.mark.asyncio
async def test_key_rename_exports_history_and_restore_keeps_current_identity(
    client: AsyncClient,
):
    project_response = await client.post("/api/v1/projects", json={"name": "语义标识重命名"})
    assert project_response.status_code == 200, project_response.text
    project = project_response.json()["data"]
    created_response = await client.post(
        f"/api/v1/projects/{project['id']}/knowledge",
        json={
            "key": "metric:old_revenue",
            "value": "收入按实付金额",
            "entry_type": "metric",
            "state": "confirmed",
            "confidence": 1,
            "source": "user",
        },
    )
    assert created_response.status_code == 200, created_response.text
    created = created_response.json()["data"]

    renamed_response = await client.put(
        f"/api/v1/projects/{project['id']}/knowledge/{created['id']}",
        json={
            "expected_active_revision_id": created["active_revision_id"],
            "key": "metric:recognized_revenue",
            "value": "收入按已审核实付金额",
            "source": "user",
        },
    )
    assert renamed_response.status_code == 200, renamed_response.text
    renamed = renamed_response.json()["data"]

    restored_response = await client.post(
        f"/api/v1/projects/{project['id']}/knowledge/{created['id']}"
        f"/revisions/{created['active_revision_id']}/restore",
        json={
            "expected_active_revision_id": renamed["active_revision_id"],
            "reason": "恢复旧口径但保留当前业务标识",
        },
    )
    assert restored_response.status_code == 200, restored_response.text
    restored = restored_response.json()["data"]
    assert restored["key"] == "metric:recognized_revenue"
    assert restored["value"] == "收入按实付金额"

    exported = await client.get(f"/api/v1/projects/{project['id']}/export")
    assert exported.status_code == 200, exported.text
    bundle = exported.json()["data"]
    history = bundle["semantic_histories"][0]
    assert history["head"]["key"] == "metric:recognized_revenue"
    assert [revision["snapshot"]["key"] for revision in history["revisions"]] == [
        "metric:old_revenue",
        "metric:recognized_revenue",
        "metric:recognized_revenue",
    ]

    bundle["project"] = {"name": "导入后的语义标识"}
    imported = await client.post("/api/v1/projects/import", json=bundle)
    assert imported.status_code == 200, imported.text


@pytest.mark.asyncio
async def test_v2_import_rejects_broken_revision_chain_before_creating_project(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="待破坏备份")
    db_session.add(project)
    await db_session.flush()
    entry = SemanticEntry(
        project_id=project.id,
        key="metric:orders",
        value="订单数",
        entry_type="metric",
        state="confirmed",
        confidence=1,
        source="user",
    )
    db_session.add(entry)
    await db_session.flush()
    first = await append_semantic_revision(
        db_session,
        entry,
        mutation_kind="created",
        actor_source="user",
    )
    entry.value = "有效订单数"
    await append_semantic_revision(
        db_session,
        entry,
        mutation_kind="user_updated",
        actor_source="user",
        expected_active_revision_id=first.id,
    )
    await db_session.commit()

    exported = await client.get(f"/api/v1/projects/{project.id}/export")
    assert exported.status_code == 200, exported.text
    broken = deepcopy(exported.json()["data"])
    broken["project"] = {"name": "不应被创建"}
    broken["semantic_histories"][0]["revisions"][1]["parent_revision_id"] = str(uuid4())
    before = await db_session.scalar(select(func.count(Project.id)))

    rejected = await client.post("/api/v1/projects/import", json=broken)
    assert rejected.status_code == 422
    after = await db_session.scalar(select(func.count(Project.id)))
    assert after == before


@pytest.mark.asyncio
async def test_export_fails_closed_when_semantic_head_has_no_revision(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="缺少历史")
    db_session.add(project)
    await db_session.flush()
    db_session.add(
        SemanticEntry(
            project_id=project.id,
            key="orphan_definition",
            value="不能静默导出",
            source="user",
        )
    )
    await db_session.commit()

    response = await client.get(f"/api/v1/projects/{project.id}/export")
    assert response.status_code == 409
    assert "版本历史" in response.json()["detail"]
