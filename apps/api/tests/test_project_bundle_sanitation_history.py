"""Project bundle v3 keeps cleaning history portable without binding old sources."""

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.tables import (
    Project,
    ProjectDataSource,
    SanitationRecipeRecord,
    SanitationRecipeRevisionRecord,
)
from app.services.sanitation_contract import canonicalize_sanitation_operations
from app.services.sanitation_revisions import (
    append_sanitation_revision,
    ensure_sanitation_revision_head,
)


def _imported_template_history(*, name: str = "历史订单整理") -> dict:
    recipe_id = uuid4()
    revision_id = uuid4()
    operations = canonicalize_sanitation_operations(
        [{"operation": "trim_text", "column": "store_id"}]
    )
    created_at = datetime.now(UTC).isoformat()
    return {
        "recipe_id": str(recipe_id),
        "head": {
            "name": name,
            "status": "needs_attention",
            "operations": operations,
            "input_fingerprint": None,
            "output_fingerprint": None,
            "active_revision_id": str(revision_id),
            "created_at": created_at,
            "updated_at": created_at,
        },
        "revisions": [
            {
                "id": str(revision_id),
                "revision_number": 1,
                "parent_revision_id": None,
                "state": "candidate",
                "operations": operations,
                "input_contract": {"version": 1, "fingerprint": None},
                "output_contract": {"version": 1, "fingerprint": None},
                "actor_source": "imported",
                "reason": "从项目备份导入",
                "source_correction_id": None,
                "created_at": created_at,
            }
        ],
    }


@pytest.mark.asyncio
async def test_v3_bundle_round_trips_complete_cleaning_history_as_unbound_candidates(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="整理历史备份")
    db_session.add(project)
    await db_session.flush()
    source = ProjectDataSource(
        project_id=project.id,
        kind="file",
        name="orders.csv",
        format="csv",
        status="needs_confirmation",
    )
    db_session.add(source)
    await db_session.flush()

    initial_operations = canonicalize_sanitation_operations(
        [{"operation": "trim_text", "column": "store_id"}]
    )
    recipe = SanitationRecipeRecord(
        project_id=project.id,
        data_source_id=source.id,
        name="订单自动整理",
        status="applied",
        operations=initial_operations,
        input_fingerprint="a" * 64,
        output_fingerprint="b" * 64,
    )
    db_session.add(recipe)
    await db_session.flush()
    first = await ensure_sanitation_revision_head(db_session, recipe)

    candidate_operations = canonicalize_sanitation_operations(
        [
            {"operation": "trim_text", "column": "store_id"},
            {"operation": "normalize_currency", "column": "amount"},
        ]
    )
    second = await append_sanitation_revision(
        db_session,
        recipe,
        expected_active_revision_id=first.id,
        state="candidate",
        operations=candidate_operations,
        input_contract={"version": 1, "fingerprint": "c" * 64, "rows": 20},
        output_contract={"version": 1, "fingerprint": "d" * 64, "rows": 18},
        actor_source="system",
        reason="新一期字段变化，等待确认",
    )
    recipe.status = "needs_attention"
    await db_session.commit()

    exported = await client.get(f"/api/v1/projects/{project.id}/export")
    assert exported.status_code == 200, exported.text
    bundle = exported.json()["data"]
    assert bundle["version"] == 3
    assert bundle["sanitation_recipes"] == []
    assert len(bundle["sanitation_histories"]) == 1
    history = bundle["sanitation_histories"][0]
    assert history["head"]["active_revision_id"] == str(second.id)
    assert [item["revision_number"] for item in history["revisions"]] == [1, 2]
    assert history["revisions"][1]["state"] == "candidate"
    assert history["revisions"][1]["reason"] == "新一期字段变化，等待确认"

    imported = await client.post("/api/v1/projects/import", json=bundle)
    assert imported.status_code == 200, imported.text
    imported_project_id = UUID(imported.json()["data"]["id"])
    imported_project = await db_session.get(Project, imported_project_id)
    assert imported_project is not None
    stored_histories = (imported_project.extra_data or {})["recipe_template_histories"]
    candidates = (imported_project.extra_data or {})["recipe_template_candidates"]
    assert len(stored_histories) == len(candidates) == 1
    assert stored_histories[0]["recipe_id"] != history["recipe_id"]
    assert stored_histories[0]["revisions"][0]["id"] != history["revisions"][0]["id"]
    assert candidates[0]["requires_explicit_binding"] is True
    assert candidates[0]["operations"] == candidate_operations

    reexported = await client.get(f"/api/v1/projects/{imported_project_id}/export")
    assert reexported.status_code == 200, reexported.text
    reexported_history = reexported.json()["data"]["sanitation_histories"][0]
    assert reexported_history["recipe_id"] == stored_histories[0]["recipe_id"]
    assert reexported_history["head"]["operations"] == candidate_operations


@pytest.mark.asyncio
async def test_v3_import_rejects_broken_cleaning_chain_before_creating_project(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="待破坏整理备份")
    db_session.add(project)
    await db_session.flush()
    source = ProjectDataSource(
        project_id=project.id,
        kind="file",
        name="orders.csv",
        format="csv",
        status="ready",
    )
    db_session.add(source)
    await db_session.flush()
    operations = canonicalize_sanitation_operations(
        [{"operation": "trim_text", "column": "store_id"}]
    )
    recipe = SanitationRecipeRecord(
        project_id=project.id,
        data_source_id=source.id,
        name="订单自动整理",
        status="applied",
        operations=operations,
        input_fingerprint="a" * 64,
        output_fingerprint="b" * 64,
    )
    db_session.add(recipe)
    await ensure_sanitation_revision_head(db_session, recipe)
    await db_session.commit()

    exported = await client.get(f"/api/v1/projects/{project.id}/export")
    broken = deepcopy(exported.json()["data"])
    broken["project"] = {"name": "不应创建的项目"}
    broken["sanitation_histories"][0]["revisions"][0]["parent_revision_id"] = str(uuid4())
    before = await db_session.scalar(select(func.count(Project.id)))

    rejected = await client.post("/api/v1/projects/import", json=broken)
    assert rejected.status_code == 422
    after = await db_session.scalar(select(func.count(Project.id)))
    assert after == before


@pytest.mark.asyncio
async def test_cleaning_history_api_restores_by_appending_a_new_head(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="恢复整理方法")
    db_session.add(project)
    await db_session.flush()
    source = ProjectDataSource(
        project_id=project.id,
        kind="file",
        name="orders.csv",
        format="csv",
        status="ready",
    )
    db_session.add(source)
    await db_session.flush()
    first_operations = canonicalize_sanitation_operations(
        [{"operation": "trim_text", "column": "store_id"}]
    )
    recipe = SanitationRecipeRecord(
        project_id=project.id,
        data_source_id=source.id,
        name="订单自动整理",
        status="applied",
        operations=first_operations,
        input_fingerprint="a" * 64,
        output_fingerprint="b" * 64,
    )
    db_session.add(recipe)
    first = await ensure_sanitation_revision_head(db_session, recipe)
    second = await append_sanitation_revision(
        db_session,
        recipe,
        expected_active_revision_id=first.id,
        state="confirmed",
        operations=canonicalize_sanitation_operations(
            [
                {"operation": "trim_text", "column": "store_id"},
                {"operation": "normalize_currency", "column": "amount"},
            ]
        ),
        input_contract={"version": 1, "fingerprint": "c" * 64},
        output_contract={"version": 1, "fingerprint": "d" * 64},
        actor_source="user",
        reason="加入金额整理",
    )
    source.profile_data = {
        "visual_cleaning": {
            "active_revision_id": str(second.id),
            "operations": [{"operation": "trim_text", "column": "store_id"}],
        }
    }
    await db_session.commit()

    listed = await client.get(f"/api/v1/projects/{project.id}/recipes/{recipe.id}/revisions")
    assert listed.status_code == 200, listed.text
    assert [item["revision_number"] for item in listed.json()["data"]] == [2, 1]

    restored = await client.post(
        f"/api/v1/projects/{project.id}/recipes/{recipe.id}/revisions/{first.id}/restore",
        json={"expected_active_revision_id": str(second.id), "reason": "恢复首次方法"},
    )
    assert restored.status_code == 200, restored.text
    restored_revision = restored.json()["data"]
    assert restored_revision["revision_number"] == 3
    assert restored_revision["state"] == "reverted"
    assert restored_revision["operations"] == first_operations

    await db_session.refresh(recipe)
    await db_session.refresh(source)
    assert recipe.status == "reverted"
    assert str(recipe.active_revision_id) == restored_revision["id"]
    assert recipe.operations == first_operations
    assert "visual_cleaning" not in (source.profile_data or {})

    stale = await client.post(
        f"/api/v1/projects/{project.id}/recipes/{recipe.id}/revisions/{second.id}/restore",
        json={"expected_active_revision_id": str(second.id)},
    )
    assert stale.status_code == 409


@pytest.mark.asyncio
async def test_imported_cleaning_template_previews_without_mutation_then_binds_once(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "WORKSPACE_ROOT", tmp_path / "workspace")
    history = _imported_template_history()
    project = Project(
        name="绑定历史整理方法",
        extra_data={
            "recipe_template_histories": [history],
            "recipe_template_candidates": [],
        },
    )
    db_session.add(project)
    await db_session.flush()
    source_path = tmp_path / "orders.csv"
    source_path.write_text("store_id,amount\n A ,10\nB,20\n", encoding="utf-8")
    trusted_working_path = tmp_path / "trusted-working.parquet"
    trusted_working_path.write_bytes(b"trusted working copy")
    source = ProjectDataSource(
        project_id=project.id,
        kind="file",
        name="orders.csv",
        format="csv",
        source_uri=str(source_path),
        working_uri=str(trusted_working_path),
        status="attached",
        profile_data={"is_current": True},
    )
    db_session.add(source)
    await db_session.flush()
    existing_recipe = SanitationRecipeRecord(
        project_id=project.id,
        data_source_id=source.id,
        name="当前自动整理",
        status="applied",
        operations=[],
        input_fingerprint="a" * 64,
        output_fingerprint="b" * 64,
    )
    db_session.add(existing_recipe)
    existing_revision = await ensure_sanitation_revision_head(
        db_session,
        existing_recipe,
    )
    source.profile_data = {
        **dict(source.profile_data or {}),
        "visual_cleaning": {
            "active_revision_id": str(existing_revision.id),
            "operations": [],
        },
    }
    await db_session.commit()

    listed = await client.get(f"/api/v1/projects/{project.id}/recipe-templates")
    assert listed.status_code == 200, listed.text
    assert listed.json()["data"] == [
        {
            "id": history["recipe_id"],
            "name": "历史订单整理",
            "active_revision_id": history["head"]["active_revision_id"],
            "revision_count": 1,
            "compatible_source_ids": [str(source.id)],
        }
    ]

    preview = await client.post(
        f"/api/v1/projects/{project.id}/recipe-templates/{history['recipe_id']}/preview",
        json={"source_id": str(source.id)},
    )
    assert preview.status_code == 200, preview.text
    preview_data = preview.json()["data"]
    assert preview_data["can_apply"] is True
    assert preview_data["before"] == {"rows": 2, "columns": 2}
    assert preview_data["after"] == {"rows": 2, "columns": 2}

    await db_session.refresh(source)
    assert source.working_uri == str(trusted_working_path)
    assert source.status == "attached"
    assert await db_session.scalar(select(func.count(SanitationRecipeRecord.id))) == 1
    assert await db_session.scalar(select(func.count(SanitationRecipeRevisionRecord.id))) == 1
    preview_root = (
        settings.WORKSPACE_ROOT
        / str(project.id)
        / "sources"
        / str(source.id)
        / "working"
        / "previews"
    )
    assert not preview_root.exists() or not any(preview_root.rglob("*"))

    bound = await client.post(
        f"/api/v1/projects/{project.id}/recipe-templates/{history['recipe_id']}/bind",
        json={
            "source_id": str(source.id),
            "expected_template_active_revision_id": preview_data["template_active_revision_id"],
            "expected_template_operations_hash": preview_data["template_operations_hash"],
            "expected_source_fingerprint": preview_data["source_fingerprint"],
            "expected_preview_output_fingerprint": preview_data["preview_output_fingerprint"],
            "expected_current_working_fingerprint": preview_data["current_working_fingerprint"],
            "expected_current_recipe_active_revision_id": preview_data[
                "current_recipe_active_revision_id"
            ],
        },
    )
    assert bound.status_code == 200, bound.text
    bound_data = bound.json()["data"]
    assert bound_data["revision"]["actor_source"] == "imported"
    assert bound_data["revision"]["state"] == "confirmed"
    assert bound_data["recipe"]["id"] == str(existing_recipe.id)
    assert bound_data["revision"]["parent_revision_id"] == str(existing_revision.id)
    assert await db_session.scalar(select(func.count(SanitationRecipeRecord.id))) == 1
    assert await db_session.scalar(select(func.count(SanitationRecipeRevisionRecord.id))) == 2

    await db_session.refresh(source)
    await db_session.refresh(project)
    assert source.working_uri is not None
    assert Path(source.working_uri).is_file()
    assert source.source_uri == str(source_path)
    assert "visual_cleaning" not in (source.profile_data or {})
    assert len((project.extra_data or {})["recipe_template_bindings"]) == 1

    relisted = await client.get(f"/api/v1/projects/{project.id}/recipe-templates")
    assert relisted.json()["data"][0]["compatible_source_ids"] == []
    rebound = await client.post(
        f"/api/v1/projects/{project.id}/recipe-templates/{history['recipe_id']}/bind",
        json={
            "source_id": str(source.id),
            "expected_template_active_revision_id": preview_data["template_active_revision_id"],
            "expected_template_operations_hash": preview_data["template_operations_hash"],
            "expected_source_fingerprint": preview_data["source_fingerprint"],
            "expected_preview_output_fingerprint": preview_data["preview_output_fingerprint"],
            "expected_current_working_fingerprint": preview_data["current_working_fingerprint"],
            "expected_current_recipe_active_revision_id": preview_data[
                "current_recipe_active_revision_id"
            ],
        },
    )
    assert rebound.status_code == 409

    exported = await client.get(f"/api/v1/projects/{project.id}/export")
    assert exported.status_code == 200, exported.text
    histories = exported.json()["data"]["sanitation_histories"]
    assert len(histories) == 2
    imported_history = next(item for item in histories if item["recipe_id"] == history["recipe_id"])
    assert [
        {key: value for key, value in item.items() if key != "created_at"}
        for item in imported_history["revisions"]
    ] == [
        {key: value for key, value in item.items() if key != "created_at"}
        for item in history["revisions"]
    ]


@pytest.mark.asyncio
async def test_template_bind_rejects_a_changed_source_without_mutating_the_project(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "WORKSPACE_ROOT", tmp_path / "workspace")
    history = _imported_template_history()
    project = Project(
        name="拒绝过期预览",
        extra_data={"recipe_template_histories": [history]},
    )
    db_session.add(project)
    await db_session.flush()
    source_path = tmp_path / "orders.csv"
    source_path.write_text("store_id,amount\nA,10\n", encoding="utf-8")
    source = ProjectDataSource(
        project_id=project.id,
        kind="file",
        name="orders.csv",
        format="csv",
        source_uri=str(source_path),
        status="attached",
        profile_data={"is_current": True},
    )
    db_session.add(source)
    await db_session.commit()

    preview = await client.post(
        f"/api/v1/projects/{project.id}/recipe-templates/{history['recipe_id']}/preview",
        json={"source_id": str(source.id)},
    )
    preview_data = preview.json()["data"]
    source_path.write_text("store_id,amount\nA,10\nB,20\n", encoding="utf-8")

    rejected = await client.post(
        f"/api/v1/projects/{project.id}/recipe-templates/{history['recipe_id']}/bind",
        json={
            "source_id": str(source.id),
            "expected_template_active_revision_id": preview_data["template_active_revision_id"],
            "expected_template_operations_hash": preview_data["template_operations_hash"],
            "expected_source_fingerprint": preview_data["source_fingerprint"],
            "expected_preview_output_fingerprint": preview_data["preview_output_fingerprint"],
            "expected_current_working_fingerprint": preview_data["current_working_fingerprint"],
            "expected_current_recipe_active_revision_id": preview_data[
                "current_recipe_active_revision_id"
            ],
        },
    )
    assert rejected.status_code == 409
    await db_session.refresh(source)
    await db_session.refresh(project)
    assert source.working_uri is None
    assert source.status == "attached"
    assert not (project.extra_data or {}).get("recipe_template_bindings")
    assert await db_session.scalar(select(func.count(SanitationRecipeRecord.id))) == 0
