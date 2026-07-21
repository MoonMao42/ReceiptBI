"""Fail-closed runtime loading for sanitation recipe drift."""

from __future__ import annotations

import json

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.tables import Project, ProjectDataSource, SemanticEntry
from app.services.project_context import _schema_signature, load_project_context


def _file_profile(
    logical_name: str,
    *,
    issues: list[dict] | None = None,
    activation_state: str | None = None,
    columns: list[dict] | None = None,
) -> dict:
    profile = {
        "logical_name": logical_name,
        "is_current": True,
        "summary": "数据整理完成",
        "issues": issues or [],
        "schema": {"columns": columns or [{"name": "store_id", "type": "string"}]},
    }
    if activation_state is not None:
        profile["activation_state"] = activation_state
    return profile


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "issue_code", "activation_state"),
    [
        ("first_import_recipe_drift", "recipe_replay_drift", None),
        ("same_source_input_changed", "recipe_input_changed", None),
        ("explicit_pending_activation", None, "pending_confirmation"),
    ],
)
async def test_active_looking_drifted_file_is_pending_and_hides_runtime_uris(
    db_session: AsyncSession,
    case: str,
    issue_code: str | None,
    activation_state: str | None,
) -> None:
    project = Project(name=f"配方漂移-{case}")
    db_session.add(project)
    await db_session.flush()
    issues = (
        [
            {
                "code": issue_code,
                "title": "整理方法需要核对",
                "detail": "输入已变化",
            }
        ]
        if issue_code
        else []
    )
    source = ProjectDataSource(
        project_id=project.id,
        kind="file",
        name="orders.csv",
        format="csv",
        status="ready",
        source_uri="/private/original/orders.csv",
        working_uri="/private/working/orders.parquet",
        profile_data=_file_profile(
            "orders",
            issues=issues,
            activation_state=activation_state,
        ),
    )
    db_session.add(source)
    await db_session.commit()

    context = await load_project_context(db_session, project.id)

    assert context.sources == []
    assert [item["id"] for item in context.pending_sources] == [str(source.id)]
    pending = context.pending_sources[0]
    assert pending["status"] == "needs_attention"
    assert pending["attention_reason"]
    assert "working_uri" not in pending
    assert "source_uri" not in pending
    public_payload = json.dumps(context.public_summary(), ensure_ascii=False)
    assert "/private/original" not in public_payload
    assert "/private/working" not in public_payload


@pytest.mark.asyncio
async def test_drifted_replacement_keeps_last_good_source_and_hides_its_candidate_relationship(
    db_session: AsyncSession,
) -> None:
    project = Project(name="月度订单配方漂移")
    db_session.add(project)
    await db_session.flush()
    order_columns = [{"name": "store_id", "type": "string"}]
    store_columns = [
        {"name": "store_id", "type": "string"},
        {"name": "store_name", "type": "string"},
    ]
    july = ProjectDataSource(
        project_id=project.id,
        kind="file",
        name="orders-july.csv",
        format="csv",
        status="ready",
        source_uri="/data/orders-july.csv",
        working_uri="/working/orders-july.parquet",
        profile_data=_file_profile("orders", columns=order_columns),
    )
    stores = ProjectDataSource(
        project_id=project.id,
        kind="file",
        name="stores.csv",
        format="csv",
        status="ready",
        source_uri="/data/stores.csv",
        working_uri="/working/stores.parquet",
        profile_data=_file_profile("stores", columns=store_columns),
    )
    august = ProjectDataSource(
        project_id=project.id,
        kind="file",
        name="orders-august.csv",
        format="csv",
        status="needs_confirmation",
        source_uri="/data/orders-august.csv",
        working_uri="/working/orders-august.parquet",
        profile_data=_file_profile(
            "orders",
            columns=order_columns,
            issues=[
                {
                    "code": "recipe_replay_drift",
                    "title": "上期整理方法未能完整复用",
                    "detail": "需要确认字段变化",
                }
            ],
        ),
    )
    db_session.add_all([july, stores, august])
    await db_session.flush()

    definition = {
        "version": 1,
        "left": {
            "source_logical_name": "orders",
            "source_kind": "file",
            "table_or_view": "orders",
            "column": "store_id",
            "data_type": "string",
            "schema_signature": _schema_signature(order_columns),
        },
        "right": {
            "source_logical_name": "stores",
            "source_kind": "file",
            "table_or_view": "stores",
            "column": "store_id",
            "data_type": "string",
            "schema_signature": _schema_signature(store_columns),
        },
        "normalization": "identifier",
        "cardinality": None,
        "default_join": "left",
        "minimum_left_match_rate": 0.8,
        "maximum_expansion_ratio": 1.2,
    }
    db_session.add_all(
        [
            SemanticEntry(
                project_id=project.id,
                key="relationship:confirmed-orders-stores",
                value="已确认的订单门店关系",
                entry_type="relationship",
                state="confirmed",
                confidence=1,
                definition=definition,
                validity="active",
                execution_state="verified",
                evidence=[{"source_id": str(july.id), "kind": "user_confirmation"}],
                source="user",
            ),
            SemanticEntry(
                project_id=project.id,
                key="relationship:confirmed-but-unverified",
                value="用户选择但尚未完成试跑的关系",
                entry_type="relationship",
                state="confirmed",
                confidence=1,
                definition=definition,
                validity="active",
                execution_state="needs_validation",
                evidence=[{"source_id": str(july.id), "kind": "user_correction"}],
                source="user",
            ),
            SemanticEntry(
                project_id=project.id,
                key="relationship:candidate-from-august",
                value="新一期数据推断出的关系",
                entry_type="relationship",
                state="candidate",
                confidence=0.55,
                definition=definition,
                validity="unverified",
                evidence=[
                    {
                        "kind": "matching_column_names",
                        "sources": [
                            "orders-august.csv.store_id",
                            "stores.csv.store_id",
                        ],
                    }
                ],
                source="inferred",
            ),
        ]
    )
    await db_session.commit()

    context = await load_project_context(db_session, project.id)

    assert {item["id"] for item in context.sources} == {str(july.id), str(stores.id)}
    assert [item["id"] for item in context.pending_sources] == [str(august.id)]
    assert list(context.executable_relationships) == ["relationship:confirmed-orders-stores"]
    assert any(
        item.get("key") == "relationship:confirmed-but-unverified"
        for item in context.candidate_relationships
    )
    assert not any(
        item.get("key") == "relationship:candidate-from-august"
        for item in context.candidate_relationships
    )
    assert all("orders-august.csv" not in str(item) for item in context.candidate_relationships)
    assert not any(
        item["key"] == "relationship:candidate-from-august" for item in context.candidate_knowledge
    )
    assert any(
        item["key"] == "relationship:candidate-from-august"
        and item["kind"] == "pending_source_candidate_hidden"
        for item in context.semantic_diagnostics
    )


@pytest.mark.asyncio
async def test_business_ambiguity_without_recipe_drift_remains_queryable(
    db_session: AsyncSession,
) -> None:
    project = Project(name="只需确认业务口径")
    db_session.add(project)
    await db_session.flush()
    source = ProjectDataSource(
        project_id=project.id,
        kind="file",
        name="orders.csv",
        format="csv",
        status="needs_confirmation",
        source_uri="/data/orders.csv",
        working_uri="/working/orders.parquet",
        profile_data={
            **_file_profile(
                "orders",
                issues=[
                    {
                        "code": "business_ambiguity",
                        "title": "退款口径需要确认",
                        "detail": "不同选择会改变收入结论",
                    }
                ],
            ),
            "ambiguities": [
                {
                    "key": "revenue_refund_policy",
                    "question": "退款订单是否计入收入？",
                }
            ],
        },
    )
    db_session.add(source)
    await db_session.commit()

    context = await load_project_context(db_session, project.id)

    assert context.pending_sources == []
    assert [item["id"] for item in context.sources] == [str(source.id)]
    assert context.sources[0]["working_uri"] == "/working/orders.parquet"
    assert context.sources[0]["source_uri"] == "/data/orders.csv"
