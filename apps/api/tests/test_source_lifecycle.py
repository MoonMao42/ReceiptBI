"""Focused lifecycle checks for failed and removed project sources."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import projects as projects_api
from app.core.config import settings
from app.db.tables import PreflightReportRecord, ProjectDataSource, SanitationRecipeRecord


async def _project(client: AsyncClient) -> str:
    response = await client.post("/api/v1/projects", json={"name": "数据生命周期"})
    assert response.status_code == 200, response.text
    return response.json()["data"]["id"]


async def _upload(client: AsyncClient, project_id: str, content: bytes) -> dict:
    response = await client.post(
        f"/api/v1/projects/{project_id}/sources/files",
        files={"file": ("orders.csv", content, "text/csv")},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


@pytest.mark.asyncio
async def test_preflight_failure_becomes_a_retryable_business_state(
    client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "WORKSPACE_ROOT", tmp_path / "projects")
    project_id = await _project(client)
    source = await _upload(client, project_id, b"order_id,amount\nO-1,12\n")

    def fail_preflight(*args, **kwargs):
        raise RuntimeError("parser exploded")

    monkeypatch.setattr(projects_api, "run_preflight", fail_preflight)
    failed = await client.post(
        f"/api/v1/projects/{project_id}/sources/{source['id']}/preflight"
    )

    assert failed.status_code == 409
    assert failed.json()["detail"] == "这份数据暂时没有整理成功，可以重新整理或移除来源"
    sources = (await client.get(f"/api/v1/projects/{project_id}/sources")).json()["data"]
    assert sources[0]["status"] == "error"
    assert "可以重新整理或移除来源" in sources[0]["profile_data"]["summary"]
    reports = (await client.get(f"/api/v1/projects/{project_id}/preflight")).json()["data"]
    assert reports[0]["status"] == "error"
    assert reports[0]["issues"][0]["code"] == "preflight_failed"


@pytest.mark.asyncio
async def test_remove_source_deletes_only_receiptbi_copy_and_records(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "WORKSPACE_ROOT", tmp_path / "projects")
    external_file = tmp_path / "customer-orders.csv"
    external_file.write_bytes(b"name,value\nA,1\nB,2\n")
    original_bytes = external_file.read_bytes()
    project_id = await _project(client)
    source = await _upload(client, project_id, original_bytes)
    prepared = await client.post(
        f"/api/v1/projects/{project_id}/sources/{source['id']}/preflight"
    )
    assert prepared.status_code == 200, prepared.text

    stored = await db_session.get(ProjectDataSource, UUID(source["id"]))
    assert stored is not None and stored.source_uri
    receiptbi_source_dir = Path(stored.source_uri).parent
    assert receiptbi_source_dir.exists()

    removed = await client.delete(
        f"/api/v1/projects/{project_id}/sources/{source['id']}"
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["data"]["external_data_untouched"] is True
    assert external_file.read_bytes() == original_bytes
    assert not receiptbi_source_dir.exists()
    assert (await client.get(f"/api/v1/projects/{project_id}/sources")).json()["data"] == []

    reports = await db_session.execute(
        select(PreflightReportRecord).where(
            PreflightReportRecord.data_source_id == UUID(source["id"])
        )
    )
    recipes = await db_session.execute(
        select(SanitationRecipeRecord).where(
            SanitationRecipeRecord.data_source_id == UUID(source["id"])
        )
    )
    assert reports.scalars().all() == []
    assert recipes.scalars().all() == []
