"""Project workspace API tests."""

import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import projects as projects_api
from app.db.tables import (
    AppSettings,
    Connection,
    PreflightReportRecord,
    Project,
    ProjectDataSource,
    SemanticEntry,
)
from app.services.database import QueryResult
from app.services.project_context import load_project_context, resolve_confirmed_ambiguity


@pytest.mark.asyncio
async def test_rename_project_trims_and_persists_name(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="新的分析项目")
    db_session.add(project)
    await db_session.commit()

    response = await client.patch(
        f"/api/v1/projects/{project.id}",
        json={"name": "  七月门店复盘  "},
    )

    assert response.status_code == 200
    assert response.json()["data"]["name"] == "七月门店复盘"
    await db_session.refresh(project)
    assert project.name == "七月门店复盘"


@pytest.mark.asyncio
async def test_rename_project_validates_normalized_name(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="新的分析项目")
    db_session.add(project)
    await db_session.commit()

    normalized_limit = await client.patch(
        f"/api/v1/projects/{project.id}",
        json={"name": f"  {'项' * 120}  "},
    )
    blank = await client.patch(
        f"/api/v1/projects/{project.id}",
        json={"name": "   "},
    )
    too_long = await client.patch(
        f"/api/v1/projects/{project.id}",
        json={"name": "项" * 121},
    )

    assert normalized_limit.status_code == 200
    assert normalized_limit.json()["data"]["name"] == "项" * 120
    assert blank.status_code == 422
    assert too_long.status_code == 422


@pytest.mark.asyncio
async def test_rename_missing_project_returns_not_found(client: AsyncClient):
    response = await client.patch(
        f"/api/v1/projects/{uuid4()}",
        json={"name": "不存在的项目"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_connection_sources_require_unique_project_names(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="同名来源保护")
    first_connection = Connection(
        name="一号经营库",
        driver="sqlite",
        database_name="first.db",
    )
    second_connection = Connection(
        name="二号经营库",
        driver="sqlite",
        database_name="second.db",
    )
    db_session.add_all([project, first_connection, second_connection])
    await db_session.commit()

    first = await client.post(
        f"/api/v1/projects/{project.id}/sources/connections",
        json={"connection_id": str(first_connection.id), "name": "经营库"},
    )
    duplicate = await client.post(
        f"/api/v1/projects/{project.id}/sources/connections",
        json={"connection_id": str(second_connection.id), "name": " 经营库 "},
    )

    assert first.status_code == 200, first.text
    assert duplicate.status_code == 409
    assert "同名数据源" in duplicate.json()["detail"]


@pytest.mark.asyncio
async def test_ambiguous_logical_source_name_disables_verified_relationship(
    db_session: AsyncSession,
):
    project = Project(name="关系来源消歧")
    first_connection = Connection(
        name="一号经营库",
        driver="sqlite",
        database_name="first.db",
    )
    second_connection = Connection(
        name="二号经营库",
        driver="sqlite",
        database_name="second.db",
    )
    db_session.add_all([project, first_connection, second_connection])
    await db_session.flush()
    table_catalog = [
        {
            "name": "orders",
            "columns": [{"name": "store_id", "type": "TEXT"}],
        },
        {
            "name": "stores",
            "columns": [{"name": "id", "type": "TEXT"}],
        },
    ]
    sources = [
        ProjectDataSource(
            project_id=project.id,
            connection_id=connection.id,
            kind="connection",
            name="经营库",
            format="sqlite",
            status="ready",
            profile_data={
                "logical_name": "经营库",
                "is_current": True,
                "tables": table_catalog,
            },
        )
        for connection in (first_connection, second_connection)
    ]
    db_session.add_all(sources)
    entry = SemanticEntry(
        project_id=project.id,
        key="relationship:orders_to_stores",
        value="订单关联门店",
        entry_type="relationship",
        state="confirmed",
        confidence=1,
        validity="active",
        execution_state="verified",
        definition={
            "version": 1,
            "left": {
                "source_logical_name": "经营库",
                "source_kind": "connection",
                "table_or_view": "orders",
                "column": "store_id",
                "data_type": "TEXT",
                "schema_signature": "a" * 64,
            },
            "right": {
                "source_logical_name": "经营库",
                "source_kind": "connection",
                "table_or_view": "stores",
                "column": "id",
                "data_type": "TEXT",
                "schema_signature": "b" * 64,
            },
            "normalization": "exact",
            "cardinality": "many_to_one",
            "default_join": "left",
            "minimum_left_match_rate": 0.8,
            "maximum_expansion_ratio": 1.2,
        },
        evidence=[{"kind": "validated_join"}],
        source="user",
    )
    db_session.add(entry)
    await db_session.commit()

    context = await load_project_context(db_session, project.id)

    assert entry.key not in context.executable_relationships
    assert any(
        diagnostic["key"] == entry.key and diagnostic["kind"] == "ambiguous_relationship_source"
        for diagnostic in context.semantic_diagnostics
    )


def test_relationship_candidate_identity_includes_physical_source_scope() -> None:
    left = {
        "source_logical_name": "经营库",
        "source_kind": "connection",
        "table_or_view": "orders",
        "column": "store_id",
    }
    right = {
        "source_logical_name": "经营库",
        "source_kind": "connection",
        "table_or_view": "stores",
        "column": "id",
    }

    first = projects_api._relationship_pair_identity(
        left,
        right,
        left_source_id="source-a",
        right_source_id="source-a",
    )
    second = projects_api._relationship_pair_identity(
        left,
        right,
        left_source_id="source-b",
        right_source_id="source-b",
    )

    assert first != second


@pytest.mark.asyncio
async def test_suggested_questions_fall_back_to_current_preflight_context(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    project = Project(name="七月经营复盘")
    db_session.add(project)
    await db_session.flush()
    source = ProjectDataSource(
        project_id=project.id,
        kind="file",
        name="七月门店订单.xlsx",
        format="xlsx",
        status="ready",
        profile_data={
            "is_current": True,
            "preanalysis": {
                "shape": {"rows": 1820, "columns": 8},
                "candidate_roles": [
                    {"column": "order_date", "role": "time", "missing": 0},
                    {"column": "net_revenue", "role": "measure", "missing": 3},
                    {"column": "store_name", "role": "dimension", "missing": 0},
                ],
            },
        },
    )
    db_session.add(source)
    db_session.add(
        SemanticEntry(
            project_id=project.id,
            key="revenue_policy",
            value="收入按实付金额计算，退款需要扣除",
            entry_type="business_rule",
            state="confirmed",
            confidence=1,
            validity="active",
            evidence=[{"kind": "user_confirmation"}],
            source="user",
        )
    )
    await db_session.commit()
    ai_suggestions = AsyncMock(return_value=None)
    monkeypatch.setattr(projects_api, "_ai_suggestions", ai_suggestions)

    response = await client.post(
        f"/api/v1/projects/{project.id}/suggested-questions",
        json={},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["generated_by"] == "preflight"
    assert len(payload["context_signature"]) == 64
    assert [item["label"] for item in payload["items"]] == [
        "先找出最值得关注的问题",
        "看看变化从哪里开始",
        "比较不同业务分组",
    ]
    assert all("七月门店订单.xlsx" in item["prompt"] for item in payload["items"])
    assert all("SQL" not in item["prompt"] for item in payload["items"])
    ai_suggestions.assert_awaited_once()
    suggestion_request = ai_suggestions.await_args.args[1]
    assert suggestion_request.locale == "zh"
    suggestion_context = ai_suggestions.await_args.args[2]
    assert suggestion_context["confirmed_business_context"] == [
        {"type": "business_rule", "value": "收入按实付金额计算，退款需要扣除"}
    ]


@pytest.mark.asyncio
async def test_suggested_questions_localize_system_fallbacks_in_english(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    project = Project(name="July business review")
    db_session.add(project)
    await db_session.flush()
    db_session.add(
        ProjectDataSource(
            project_id=project.id,
            kind="file",
            name="七月门店订单.xlsx",
            format="xlsx",
            status="ready",
            profile_data={
                "is_current": True,
                "preanalysis": {
                    "candidate_roles": [
                        {"column": "order_date", "role": "time", "missing": 0},
                        {"column": "net_revenue", "role": "measure", "missing": 3},
                        {"column": "store_name", "role": "dimension", "missing": 0},
                    ],
                },
            },
        )
    )
    await db_session.commit()
    ai_suggestions = AsyncMock(return_value=None)
    monkeypatch.setattr(projects_api, "_ai_suggestions", ai_suggestions)

    response = await client.post(
        f"/api/v1/projects/{project.id}/suggested-questions",
        json={"locale": "en"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    assert payload["generated_by"] == "preflight"
    assert [item["label"] for item in payload["items"]] == [
        "Find the most important issue",
        "See where the change began",
        "Compare business groups",
    ]
    assert all("七月门店订单.xlsx" in item["prompt"] for item in payload["items"])
    assert all(item["reason"] for item in payload["items"])
    ai_suggestions.assert_awaited_once()
    suggestion_request = ai_suggestions.await_args.args[1]
    assert suggestion_request.locale == "en"


@pytest.mark.asyncio
async def test_suggested_questions_dedupe_model_output_and_fill_distinct_fallbacks(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    project = Project(name="建议去重测试")
    db_session.add(project)
    await db_session.flush()
    db_session.add(
        ProjectDataSource(
            project_id=project.id,
            kind="connection",
            name="业务数据库",
            format="sqlite",
            status="ready",
            profile_data={"is_current": True, "preanalysis": {}},
        )
    )
    await db_session.commit()
    repeated = projects_api.SuggestedQuestion(
        label="检查数据能回答什么",
        prompt="检查业务数据库目前可以可靠回答哪些经营问题。",
        reason="先确认数据边界",
    )
    monkeypatch.setattr(
        projects_api,
        "_ai_suggestions",
        AsyncMock(return_value=[repeated, repeated, repeated]),
    )

    response = await client.post(
        f"/api/v1/projects/{project.id}/suggested-questions",
        json={},
    )

    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    assert payload["generated_by"] == "ai"
    assert len(payload["items"]) == 3
    assert len({item["prompt"] for item in payload["items"]}) == 3


@pytest.mark.asyncio
async def test_suggested_questions_are_empty_without_ready_sources(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    project = Project(name="空项目")
    db_session.add(project)
    await db_session.commit()
    ai_suggestions = AsyncMock(return_value=None)
    monkeypatch.setattr(projects_api, "_ai_suggestions", ai_suggestions)

    response = await client.post(
        f"/api/v1/projects/{project.id}/suggested-questions",
        json={},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["items"] == []
    assert payload["generated_by"] == "preflight"
    ai_suggestions.assert_not_awaited()


@pytest.mark.asyncio
async def test_suggested_questions_require_explicit_permission_without_calling_model(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    project = Project(name="关闭分析建议")
    db_session.add_all(
        [
            project,
            AppSettings(id=1, self_analysis_enabled=False),
        ]
    )
    await db_session.flush()
    db_session.add(
        ProjectDataSource(
            project_id=project.id,
            kind="file",
            name="订单.csv",
            format="csv",
            status="ready",
            profile_data={"is_current": True},
        )
    )
    await db_session.commit()
    ai_suggestions = AsyncMock(return_value=[])
    monkeypatch.setattr(projects_api, "_ai_suggestions", ai_suggestions)

    response = await client.post(
        f"/api/v1/projects/{project.id}/suggested-questions",
        json={},
    )

    assert response.status_code == 403
    assert "分析建议已在设置中关闭" in response.json()["detail"]
    ai_suggestions.assert_not_awaited()


@pytest.mark.asyncio
async def test_user_dismissed_candidate_is_not_reused_by_runtime(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="候选理解测试")
    db_session.add(project)
    await db_session.flush()
    entry = SemanticEntry(
        project_id=project.id,
        key="candidate:discount",
        value="折扣代表亏损",
        entry_type="business_rule",
        state="candidate",
        confidence=0.6,
        validity="active",
        evidence=[{"kind": "inference"}],
        source="inferred",
    )
    db_session.add(entry)
    await db_session.commit()

    response = await client.put(
        f"/api/v1/projects/{project.id}/knowledge/{entry.id}",
        json={
            "validity": "stale",
            "source": "user",
            "evidence": [{"kind": "user_rejection"}],
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["source"] == "user"
    context = await load_project_context(db_session, project.id)
    assert not any(item["key"] == entry.key for item in context.candidate_knowledge)
    assert any(
        item["key"] == entry.key and item["kind"] == "inactive_knowledge_hidden"
        for item in context.semantic_diagnostics
    )

    await projects_api._upsert_candidate_knowledge(
        db_session,
        project_id=project.id,
        key=entry.key,
        value="预检再次推断折扣代表亏损",
        entry_type="business_rule",
        confidence=0.9,
        evidence=[{"kind": "preflight"}],
    )
    await db_session.commit()
    await db_session.refresh(entry)
    assert entry.validity == "stale"
    assert entry.source == "user"
    assert entry.value == "折扣代表亏损"


@pytest.mark.asyncio
async def test_preflight_reuses_only_active_non_stale_confirmed_answers(
    db_session: AsyncSession,
):
    project = Project(name="只复用仍有效的口径")
    db_session.add(project)
    await db_session.flush()
    db_session.add_all(
        [
            SemanticEntry(
                project_id=project.id,
                key="stale_answer",
                value="已经失效",
                entry_type="business_rule",
                state="confirmed",
                confidence=1,
                validity="stale",
                is_active=True,
                source="user",
            ),
            SemanticEntry(
                project_id=project.id,
                key="inactive_answer",
                value="已经停用",
                entry_type="business_rule",
                state="locked",
                confidence=1,
                validity="active",
                is_active=False,
                source="user",
            ),
            SemanticEntry(
                project_id=project.id,
                key="refund_handling",
                value="收入扣除退款订单",
                entry_type="business_rule",
                state="locked",
                confidence=1,
                validity="active",
                is_active=True,
                source="user",
            ),
        ]
    )
    await db_session.commit()
    preflight = SimpleNamespace(
        ambiguities=[
            {"key": "stale_answer"},
            {"key": "inactive_answer"},
            {
                "key": "revenue_refund_policy",
                "question": "计算收入时，退款订单需要扣除吗？",
                "options": ["收入扣除退款订单", "收入保留退款订单"],
            },
        ],
        issues=[],
        status="needs_confirmation",
        summary="数据已准备好，有 3 个业务口径需要确认",
    )

    await projects_api._reuse_confirmed_preflight_answers(
        db_session,
        project.id,
        preflight,
    )

    assert {item["key"] for item in preflight.ambiguities} == {
        "stale_answer",
        "inactive_answer",
    }
    assert preflight.issues[-1]["code"] == "confirmed_knowledge_reused"
    assert preflight.issues[-1]["count"] == 1


@pytest.mark.asyncio
async def test_conflicting_decision_aliases_do_not_suppress_preflight_question(
    db_session: AsyncSession,
):
    project = Project(name="冲突口径仍需确认")
    db_session.add(project)
    await db_session.flush()
    db_session.add_all(
        [
            SemanticEntry(
                project_id=project.id,
                key="revenue_refund_policy",
                value="收入扣除退款订单",
                entry_type="business_rule",
                state="confirmed",
                confidence=1,
                validity="active",
                is_active=True,
                source="user",
            ),
            SemanticEntry(
                project_id=project.id,
                key="refund_policy",
                value="收入保留退款订单",
                entry_type="business_rule",
                state="locked",
                confidence=1,
                validity="active",
                is_active=True,
                source="user",
            ),
        ]
    )
    await db_session.commit()
    ambiguity = {
        "key": "revenue_refund_policy",
        "question": "计算收入时，退款订单需要扣除吗？",
        "options": ["收入扣除退款订单", "收入保留退款订单"],
    }
    preflight = SimpleNamespace(
        ambiguities=[ambiguity],
        issues=[],
        status="needs_confirmation",
        summary="数据已准备好，有 1 个业务口径需要确认",
    )

    await projects_api._reuse_confirmed_preflight_answers(
        db_session,
        project.id,
        preflight,
    )

    assert preflight.ambiguities == [ambiguity]
    assert preflight.issues == []
    assert preflight.status == "needs_confirmation"


@pytest.mark.asyncio
async def test_alias_key_resolves_the_canonical_preflight_question(
    db_session: AsyncSession,
):
    project = Project(name="稳定业务问题")
    db_session.add(project)
    await db_session.flush()
    ambiguity = {
        "key": "revenue_refund_policy",
        "question": "计算收入时，退款订单需要扣除吗？",
        "reason": "不同处理会改变收入结论",
        "options": ["收入扣除退款订单", "收入保留退款订单"],
    }
    source = ProjectDataSource(
        project_id=project.id,
        kind="file",
        name="orders.csv",
        format="csv",
        status="needs_confirmation",
        profile_data={
            "is_current": True,
            "summary": "数据已准备好，有 1 个业务口径需要确认",
            "ambiguities": [ambiguity],
        },
    )
    db_session.add(source)
    await db_session.flush()
    report = PreflightReportRecord(
        project_id=project.id,
        data_source_id=source.id,
        status="needs_confirmation",
        summary="数据已准备好，有 1 个业务口径需要确认",
        issues=[],
        ambiguities=[ambiguity],
        inferred_schema={},
        source_snapshot={},
    )
    db_session.add(report)
    await db_session.commit()

    await resolve_confirmed_ambiguity(db_session, project.id, "refund_handling")
    await db_session.commit()
    await db_session.refresh(report)
    await db_session.refresh(source)

    assert report.ambiguities == []
    assert report.status == "ready"
    assert (source.profile_data or {})["ambiguities"] == []
    assert source.status == "ready"


@pytest.mark.asyncio
async def test_project_context_dual_reads_one_legacy_decision_alias(
    db_session: AsyncSession,
):
    project = Project(name="兼容旧口径键")
    db_session.add(project)
    await db_session.flush()
    db_session.add(
        SemanticEntry(
            project_id=project.id,
            key="refund_policy",
            value="收入扣除退款订单",
            entry_type="business_rule",
            state="locked",
            confidence=1,
            validity="active",
            is_active=True,
            source="user",
        )
    )
    await db_session.commit()

    context = await load_project_context(db_session, project.id)

    assert [item["key"] for item in context.confirmed_knowledge] == ["revenue_refund_policy"]
    assert context.confirmed_knowledge[0]["state"] == "locked"


@pytest.mark.asyncio
async def test_project_context_fails_closed_on_conflicting_decision_aliases(
    db_session: AsyncSession,
):
    project = Project(name="拒绝冲突旧口径")
    db_session.add(project)
    await db_session.flush()
    db_session.add_all(
        [
            SemanticEntry(
                project_id=project.id,
                key="revenue_refund_policy",
                value="收入扣除退款订单",
                entry_type="business_rule",
                state="confirmed",
                confidence=1,
                validity="active",
                is_active=True,
                source="user",
            ),
            SemanticEntry(
                project_id=project.id,
                key="refund_handling",
                value="收入保留退款订单",
                entry_type="business_rule",
                state="locked",
                confidence=1,
                validity="active",
                is_active=True,
                source="user",
            ),
        ]
    )
    await db_session.commit()

    context = await load_project_context(db_session, project.id)

    assert not any(item["key"] == "revenue_refund_policy" for item in context.confirmed_knowledge)
    assert any(
        item["key"] == "revenue_refund_policy" and item["kind"] == "decision_slot_conflict"
        for item in context.semantic_diagnostics
    )


@pytest.mark.asyncio
async def test_database_preflight_persists_bounded_value_context_for_the_project(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    project = Project(name="数据库值画像")
    connection = Connection(
        name="只读门店库",
        driver="sqlite",
        database_name="ignored.db",
    )
    db_session.add_all([project, connection])
    await db_session.flush()
    source = ProjectDataSource(
        project_id=project.id,
        connection_id=connection.id,
        kind="connection",
        name="门店库",
        format="sqlite",
        status="attached",
        profile_data={},
    )
    db_session.add(source)
    await db_session.commit()

    class ProfileManager:
        def get_schema_catalog(self):
            return [
                {
                    "name": "orders",
                    "columns": [
                        {"name": "order_id", "type": "TEXT"},
                        {"name": "order_date", "type": "TEXT"},
                        {"name": "amount", "type": "REAL"},
                        {"name": "refund_status", "type": "TEXT"},
                    ],
                }
            ]

        def sample_table(self, table_name, columns, **kwargs):
            assert table_name == "orders"
            assert columns == ["order_id", "order_date", "amount", "refund_status"]
            assert kwargs["max_rows"] == 257
            return QueryResult(
                data=[
                    {
                        "order_id": f"O-{index}",
                        "order_date": f"2026-07-{index + 1:02d}",
                        "amount": 10 + index,
                        "refund_status": "已退款" if index == 0 else "未退款",
                    }
                    for index in range(4)
                ],
                rows_count=4,
            )

    monkeypatch.setattr(
        projects_api,
        "create_database_manager",
        lambda _config: ProfileManager(),
    )

    response = await client.post(f"/api/v1/projects/{project.id}/sources/{source.id}/preflight")

    assert response.status_code == 200, response.text
    report = response.json()["data"]
    assert report["status"] == "ready"
    assert report["source_snapshot"]["read_only"] is True
    assert report["source_snapshot"]["preanalysis"]["shape"] == {
        "tables": 1,
        "profiled_tables": 1,
        "columns": 4,
        "sampled_rows": 4,
        "rows_are_sampled": True,
    }
    roles = {
        item["column"]: item for item in report["source_snapshot"]["preanalysis"]["candidate_roles"]
    }
    assert roles["order_id"]["value_visibility"] == "suppressed_identifier"
    assert roles["order_date"]["role"] == "time"
    assert roles["amount"]["role"] == "measure"
    assert {item["value"] for item in roles["refund_status"]["top_values"]} == {
        "已退款",
        "未退款",
    }


@pytest.mark.asyncio
async def test_preflight_requires_explicit_permission_and_preserves_attached_source(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="关闭数据预处理")
    db_session.add_all(
        [
            project,
            AppSettings(id=1, preprocessing_enabled=False),
        ]
    )
    await db_session.flush()
    source = ProjectDataSource(
        project_id=project.id,
        kind="file",
        name="尚未读取.csv",
        format="csv",
        status="attached",
        profile_data={},
    )
    db_session.add(source)
    await db_session.commit()

    response = await client.post(f"/api/v1/projects/{project.id}/sources/{source.id}/preflight")

    assert response.status_code == 403
    assert "数据预处理已在设置中关闭" in response.json()["detail"]
    await db_session.refresh(source)
    assert source.status == "attached"


@pytest.mark.asyncio
async def test_database_foreign_key_becomes_unverified_project_relationship_candidate(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path,
):
    database_path = tmp_path / "shops.db"
    with sqlite3.connect(database_path) as connection_db:
        connection_db.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE stores (store_code TEXT PRIMARY KEY, name TEXT);
            CREATE TABLE orders (
                order_id TEXT PRIMARY KEY,
                shop_code TEXT NOT NULL,
                amount REAL,
                FOREIGN KEY (shop_code) REFERENCES stores(store_code)
            );
            INSERT INTO stores VALUES ('S-1', '一店'), ('S-2', '二店');
            INSERT INTO orders VALUES ('O-1', 'S-1', 12), ('O-2', 'S-2', 18);
            """
        )

    project = Project(name="约束关系候选")
    connection = Connection(
        name="门店订单库",
        driver="sqlite",
        database_name=str(database_path),
    )
    db_session.add_all([project, connection])
    await db_session.flush()
    source = ProjectDataSource(
        project_id=project.id,
        connection_id=connection.id,
        kind="connection",
        name="门店订单库",
        format="sqlite",
        status="attached",
        profile_data={},
    )
    db_session.add(source)
    await db_session.commit()

    response = await client.post(f"/api/v1/projects/{project.id}/sources/{source.id}/preflight")
    assert response.status_code == 200, response.text

    entries_result = await db_session.execute(
        select(SemanticEntry).where(SemanticEntry.project_id == project.id)
    )
    relationships = [
        entry
        for entry in entries_result.scalars()
        if entry.entry_type == "relationship" and entry.key.startswith("relationship_candidate:fk:")
    ]
    assert len(relationships) == 1
    candidate = relationships[0]
    assert candidate.state == "candidate"
    assert candidate.validity == "unverified"
    assert candidate.definition["left"]["column"] == "shop_code"
    assert candidate.definition["right"]["column"] == "store_code"
    assert candidate.definition["cardinality"] == "many_to_one"
    assert candidate.evidence[0]["kind"] == "declared_foreign_key"
    assert candidate.evidence[0]["automatic_confirmation"] is False
    assert candidate.evidence[0]["requires_value_validation"] is True

    await db_session.refresh(source)
    assert source.status == "ready"
    assert source.profile_data["preanalysis"]["read_only"] is True
    context = await load_project_context(db_session, project.id)
    assert context.sources[0]["profile"]["preanalysis"]["candidate_roles"]
