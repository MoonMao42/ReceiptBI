"""Hierarchical semantic scopes stay exact, portable and runtime-private."""

from __future__ import annotations

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import projects as projects_api
from app.db.tables import (
    Connection,
    Project,
    ProjectDataSource,
    SemanticEntry,
    SemanticScopeNode,
)
from app.services.database_adapters import BoundedRelationIndex
from app.services.project_context import load_project_context
from app.services.semantic_revisions import append_semantic_revision
from app.services.semantic_scopes import (
    SemanticScopeResolutionError,
    ensure_semantic_scope_tree,
    resolve_definition_scope,
)


def _columns() -> list[dict[str, str]]:
    return [
        {"name": "department", "type": "text"},
        {"name": "amount", "type": "numeric"},
    ]


def _connection_profile(*tables: str) -> dict:
    return {
        "logical_name": "经营仓库",
        "tables": [
            {
                "name": table,
                "kind": "table",
                "columns": _columns(),
            }
            for table in tables
        ],
    }


def _metric_definition(table: str) -> dict:
    return {
        "version": 1,
        "kind": "aggregate_metric",
        "operation": "sum",
        "source": {
            "source_logical_name": "经营仓库",
            "source_kind": "connection",
            "table_or_view": table,
            "action_column": "amount",
            "canonical_type": "number",
            "schema_signature": "a" * 64,
        },
        "null_policy": "ignore",
        "business_name": f"{table} 金额",
    }


async def _project_with_tables(
    db: AsyncSession,
    *tables: str,
) -> tuple[Project, ProjectDataSource]:
    project = Project(name="层级语义测试")
    db.add(project)
    await db.flush()
    source = ProjectDataSource(
        project_id=project.id,
        kind="connection",
        name="经营数据库",
        status="ready",
        profile_data=_connection_profile(*tables),
    )
    db.add(source)
    await db.commit()
    return project, source


async def _create_metric(
    client: AsyncClient,
    project_id: UUID,
    *,
    key: str,
    table: str,
) -> dict:
    response = await client.post(
        f"/api/v1/projects/{project_id}/knowledge",
        json={
            "key": key,
            "value": f"{table} 的已确认金额",
            "entry_type": "metric",
            "state": "confirmed",
            "confidence": 1,
            "definition": _metric_definition(table),
            "validity": "active",
            "evidence": [],
            "source": "user",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


@pytest.mark.asyncio
async def test_exact_scope_page_keeps_sibling_tables_isolated(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    project, _source = await _project_with_tables(db_session, "table_a", "table_b")
    entry_a = await _create_metric(client, project.id, key="metric:a", table="table_a")
    entry_b = await _create_metric(client, project.id, key="metric:b", table="table_b")

    assert entry_a["scope_id"] != entry_b["scope_id"]
    assert [item["kind"] for item in entry_a["scope_path"]] == [
        "project",
        "source",
        "table",
    ]
    assert entry_a["scope_path"][-1]["table_or_view"] == "table_a"

    scopes = await client.get(f"/api/v1/projects/{project.id}/semantic-scopes")
    assert scopes.status_code == 200, scopes.text
    by_id = {item["id"]: item for item in scopes.json()["data"]}
    assert by_id[entry_a["scope_id"]]["direct_entry_count"] == 1
    assert by_id[entry_a["scope_id"]]["path"][-1]["table_or_view"] == "table_a"

    page_a = await client.get(
        f"/api/v1/projects/{project.id}/knowledge/page",
        params={"scope_id": entry_a["scope_id"]},
    )
    assert page_a.status_code == 200, page_a.text
    assert [item["key"] for item in page_a.json()["data"]["items"]] == ["metric:a"]

    wrong_scope = await client.put(
        f"/api/v1/projects/{project.id}/knowledge/{entry_a['id']}",
        json={
            "scope_id": entry_b["scope_id"],
            "expected_active_revision_id": entry_a["active_revision_id"],
            "source": "user",
        },
    )
    assert wrong_scope.status_code == 422


@pytest.mark.asyncio
async def test_recommendations_are_persisted_on_the_selected_table_scope(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    project, source = await _project_with_tables(db_session, "table_a", "table_b")
    response = await client.post(
        f"/api/v1/projects/{project.id}/knowledge/recommendations",
        json={
            "locale": "zh",
            "scopes": [{"source_id": str(source.id), "tables": ["table_a"]}],
            "limit": 10,
        },
    )
    assert response.status_code == 200, response.text
    items = response.json()["data"]["items"]
    assert items
    source_presentations = [
        item
        for item in items
        if item["entry_type"] == "scope_presentation"
        and item["definition"]["scope_kind"] == "source"
    ]
    assert len(source_presentations) == 1
    assert source_presentations[0]["scope_path"][-1]["kind"] == "source"
    table_items = [item for item in items if item not in source_presentations]
    assert {item["scope_path"][-1]["table_or_view"] for item in table_items} == {"table_a"}
    assert {item["scope_path"][-1]["kind"] for item in table_items} == {"table"}


@pytest.mark.asyncio
async def test_relation_index_builds_all_table_scopes_and_catalog_only_recommendation(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    project = Project(name="完整目录作用域")
    db_session.add(project)
    await db_session.flush()
    relations = [
        {
            "name": f"table_{index:03d}",
            "schema": "main",
            "kind": "table",
            "comment": f"业务表 {index:03d}",
        }
        for index in range(87)
    ]
    source = ProjectDataSource(
        project_id=project.id,
        kind="connection",
        name="完整经营数据库",
        status="ready",
        profile_data={
            "logical_name": "完整经营仓库",
            "tables": [
                {**relations[index], "columns": _columns()}
                for index in range(2)
            ],
            "preanalysis": {
                "relation_index": {
                    "relations": relations,
                    "relations_loaded": 87,
                    "relations_total": 87,
                    "complete": True,
                    "truncated": False,
                }
            },
        },
    )
    db_session.add(source)
    await db_session.commit()

    nodes = await ensure_semantic_scope_tree(db_session, project.id)
    table_nodes = [node for node in nodes if node.kind == "table" and node.is_active]
    assert len(table_nodes) == 87
    catalog_only = next(
        node for node in table_nodes if node.table_or_view == "main.table_086"
    )
    assert catalog_only.context_facts["profile_status"] == "catalog_only"
    assert catalog_only.context_facts["column_count"] == 0

    response = await client.post(
        f"/api/v1/projects/{project.id}/knowledge/recommendations",
        json={
            "locale": "zh",
            "scopes": [{"source_id": str(source.id), "tables": ["main.table_086"]}],
            "limit": 10,
        },
    )
    assert response.status_code == 200, response.text
    items = response.json()["data"]["items"]
    assert [item["entry_type"] for item in items] == [
        "scope_presentation",
        "scope_presentation",
    ]
    table_presentation = next(
        item for item in items if item["definition"]["scope_kind"] == "table"
    )
    assert "确认后可继续完善" in table_presentation["definition"]["description"]
    assert "字段尚未画像" not in table_presentation["definition"]["description"]
    assert table_presentation["scope_path"][-1]["table_or_view"] == "main.table_086"


@pytest.mark.asyncio
async def test_same_name_tables_keep_separate_schema_scopes(
    db_session: AsyncSession,
) -> None:
    project = Project(name="跨 Schema 目录")
    db_session.add(project)
    await db_session.flush()
    source = ProjectDataSource(
        project_id=project.id,
        kind="connection",
        name="销售数仓",
        status="ready",
        profile_data={
            "logical_name": "经营仓库",
            "tables": [
                {
                    "schema": "public",
                    "name": "orders",
                    "kind": "table",
                    "columns": _columns(),
                },
                {
                    "schema": "archive",
                    "name": "orders",
                    "kind": "table",
                    "columns": _columns(),
                },
            ],
        },
    )
    db_session.add(source)
    await db_session.flush()

    nodes = await ensure_semantic_scope_tree(db_session, project.id)
    assert {
        node.table_or_view for node in nodes if node.kind == "table" and node.is_active
    } == {"public.orders", "archive.orders"}

    resolved = resolve_definition_scope(
        [source],
        _metric_definition("public.orders"),
    )
    assert resolved.table_or_view == "public.orders"
    with pytest.raises(SemanticScopeResolutionError, match="无法唯一确认表"):
        resolve_definition_scope([source], _metric_definition("orders"))


@pytest.mark.asyncio
async def test_relation_index_refresh_expands_scopes_without_replacing_confirmed_context(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = Project(name="目录刷新集成")
    connection = Connection(
        name="完整经营库",
        driver="sqlite",
        database_name="ignored.db",
    )
    db_session.add_all([project, connection])
    await db_session.flush()
    relations = [
        {
            "name": f"table_{index:03d}",
            "schema": "main",
            "kind": "table",
            "comment": f"业务表 {index:03d}",
        }
        for index in range(87)
    ]
    source = ProjectDataSource(
        project_id=project.id,
        connection_id=connection.id,
        kind="connection",
        name="完整经营数据库",
        format="sqlite",
        status="ready",
        profile_data={
            "logical_name": "经营仓库",
            "profile_marker": "keep-me",
            "tables": [
                {**relations[index], "columns": _columns()}
                for index in range(24)
            ],
            "preanalysis": {
                "shape": {"tables": 24, "profiled_tables": 24},
                "candidate_roles": [{"column": "amount", "role": "measure"}],
            },
        },
    )
    db_session.add(source)
    await db_session.commit()

    initial_scopes = await client.get(f"/api/v1/projects/{project.id}/semantic-scopes")
    assert initial_scopes.status_code == 200, initial_scopes.text
    initial_tables = [
        item for item in initial_scopes.json()["data"] if item["kind"] == "table"
    ]
    assert len(initial_tables) == 24
    original_target = next(
        item for item in initial_tables if item["table_or_view"] == "main.table_005"
    )

    metric = await _create_metric(
        client,
        project.id,
        key="metric:confirmed-before-directory-refresh",
        table="main.table_005",
    )
    presentation_response = await client.post(
        f"/api/v1/projects/{project.id}/knowledge",
        json={
            "key": "scope_presentation:confirmed-before-directory-refresh",
            "value": "候选数据表名称：已确认销售表",
            "entry_type": "scope_presentation",
            "state": "candidate",
            "confidence": 0.9,
            "definition": {
                "version": 1,
                "kind": "scope_presentation",
                "scope_kind": "table",
                "source_logical_name": "经营仓库",
                "source_kind": "connection",
                "table_or_view": "main.table_005",
                "business_name": "已确认销售表",
                "description": "经过人工确认的销售业务范围。",
                "synonyms": ["table_005", "销售明细"],
                "example_questions": ["销售额是多少？"],
            },
            "validity": "unverified",
            "evidence": [],
            "source": "inferred",
        },
    )
    assert presentation_response.status_code == 200, presentation_response.text
    presentation = presentation_response.json()["data"]
    adopted_response = await client.post(
        f"/api/v1/projects/{project.id}/knowledge/batch",
        json={
            "action": "remember",
            "items": [
                {
                    "entry_id": presentation["id"],
                    "expected_active_revision_id": presentation["active_revision_id"],
                }
            ],
        },
    )
    assert adopted_response.status_code == 200, adopted_response.text

    class RelationIndexManager:
        def get_bounded_relation_index(self, *, max_relations: int):
            assert max_relations >= len(relations)
            return BoundedRelationIndex(relations=relations)

    monkeypatch.setattr(
        projects_api,
        "_database_manager_for_connection",
        lambda _connection: RelationIndexManager(),
    )
    refreshed = await client.post(
        f"/api/v1/projects/{project.id}/sources/{source.id}/relation-index"
    )
    assert refreshed.status_code == 200, refreshed.text
    refreshed_payload = refreshed.json()["data"]
    assert refreshed_payload["relation_index"]["relations_loaded"] == 87
    assert refreshed_payload["semantic_scope_table_count"] == 87

    await db_session.refresh(source)
    assert len(source.profile_data["tables"]) == 24
    assert source.profile_data["profile_marker"] == "keep-me"
    assert source.profile_data["preanalysis"]["candidate_roles"] == [
        {"column": "amount", "role": "measure"}
    ]
    assert source.profile_data["preanalysis"]["shape"] == {
        "tables": 87,
        "profiled_tables": 24,
    }
    assert source.profile_data["relation_index"] == refreshed_payload["relation_index"]
    assert (
        source.profile_data["preanalysis"]["relation_index"]
        == refreshed_payload["relation_index"]
    )

    ensured_nodes = await ensure_semantic_scope_tree(db_session, project.id)
    ensured_tables = [
        node for node in ensured_nodes if node.kind == "table" and node.is_active
    ]
    assert len(ensured_tables) == 87
    ensured_target = next(
        node for node in ensured_tables if node.table_or_view == "main.table_005"
    )
    assert str(ensured_target.id) == original_target["id"]
    assert ensured_target.business_name == "已确认销售表"
    assert ensured_target.description == "经过人工确认的销售业务范围。"
    assert ensured_target.context_facts["synonyms"] == ["table_005", "销售明细"]

    listed_scopes = await client.get(f"/api/v1/projects/{project.id}/semantic-scopes")
    assert listed_scopes.status_code == 200, listed_scopes.text
    listed_tables = [
        item for item in listed_scopes.json()["data"] if item["kind"] == "table"
    ]
    assert len(listed_tables) == 87
    listed_target = next(
        item for item in listed_tables if item["table_or_view"] == "main.table_005"
    )
    assert listed_target["id"] == original_target["id"] == metric["scope_id"]
    assert listed_target["business_name"] == "已确认销售表"
    assert listed_target["synonyms"] == ["table_005", "销售明细"]
    assert listed_target["direct_entry_count"] == 2
    catalog_only = next(
        item for item in listed_tables if item["table_or_view"] == "main.table_086"
    )
    assert catalog_only["context_facts"]["profile_status"] == "catalog_only"


@pytest.mark.asyncio
async def test_adopted_scope_presentation_overlays_scope_without_execution_validation(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    project, source = await _project_with_tables(db_session, "catalog_items_2024")
    created = await client.post(
        f"/api/v1/projects/{project.id}/knowledge",
        json={
            "key": "scope_presentation:product_2024",
            "value": "候选数据表名称：2024 年商品信息",
            "entry_type": "scope_presentation",
            "state": "candidate",
            "confidence": 0.8,
            "definition": {
                "version": 1,
                "kind": "scope_presentation",
                "scope_kind": "table",
                "source_logical_name": "经营仓库",
                "source_kind": "connection",
                "table_or_view": "catalog_items_2024",
                "business_name": "2024 年商品信息",
                "description": "记录 2024 年商品主数据及其业务属性。",
                "synonyms": ["catalog_items_2024", "商品主数据"],
                "example_questions": ["2024 年有哪些商品？"],
            },
            "validity": "unverified",
            "evidence": [],
            "source": "inferred",
        },
    )
    assert created.status_code == 200, created.text
    candidate = created.json()["data"]
    assert candidate["execution_state"] == "definition_only"
    assert candidate["allowed_actions"] == ["ignore", "remember"]
    before_adoption = await client.get(f"/api/v1/projects/{project.id}/semantic-scopes")
    assert before_adoption.status_code == 200, before_adoption.text
    unchanged_scope = next(
        item
        for item in before_adoption.json()["data"]
        if item["kind"] == "table"
        and item["table_or_view"] == "catalog_items_2024"
    )
    assert unchanged_scope["business_name"] == "catalog_items_2024"

    rejected_validation = await client.post(
        f"/api/v1/projects/{project.id}/knowledge/batch",
        json={
            "action": "queue_validation",
            "items": [
                {
                    "entry_id": candidate["id"],
                    "expected_active_revision_id": candidate["active_revision_id"],
                }
            ],
        },
    )
    assert rejected_validation.status_code == 409

    adopted = await client.post(
        f"/api/v1/projects/{project.id}/knowledge/batch",
        json={
            "action": "remember",
            "items": [
                {
                    "entry_id": candidate["id"],
                    "expected_active_revision_id": candidate["active_revision_id"],
                }
            ],
        },
    )
    assert adopted.status_code == 200, adopted.text
    adopted_entry = adopted.json()["data"]["items"][0]
    assert adopted_entry["state"] == "confirmed"
    assert adopted_entry["execution_state"] == "definition_only"
    assert adopted_entry["evidence"][-1]["kind"] == "scope_presentation_adopted"

    scopes = await client.get(f"/api/v1/projects/{project.id}/semantic-scopes")
    assert scopes.status_code == 200, scopes.text
    table_scope = next(
        item
        for item in scopes.json()["data"]
        if item["kind"] == "table"
        and item["table_or_view"] == "catalog_items_2024"
    )
    assert table_scope["business_name"] == "2024 年商品信息"
    assert table_scope["description"] == "记录 2024 年商品主数据及其业务属性。"
    assert table_scope["synonyms"] == ["catalog_items_2024", "商品主数据"]

    page = await client.get(
        f"/api/v1/projects/{project.id}/knowledge/page",
        params={"entry_type": "scope_presentation"},
    )
    assert page.status_code == 200, page.text
    assert page.json()["data"]["total"] == 1
    summary = await client.get(f"/api/v1/projects/{project.id}/knowledge/summary")
    assert summary.status_code == 200, summary.text
    assert summary.json()["data"]["active_total"] == 1
    assert summary.json()["data"]["confirmed_total"] == 1

    context = await load_project_context(db_session, project.id)
    stored = next(
        item
        for item in context.confirmed_knowledge
        if item["type"] == "scope_presentation"
    )
    assert stored["definition"]["synonyms"] == [
        "catalog_items_2024",
        "商品主数据",
    ]
    assert stored["scope_table_or_view"] == "catalog_items_2024"


@pytest.mark.asyncio
async def test_public_summary_hides_table_semantics_but_keeps_project_direct(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    project, _source = await _project_with_tables(db_session, "table_a")
    await _create_metric(client, project.id, key="metric:private", table="table_a")
    root = await client.post(
        f"/api/v1/projects/{project.id}/knowledge",
        json={
            "key": "rule:project",
            "value": "项目统一按自然月汇报",
            "entry_type": "business_rule",
            "state": "confirmed",
            "confidence": 1,
            "definition": {"kind": "receiptbi_note", "version": 1},
            "validity": "active",
            "evidence": [],
            "source": "user",
        },
    )
    assert root.status_code == 200, root.text

    context = await load_project_context(db_session, project.id)
    summary = context.public_summary()
    assert [item["key"] for item in summary["confirmed_knowledge"]] == ["rule:project"]
    assert {item["key"] for item in context.confirmed_knowledge} == {
        "metric:private",
        "rule:project",
    }


@pytest.mark.asyncio
async def test_legacy_exact_backfill_preserves_verified_proof(
    db_session: AsyncSession,
) -> None:
    project, _source = await _project_with_tables(db_session, "table_a")
    entry = SemanticEntry(
        project_id=project.id,
        scope_id=None,
        key="metric:legacy",
        value="历史已验证金额",
        entry_type="metric",
        state="confirmed",
        confidence=1,
        definition=_metric_definition("table_a"),
        validity="active",
        execution_state="verified",
        execution_details={"status": "verified", "proof": "kept"},
        evidence=[],
        source="user",
        is_active=True,
    )
    db_session.add(entry)
    await db_session.flush()
    await append_semantic_revision(
        db_session,
        entry,
        mutation_kind="legacy_created",
        actor_source="user",
    )
    previous_revision = entry.active_revision_id
    await db_session.commit()

    await load_project_context(db_session, project.id)
    await db_session.refresh(entry)
    assert entry.scope_id is not None
    assert entry.execution_state == "verified"
    assert entry.execution_details == {"status": "verified", "proof": "kept"}
    assert entry.active_revision_id != previous_revision


@pytest.mark.asyncio
async def test_logical_scope_survives_physical_source_replacement(
    db_session: AsyncSession,
) -> None:
    project, source = await _project_with_tables(db_session, "table_a")
    first_nodes = await ensure_semantic_scope_tree(db_session, project.id)
    first_table = next(node for node in first_nodes if node.kind == "table")
    first_id = first_table.id
    first_key = first_table.stable_key

    source.status = "superseded"
    replacement = ProjectDataSource(
        project_id=project.id,
        kind="connection",
        name="经营数据库 7 月",
        status="ready",
        profile_data=_connection_profile("table_a"),
    )
    db_session.add(replacement)
    await db_session.flush()

    second_nodes = await ensure_semantic_scope_tree(db_session, project.id)
    second_table = next(
        node for node in second_nodes if node.kind == "table" and node.is_active
    )
    assert second_table.id == first_id
    assert second_table.stable_key == first_key
    assert second_table.context_facts["source_id"] == str(replacement.id)


@pytest.mark.asyncio
async def test_pending_replacement_is_not_added_to_the_current_scope_tree(
    db_session: AsyncSession,
) -> None:
    project, current = await _project_with_tables(db_session, "table_a")
    first_nodes = await ensure_semantic_scope_tree(db_session, project.id)
    current_table = next(node for node in first_nodes if node.kind == "table")

    pending_profile = _connection_profile("table_b")
    pending_profile.update(
        {
            "is_current": False,
            "activation_state": "pending_confirmation",
            "replacement_of": str(current.id),
        }
    )
    pending = ProjectDataSource(
        project_id=project.id,
        kind="connection",
        name="经营数据库待确认版本",
        status="needs_confirmation",
        profile_data=pending_profile,
    )
    db_session.add(pending)
    await db_session.flush()

    nodes = await ensure_semantic_scope_tree(db_session, project.id)
    active_sources = [node for node in nodes if node.kind == "source" and node.is_active]
    active_tables = [node for node in nodes if node.kind == "table" and node.is_active]

    assert len(active_sources) == 1
    assert active_sources[0].context_facts["source_id"] == str(current.id)
    assert [node.table_or_view for node in active_tables] == ["table_a"]
    assert active_tables[0].id == current_table.id


@pytest.mark.asyncio
async def test_scope_tree_still_rejects_duplicate_current_logical_sources(
    db_session: AsyncSession,
) -> None:
    project, _source = await _project_with_tables(db_session, "table_a")
    duplicate_profile = _connection_profile("table_b")
    duplicate_profile["is_current"] = True
    db_session.add(
        ProjectDataSource(
            project_id=project.id,
            kind="connection",
            name="经营数据库重复当前版本",
            status="ready",
            profile_data=duplicate_profile,
        )
    )
    await db_session.flush()

    with pytest.raises(SemanticScopeResolutionError, match="逻辑名称缺失或重复"):
        await ensure_semantic_scope_tree(db_session, project.id)


@pytest.mark.asyncio
async def test_file_scope_extracts_only_evidence_backed_period_context(
    db_session: AsyncSession,
) -> None:
    project = Project(name="时间上下文")
    db_session.add(project)
    await db_session.flush()
    source = ProjectDataSource(
        project_id=project.id,
        kind="file",
        name="orders-2026-06.csv",
        format="csv",
        status="ready",
        profile_data={
            "logical_name": "orders_2026",
            "schema": {"columns": [{"name": "date", "dtype": "datetime64[ns]"}]},
            "preanalysis": {
                "candidate_roles": [
                    {
                        "column": "date",
                        "role": "time",
                        "range": {
                            "start": "2026-06-01T00:00:00",
                            "end": "2026-06-30T00:00:00",
                        },
                    }
                ]
            },
        },
    )
    db_session.add(source)
    await db_session.flush()

    nodes = await ensure_semantic_scope_tree(db_session, project.id)
    table = next(node for node in nodes if node.kind == "table")
    assert table.business_name == "orders-2026-06"
    assert table.table_or_view == "orders_2026"
    assert table.context_facts["year"] == 2026
    assert table.context_facts["month"] == 6
    assert table.context_facts["business_topic_status"] == "unconfirmed"
    assert table.description == "2026 年 6 月数据 · 业务主题待确认"
    assert "订单" not in table.description

    runtime = await load_project_context(db_session, project.id)
    runtime_table = next(
        item
        for item in runtime.semantic_scopes
        if item["kind"] == "table" and item["id"] == str(table.id)
    )
    assert runtime_table["context_facts"] == table.context_facts
    assert runtime_table["path"][-1]["id"] == str(table.id)


@pytest.mark.asyncio
async def test_scope_rows_are_direct_not_descendant_reads(
    db_session: AsyncSession,
) -> None:
    project, _source = await _project_with_tables(db_session, "table_a")
    nodes = await ensure_semantic_scope_tree(db_session, project.id)
    root = next(node for node in nodes if node.kind == "project")
    table = next(node for node in nodes if node.kind == "table")
    result = await db_session.execute(
        select(SemanticScopeNode).where(SemanticScopeNode.parent_id == root.id)
    )
    assert table.id not in {node.id for node in result.scalars()}
