"""Metadata-only relation directory refresh API tests."""

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import projects as projects_api
from app.db.tables import Connection, Project, ProjectDataSource, SemanticScopeNode
from app.services.database_adapters import BoundedRelationIndex


def _relation(index: int) -> dict[str, Any]:
    return {
        "name": f"table_{index:03d}",
        "schema": "main",
        "kind": "table",
        "comment": f"业务表 {index:03d}",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("relation_count", "truncated", "expected_total", "expected_total_at_least"),
    [
        (87, False, 87, 87),
        (512, True, None, 513),
    ],
)
async def test_relation_index_refresh_preserves_deep_profile_and_syncs_scope_tree(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    relation_count: int,
    truncated: bool,
    expected_total: int | None,
    expected_total_at_least: int,
) -> None:
    project = Project(name=f"旧版 {relation_count} 表项目")
    connection = Connection(
        name=f"旧版 {relation_count} 表数据库",
        driver="sqlite",
        database_name="unused.db",
    )
    db_session.add_all([project, connection])
    await db_session.flush()
    deep_tables = [
        {
            **_relation(index),
            "columns": [{"name": "id", "type": "INTEGER"}],
        }
        for index in range(24)
    ]
    source = ProjectDataSource(
        project_id=project.id,
        connection_id=connection.id,
        kind="connection",
        name="旧版经营数据库",
        format="sqlite",
        status="ready",
        profile_data={
            "logical_name": "经营数据库",
            "marker": "keep-existing-profile",
            "tables": deep_tables,
            "preanalysis": {
                "shape": {
                    "tables": 24,
                    "profiled_tables": 24,
                    "sampled_rows": 48,
                },
                "candidate_roles": [{"table": "table_000", "column": "id"}],
            },
        },
    )
    db_session.add(source)
    await db_session.commit()

    class MetadataOnlyManager:
        calls: list[int] = []

        def get_bounded_relation_index(
            self,
            *,
            max_relations: int,
        ) -> BoundedRelationIndex:
            self.calls.append(max_relations)
            return BoundedRelationIndex(
                relations=[_relation(index) for index in range(relation_count)],
                truncated=truncated,
                # Even if a driver forgets the sentinel count, truncation still
                # means there is at least one relation beyond the returned slice.
                unread_relations_at_least=0,
            )

    manager = MetadataOnlyManager()
    monkeypatch.setattr(
        projects_api,
        "create_database_manager",
        lambda _config: manager,
    )

    response = await client.post(
        f"/api/v1/projects/{project.id}/sources/{source.id}/relation-index"
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    index = data["relation_index"]
    assert manager.calls == [512]
    assert index["relations_loaded"] == relation_count
    assert index["relations_total"] == expected_total
    assert index["relations_total_at_least"] == expected_total_at_least
    assert index["complete"] is (not truncated)
    assert index["truncated"] is truncated
    assert index["unread_relations_at_least"] == int(truncated)
    assert data["semantic_scope_table_count"] == relation_count

    await db_session.refresh(source)
    profile = source.profile_data
    assert profile["marker"] == "keep-existing-profile"
    assert profile["tables"] == deep_tables
    assert profile["relation_index"] == index
    assert profile["preanalysis"]["relation_index"] == index
    assert profile["preanalysis"]["candidate_roles"] == [{"table": "table_000", "column": "id"}]
    assert profile["preanalysis"]["shape"]["tables"] == expected_total_at_least
    assert profile["preanalysis"]["shape"]["profiled_tables"] == 24
    assert profile["preanalysis"]["shape"]["sampled_rows"] == 48
    assert profile["preanalysis"]["shape"].get("tables_are_lower_bound") is (
        True if truncated else None
    )

    nodes_result = await db_session.execute(
        select(SemanticScopeNode).where(
            SemanticScopeNode.project_id == project.id,
            SemanticScopeNode.kind == "table",
            SemanticScopeNode.is_active.is_(True),
        )
    )
    source_table_nodes = [
        node
        for node in nodes_result.scalars()
        if str((node.context_facts or {}).get("source_id") or "") == str(source.id)
    ]
    assert len(source_table_nodes) == relation_count
    assert (
        next(
            node
            for node in source_table_nodes
            if node.table_or_view == f"main.table_{relation_count - 1:03d}"
        ).context_facts["profile_status"]
        == "catalog_only"
    )


@pytest.mark.asyncio
async def test_relation_index_refresh_rejects_ineligible_sources_and_localizes_failures(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = Project(name="目录刷新边界")
    connection = Connection(
        name="读取失败数据库",
        driver="sqlite",
        database_name="unused.db",
    )
    db_session.add_all([project, connection])
    await db_session.flush()
    file_source = ProjectDataSource(
        project_id=project.id,
        kind="file",
        name="orders.csv",
        format="csv",
        status="ready",
        profile_data={"marker": "file-unchanged"},
    )
    pending_source = ProjectDataSource(
        project_id=project.id,
        connection_id=connection.id,
        kind="connection",
        name="尚未准备数据库",
        format="sqlite",
        status="attached",
        profile_data={"marker": "pending-unchanged"},
    )
    failing_source = ProjectDataSource(
        project_id=project.id,
        connection_id=connection.id,
        kind="connection",
        name="读取失败数据库",
        format="sqlite",
        status="ready",
        profile_data={"marker": "failure-unchanged"},
    )
    db_session.add_all([file_source, pending_source, failing_source])
    await db_session.commit()

    factory_calls = 0

    class FailingMetadataManager:
        def get_bounded_relation_index(self, *, max_relations: int) -> BoundedRelationIndex:
            assert max_relations == 512
            raise RuntimeError("secret backend failure: password=do-not-leak")

    def manager_factory(_config: dict[str, Any]) -> FailingMetadataManager:
        nonlocal factory_calls
        factory_calls += 1
        return FailingMetadataManager()

    monkeypatch.setattr(projects_api, "create_database_manager", manager_factory)

    file_response = await client.post(
        f"/api/v1/projects/{project.id}/sources/{file_source.id}/relation-index"
    )
    pending_response = await client.post(
        f"/api/v1/projects/{project.id}/sources/{pending_source.id}/relation-index"
    )
    assert file_response.status_code == 409
    assert file_response.json()["detail"] == "只有数据库数据源可以刷新数据目录"
    assert pending_response.status_code == 409
    assert "先完成数据库数据源准备" in pending_response.json()["detail"]
    assert factory_calls == 0

    failed_response = await client.post(
        f"/api/v1/projects/{project.id}/sources/{failing_source.id}/relation-index"
    )
    assert failed_response.status_code == 503
    assert failed_response.json()["detail"] == "数据库目录暂时无法读取，请检查连接后重试"
    assert "do-not-leak" not in failed_response.text
    assert factory_calls == 1
    await db_session.refresh(failing_source)
    assert failing_source.profile_data == {"marker": "failure-unchanged"}
