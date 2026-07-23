"""HTTP contract for explicit, resumable semantic inventory jobs."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import projects as projects_api
from app.db.tables import (
    AppSettings,
    Connection,
    Project,
    ProjectDataSource,
    SemanticInventoryJob,
    SemanticInventoryJobItem,
)


async def _connection_source(
    db: AsyncSession,
    tmp_path: Path,
) -> tuple[Project, ProjectDataSource]:
    database_path = tmp_path / "inventory-api.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE orders (
                order_id INTEGER PRIMARY KEY,
                published_at TEXT,
                sales_amount REAL
            );
            """
        )
    project = Project(name="显式业务目录")
    connection = Connection(
        name="本地订单库",
        driver="sqlite",
        database_name=str(database_path),
    )
    db.add_all([project, connection])
    await db.flush()
    source = ProjectDataSource(
        project_id=project.id,
        connection_id=connection.id,
        kind="connection",
        name="本地订单库",
        format="sqlite",
        status="ready",
        profile_data={
            "logical_name": "本地订单库",
            "is_current": True,
            "preanalysis": {
                "relation_index": {
                    "relations": [
                        {
                            "schema": "main",
                            "name": "orders",
                            "kind": "table",
                            "comment": None,
                        }
                    ],
                    "complete": True,
                    "truncated": False,
                }
            },
        },
    )
    db.add(source)
    await db.commit()
    return project, source


@pytest.mark.asyncio
async def test_inventory_routes_require_a_click_and_keep_qualified_display_name(
    client,
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, source = await _connection_source(db_session, tmp_path)
    scheduled: list[object] = []
    monkeypatch.setattr(
        projects_api,
        "schedule_semantic_inventory_job",
        lambda job_id: scheduled.append(job_id),
    )

    response = await client.post(
        f"/api/v1/projects/{project.id}/sources/{source.id}/semantic-inventory-jobs",
        json={
            "locale": "zh",
            "tables": ["main.orders"],
            "depth": "structure",
        },
    )

    assert response.status_code == 202, response.text
    payload = response.json()["data"]
    assert payload["status"] == "queued"
    assert payload["progress"] == {
        "total": 1,
        "queued": 1,
        "running": 0,
        "succeeded": 0,
        "failed": 0,
        "cancelled": 0,
    }
    assert payload["items"] == []
    assert payload["tables"] == []
    assert [str(item) for item in scheduled] == [payload["id"]]

    items = await client.get(
        f"/api/v1/projects/{project.id}/sources/{source.id}/semantic-inventory-jobs/"
        f"{payload['id']}/items"
    )
    assert items.status_code == 200, items.text
    item_page = items.json()["data"]
    assert item_page["job_id"] == payload["id"]
    assert item_page["items"][0]["table"] == "main.orders"
    assert item_page["items"][0]["ordinal"] == 0
    assert item_page["next_after_ordinal"] is None
    assert item_page["has_more"] is False

    missing = await client.get(
        f"/api/v1/projects/{project.id}/sources/{source.id}/semantic-inventory-jobs/"
        f"{payload['id']}/items",
        params={"table": "main.missing"},
    )
    assert missing.status_code == 404, missing.text
    assert missing.json()["detail"]["code"] == "semantic_inventory_table_unknown"

    job = await db_session.get(SemanticInventoryJob, UUID(payload["id"]))
    assert job is not None
    job.details = {**dict(job.details or {}), "source_recommendation_count": 1}
    item_result = await db_session.execute(
        select(SemanticInventoryJobItem).where(SemanticInventoryJobItem.job_id == job.id)
    )
    stored_item = item_result.scalar_one()
    stored_item.status = "succeeded"
    stored_item.phase = "complete"
    stored_item.recommendation_batch_id = uuid4()
    stored_item.candidate_count = 2
    await db_session.commit()

    current = await client.get(
        f"/api/v1/projects/{project.id}/sources/{source.id}/semantic-inventory-jobs/current"
    )
    assert current.status_code == 200, current.text
    assert current.json()["data"]["id"] == payload["id"]
    assert current.json()["data"]["items"] == []
    assert current.json()["data"]["tables"] == []
    assert current.json()["data"]["candidate_count"] == 3
    assert current.json()["data"]["reviewable_count"] == 1
    assert current.json()["data"]["next_review_item"]["table"] == "main.orders"

    cancelled = await client.post(
        f"/api/v1/projects/{project.id}/sources/{source.id}/semantic-inventory-jobs/"
        f"{payload['id']}/cancel"
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["data"]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_inventory_click_respects_disabled_self_analysis(
    client,
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, source = await _connection_source(db_session, tmp_path)
    db_session.add(AppSettings(id=1, self_analysis_enabled=False))
    await db_session.commit()
    monkeypatch.setattr(
        projects_api,
        "schedule_semantic_inventory_job",
        lambda _job_id: None,
    )

    response = await client.post(
        f"/api/v1/projects/{project.id}/sources/{source.id}/semantic-inventory-jobs",
        json={
            "locale": "zh",
            "tables": ["main.orders"],
            "depth": "structure",
        },
    )

    assert response.status_code == 403, response.text
    assert "设置" in response.text
