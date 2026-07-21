"""Acceptance tests for immutable originals and monthly sanitation replay."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pandas as pd
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import projects as projects_api
from app.core.config import settings
from app.db.tables import ProjectDataSource, SanitationRecipeRecord
from app.services.data_preflight import fingerprint_file
from app.services.project_context import load_project_context


async def _upload_csv(
    client: AsyncClient,
    project_id: str,
    filename: str,
    content: str,
) -> dict:
    response = await client.post(
        f"/api/v1/projects/{project_id}/sources/files",
        files={"file": (filename, content.encode("utf-8"), "text/csv")},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


@pytest.mark.asyncio
async def test_failed_reapply_keeps_the_last_trusted_working_copy(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "WORKSPACE_ROOT", tmp_path / "projects")
    created = await client.post("/api/v1/projects", json={"name": "可信工作副本"})
    project_id = created.json()["data"]["id"]
    source = await _upload_csv(
        client,
        project_id,
        "orders.csv",
        "order_id,amount\nO-1,32\nO-2,28\n",
    )
    preflight = await client.post(
        f"/api/v1/projects/{project_id}/sources/{source['id']}/preflight"
    )
    assert preflight.status_code == 200, preflight.text

    source_row = await db_session.get(ProjectDataSource, UUID(source["id"]))
    assert source_row is not None and source_row.working_uri
    trusted_uri = source_row.working_uri
    trusted_path = Path(trusted_uri)
    trusted_fingerprint = fingerprint_file(trusted_path)
    recipe = next(
        item
        for item in (await client.get(f"/api/v1/projects/{project_id}/recipes")).json()["data"]
        if item["data_source_id"] == source["id"]
    )

    def fail_after_writing_attempt(
        _source_path: Path,
        output_dir: Path,
        recipe_operations: list[dict] | None = None,
    ):
        del recipe_operations
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "analysis-ready.parquet").write_bytes(b"failed-attempt")
        raise RuntimeError("simulated sanitation failure")

    monkeypatch.setattr(projects_api, "run_preflight", fail_after_writing_attempt)
    failed = await client.post(
        f"/api/v1/projects/{project_id}/recipes/{recipe['id']}/reapply"
    )
    assert failed.status_code == 409, failed.text
    assert "仍使用上一次成功副本" in failed.json()["detail"]

    await db_session.refresh(source_row)
    assert source_row.status == "ready"
    assert source_row.working_uri == trusted_uri
    assert (source_row.profile_data or {})["is_current"] is True
    assert fingerprint_file(trusted_path) == trusted_fingerprint
    context = await load_project_context(db_session, UUID(project_id))
    assert [item["id"] for item in context.sources] == [source["id"]]


@pytest.mark.asyncio
async def test_failed_first_preflight_never_becomes_a_runtime_source(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "WORKSPACE_ROOT", tmp_path / "projects")
    created = await client.post("/api/v1/projects", json={"name": "失败来源隔离"})
    project_id = created.json()["data"]["id"]
    source = await _upload_csv(
        client,
        project_id,
        "broken.csv",
        "order_id,amount\nO-1,32\n",
    )

    def fail_preflight(
        _source_path: Path,
        _output_dir: Path,
        recipe_operations: list[dict] | None = None,
    ):
        del recipe_operations
        raise RuntimeError("simulated first preflight failure")

    monkeypatch.setattr(projects_api, "run_preflight", fail_preflight)
    failed = await client.post(
        f"/api/v1/projects/{project_id}/sources/{source['id']}/preflight"
    )
    assert failed.status_code == 409, failed.text

    source_row = await db_session.get(ProjectDataSource, UUID(source["id"]))
    assert source_row is not None
    assert source_row.status == "error"
    assert source_row.working_uri is None
    assert (source_row.profile_data or {})["is_current"] is False
    assert (source_row.profile_data or {})["activation_state"] == "failed"
    context = await load_project_context(db_session, UUID(project_id))
    assert context.sources == []
    assert [item["id"] for item in context.pending_sources] == [source["id"]]


@pytest.mark.asyncio
async def test_severe_monthly_drift_still_replays_series_recipe_without_touching_originals(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "WORKSPACE_ROOT", tmp_path / "projects")
    created = await client.post("/api/v1/projects", json={"name": "月度订单"})
    project_id = created.json()["data"]["id"]
    july = await _upload_csv(
        client,
        project_id,
        "orders-july.csv",
        (
            "order_id,store_id,amount,date,refund_status\n"
            "O-1,S-1,¥32.00,2026/07/01,no\n"
            "O-1,S-1,¥32.00,2026/07/01,no\n"
            "合计,,,,\n"
        ),
    )
    july_row = await db_session.get(ProjectDataSource, UUID(july["id"]))
    assert july_row is not None and july_row.source_uri
    july_original = Path(july_row.source_uri)
    july_fingerprint = fingerprint_file(july_original)

    july_preflight = await client.post(
        f"/api/v1/projects/{project_id}/sources/{july['id']}/preflight"
    )
    assert july_preflight.status_code == 200, july_preflight.text
    july_recipe = next(
        item
        for item in (await client.get(f"/api/v1/projects/{project_id}/recipes")).json()["data"]
        if item["data_source_id"] == july["id"]
    )
    july_operations = {item["operation"] for item in july_recipe["operations"]}
    assert {
        "drop_exact_duplicates",
        "exclude_summary_rows",
        "normalize_currency",
    } <= july_operations
    assert fingerprint_file(july_original) == july_fingerprint

    august = await _upload_csv(
        client,
        project_id,
        "orders-august.csv",
        (
            "订单编号,门店编码,支付金额,下单时间,退款状态,区域\n"
            "O-2,S-2,¥28.00,2026/08/01,否,华东\n"
            "O-3,S-3,30,2026-08-02,否,华南\n"
        ),
    )
    august_row = await db_session.get(ProjectDataSource, UUID(august["id"]))
    assert august_row is not None and august_row.source_uri
    august_original = Path(august_row.source_uri)
    august_fingerprint = fingerprint_file(august_original)

    replayed = await client.post(f"/api/v1/projects/{project_id}/sources/{august['id']}/preflight")
    assert replayed.status_code == 200, replayed.text
    report = replayed.json()["data"]
    issue_codes = {item["code"] for item in report["issues"]}
    assert {"recipe_replay_drift", "schema_drift"} <= issue_codes
    assert report["status"] == "needs_confirmation"
    drift = report["source_snapshot"]["schema_drift"]
    assert drift["matched_by"] == "source_series"
    assert drift["overlap_ratio"] == 0
    assert drift["requires_confirmation"] is True
    assert set(drift["removed_columns"]) == {
        "amount",
        "date",
        "order_id",
        "refund_status",
        "store_id",
    }
    assert report["source_snapshot"]["recipe_replay"]["requested_steps"] > 0
    assert report["source_snapshot"]["recipe_replay"]["drift"]

    await db_session.refresh(july_row)
    await db_session.refresh(august_row)
    # July contains a refund column but no observed refunded order, so the choice cannot
    # change this month's result and should not block the current trusted version.
    assert july_row.status == "ready"
    assert (july_row.profile_data or {})["is_current"] is True
    assert august_row.status == "needs_confirmation"
    assert (august_row.profile_data or {})["is_current"] is False
    assert (august_row.profile_data or {})["replacement_of"] == july["id"]
    replacement = report["source_snapshot"]["replacement"]
    assert replacement == {
        "status": "pending_confirmation",
        "replaces_source_id": july["id"],
        "active_source_id": july["id"],
    }
    runtime_context = await load_project_context(db_session, UUID(project_id))
    assert [item["id"] for item in runtime_context.sources] == [july["id"]]
    assert [item["id"] for item in runtime_context.pending_sources] == [august["id"]]
    assert (
        runtime_context.public_summary()["pending_sources"][0]["replaces_source_id"] == july["id"]
    )

    confirmed = await client.post(
        f"/api/v1/projects/{project_id}/knowledge",
        json={
            "key": "revenue_refund_policy",
            "value": "收入扣除退款订单",
            "state": "locked",
            "confidence": 1,
            "source": "user",
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    await db_session.refresh(july_row)
    await db_session.refresh(august_row)
    assert july_row.status == "ready"
    assert august_row.status == "needs_confirmation"
    assert (august_row.profile_data or {})["is_current"] is False
    confirmed_context = await load_project_context(db_session, UUID(project_id))
    assert [item["id"] for item in confirmed_context.sources] == [july["id"]]
    assert [item["id"] for item in confirmed_context.pending_sources] == [august["id"]]

    assert fingerprint_file(july_original) == july_fingerprint
    assert fingerprint_file(august_original) == august_fingerprint
    assert august_row.working_uri and Path(august_row.working_uri).is_file()
    ready_frame = pd.read_parquet(august_row.working_uri)
    assert ready_frame["支付金额"].tolist() == [28.0, 30.0]

    august_recipe = next(
        item
        for item in (await client.get(f"/api/v1/projects/{project_id}/recipes")).json()["data"]
        if item["data_source_id"] == august["id"]
    )
    assert august_recipe["status"] == "needs_attention"
    assert august_recipe["operations"][0]["operation"] == "replay_prior_recipe"
    first_output_fingerprint = august_recipe["output_fingerprint"]

    reapplied = await client.post(
        f"/api/v1/projects/{project_id}/recipes/{august_recipe['id']}/reapply"
    )
    assert reapplied.status_code == 200, reapplied.text
    assert reapplied.json()["data"]["status"] == "needs_confirmation"
    assert reapplied.json()["data"]["source_snapshot"]["replacement"] == {
        "status": "pending_confirmation",
        "replaces_source_id": july["id"],
        "active_source_id": july["id"],
    }
    assert (
        reapplied.json()["data"]["source_snapshot"]["schema_drift"]["matched_by"]
        == "pending_replacement"
    )
    refreshed_recipe = next(
        item
        for item in (await client.get(f"/api/v1/projects/{project_id}/recipes")).json()["data"]
        if item["id"] == august_recipe["id"]
    )
    assert refreshed_recipe["status"] == "needs_attention"
    assert refreshed_recipe["output_fingerprint"] == first_output_fingerprint
    await db_session.refresh(july_row)
    await db_session.refresh(august_row)
    assert july_row.status == "ready"
    assert august_row.status == "needs_confirmation"
    assert (july_row.profile_data or {})["is_current"] is True
    assert (august_row.profile_data or {})["is_current"] is False
    assert (august_row.profile_data or {})["replacement_of"] == july["id"]
    still_trusted_context = await load_project_context(db_session, UUID(project_id))
    assert [item["id"] for item in still_trusted_context.sources] == [july["id"]]
    assert [item["id"] for item in still_trusted_context.pending_sources] == [august["id"]]

    repeated = await client.post(
        f"/api/v1/projects/{project_id}/recipes/{august_recipe['id']}/reapply"
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["data"]["status"] == "needs_confirmation"
    await db_session.refresh(july_row)
    await db_session.refresh(august_row)
    assert july_row.status == "ready"
    assert (july_row.profile_data or {})["is_current"] is True
    assert (august_row.profile_data or {})["is_current"] is False

    accepted = await client.post(
        f"/api/v1/projects/{project_id}/sources/{august['id']}/accept-replacement"
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["data"]["status"] == "ready"
    assert accepted.json()["data"]["profile_data"]["is_current"] is True
    assert accepted.json()["data"]["profile_data"]["accepted_replacement"][
        "previous_source_id"
    ] == july["id"]
    await db_session.refresh(july_row)
    await db_session.refresh(august_row)
    assert july_row.status == "superseded"
    assert august_row.status == "ready"
    assert (august_row.profile_data or {})["is_current"] is True
    assert "replacement_of" not in (august_row.profile_data or {})
    activated_context = await load_project_context(db_session, UUID(project_id))
    assert [item["id"] for item in activated_context.sources] == [august["id"]]
    assert activated_context.pending_sources == []

    recipe_row = await db_session.get(
        SanitationRecipeRecord,
        UUID(august_recipe["id"]),
    )
    assert recipe_row is not None and recipe_row.active_revision_id is not None
    august_row.profile_data = {
        **dict(august_row.profile_data or {}),
        "visual_cleaning": {
            "active_revision_id": str(recipe_row.active_revision_id),
            "operations": [],
        },
    }
    await db_session.commit()

    undone = await client.post(
        f"/api/v1/projects/{project_id}/recipes/{august_recipe['id']}/undo"
    )
    assert undone.status_code == 200, undone.text
    assert undone.json()["data"]["status"] == "reverted"
    assert "恢复上一个成功版本" in undone.json()["message"]
    await db_session.refresh(july_row)
    await db_session.refresh(august_row)
    assert july_row.status == "ready"
    assert (july_row.profile_data or {})["is_current"] is True
    assert august_row.status == "attached"
    assert august_row.working_uri is None
    assert (august_row.profile_data or {})["is_current"] is False
    assert "visual_cleaning" not in (august_row.profile_data or {})
    restored_context = await load_project_context(db_session, UUID(project_id))
    assert [item["id"] for item in restored_context.sources] == [july["id"]]
    assert [item["id"] for item in restored_context.pending_sources] == [august["id"]]
    assert fingerprint_file(july_original) == july_fingerprint
    assert fingerprint_file(august_original) == august_fingerprint


@pytest.mark.asyncio
async def test_monthly_reuse_reports_column_type_drift_even_when_names_do_not_change(
    client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "WORKSPACE_ROOT", tmp_path / "projects")
    created = await client.post("/api/v1/projects", json={"name": "月度库存"})
    project_id = created.json()["data"]["id"]
    july = await _upload_csv(
        client,
        project_id,
        "inventory-july.csv",
        "sku,quantity\nA-1,12\nA-2,8\n",
    )
    first = await client.post(f"/api/v1/projects/{project_id}/sources/{july['id']}/preflight")
    assert first.status_code == 200, first.text

    august = await _upload_csv(
        client,
        project_id,
        "inventory-august.csv",
        "sku,quantity\nA-1,很多\nA-2,少量\n",
    )
    second = await client.post(f"/api/v1/projects/{project_id}/sources/{august['id']}/preflight")
    assert second.status_code == 200, second.text
    report = second.json()["data"]
    drift = report["source_snapshot"]["schema_drift"]
    assert drift["matched_by"] == "source_series"
    assert drift["added_columns"] == []
    assert drift["removed_columns"] == []
    assert drift["requires_confirmation"] is True
    assert drift["type_changes"] == [
        {
            "column": "quantity",
            "previous_type": "int64",
            "current_type": "str",
            "previous_category": "number",
            "current_category": "text",
        }
    ]
    assert report["status"] == "needs_confirmation"
    assert any(item["code"] == "schema_drift" for item in report["issues"])
