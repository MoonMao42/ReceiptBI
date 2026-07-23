"""API coverage for governed recommendation persistence and validation closure."""

from __future__ import annotations

from uuid import UUID

import pandas as pd
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import projects as projects_api
from app.db.tables import (
    AnalysisRun,
    Project,
    ProjectDataSource,
    SemanticEntry,
    SemanticEntryRevision,
)
from app.services.semantic_revisions import append_semantic_revision


def _profile() -> dict:
    return {
        "logical_name": "orders",
        "is_current": True,
        "schema": {
            "columns": [
                {"name": "amount", "dtype": "float64"},
                {"name": "region", "dtype": "object"},
            ]
        },
        "preanalysis": {
            "generated_by": "deterministic_preflight",
            "candidate_roles": [
                {
                    "column": "amount",
                    "role": "measure",
                    "status": "candidate",
                    "non_null": 3,
                    "unique": 3,
                },
                {
                    "column": "region",
                    "role": "dimension",
                    "status": "candidate",
                    "non_null": 3,
                    "unique": 2,
                    "uniqueness": 2 / 3,
                },
            ],
        },
    }


async def _project_with_orders(db: AsyncSession, tmp_path) -> tuple[Project, ProjectDataSource]:
    working = tmp_path / "orders.parquet"
    pd.DataFrame(
        {
            "amount": [10.0, 20.0, 30.0],
            "region": ["east", "west", "east"],
        }
    ).to_parquet(working, index=False)
    project = Project(name="语义推荐 API")
    db.add(project)
    await db.flush()
    source = ProjectDataSource(
        project_id=project.id,
        kind="file",
        name="orders.parquet",
        format="parquet",
        working_uri=str(working),
        status="ready",
        profile_data=_profile(),
    )
    db.add(source)
    await db.commit()
    return project, source


async def _disable_model_enhancement(monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_enhancer(*_args, **_kwargs):
        return None

    monkeypatch.setattr(projects_api, "_semantic_recommendation_enhancer", no_enhancer)


async def _recommend(client, project_id: UUID, source_id: UUID, *, limit: int = 20):
    return await client.post(
        f"/api/v1/projects/{project_id}/knowledge/recommendations",
        json={
            "locale": "zh",
            "scopes": [{"source_id": str(source_id), "tables": []}],
            "limit": limit,
        },
    )


@pytest.mark.asyncio
async def test_recommendation_api_persists_batch_provenance_and_page_order(
    client,
    db_session: AsyncSession,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    project, source = await _project_with_orders(db_session, tmp_path)
    await _disable_model_enhancement(monkeypatch)

    def reject_live_database(*_args, **_kwargs):
        raise AssertionError("recommendation generation must use profiles, not live data")

    monkeypatch.setattr(projects_api, "create_database_manager", reject_live_database)

    response = await _recommend(client, project.id, source.id)

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["generated_by"] == "preflight"
    assert data["items"]
    assert all(item["state"] == "candidate" for item in data["items"])
    assert all(item["validity"] == "unverified" for item in data["items"])
    presentations = [
        item for item in data["items"] if item["entry_type"] == "scope_presentation"
    ]
    executable = [
        item for item in data["items"] if item["entry_type"] != "scope_presentation"
    ]
    assert presentations
    assert all(item["execution_state"] == "definition_only" for item in presentations)
    assert all("remember" in item["allowed_actions"] for item in presentations)
    assert all("queue_validation" not in item["allowed_actions"] for item in presentations)
    assert all(item["execution_state"] == "needs_validation" for item in executable)
    assert all(item["recommendation_batch_id"] == data["batch_id"] for item in data["items"])
    assert all("queue_validation" in item["allowed_actions"] for item in executable)
    assert (
        int(await db_session.scalar(select(func.count()).select_from(AnalysisRun)) or 0)
        == 0
    )

    page = await client.get(
        f"/api/v1/projects/{project.id}/knowledge/page",
        params={"recommendation_batch_id": data["batch_id"], "limit": 100},
    )
    assert page.status_code == 200, page.text
    page_items = page.json()["data"]["items"]
    assert {item["id"] for item in page_items} == {item["id"] for item in data["items"]}
    assert [item["entry_type"] for item in page_items] == [
        "scope_presentation",
        "scope_presentation",
        "metric",
        "dimension",
    ]

    revision = await db_session.scalar(
        select(SemanticEntryRevision).where(
            SemanticEntryRevision.id == UUID(data["items"][0]["active_revision_id"])
        )
    )
    assert revision is not None
    assert any(
        item.get("kind") == "semantic_recommendation_batch"
        and item.get("batch_id") == data["batch_id"]
        for item in revision.snapshot["evidence"]
    )


@pytest.mark.asyncio
async def test_model_unavailable_falls_back_and_invalid_scope_is_explicit(
    client,
    db_session: AsyncSession,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    project, source = await _project_with_orders(db_session, tmp_path)

    async def unavailable_enhancer(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        projects_api,
        "_semantic_recommendation_enhancer",
        unavailable_enhancer,
    )
    fallback = await _recommend(client, project.id, source.id)
    assert fallback.status_code == 200, fallback.text
    assert fallback.json()["data"]["generated_by"] == "preflight"

    invalid = await _recommend(client, project.id, UUID(int=0))
    assert invalid.status_code == 422, invalid.text
    assert invalid.json()["detail"]["code"] == "semantic_recommendation_scope_invalid"


@pytest.mark.asyncio
async def test_duplicate_recommendations_refresh_only_untouched_candidates(
    client,
    db_session: AsyncSession,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    project, source = await _project_with_orders(db_session, tmp_path)
    await _disable_model_enhancement(monkeypatch)
    first_response = await _recommend(client, project.id, source.id)
    first = first_response.json()["data"]
    first_by_key = {item["key"]: item for item in first["items"]}

    second_response = await _recommend(client, project.id, source.id)
    assert second_response.status_code == 200, second_response.text
    second = second_response.json()["data"]
    second_by_key = {item["key"]: item for item in second["items"]}
    assert second["batch_id"] != first["batch_id"]
    assert set(second_by_key) == set(first_by_key)
    assert all(
        second_by_key[key]["id"] == first_by_key[key]["id"] for key in first_by_key
    )
    assert all(
        second_by_key[key]["revision_number"] == first_by_key[key]["revision_number"] + 1
        for key in first_by_key
    )
    assert int(
        await db_session.scalar(
            select(func.count()).select_from(SemanticEntry).where(
                SemanticEntry.project_id == project.id
            )
        )
        or 0
    ) == len(first_by_key)

    metric = next(item for item in second["items"] if item["entry_type"] == "metric")
    dimension = next(item for item in second["items"] if item["entry_type"] == "dimension")
    metric_entry = await db_session.get(SemanticEntry, UUID(metric["id"]))
    assert metric_entry is not None
    metric_batch_id = metric_entry.recommendation_batch_id
    metric_entry.state = "confirmed"
    metric_entry.source = "user"
    metric_entry.validity = "active"
    await append_semantic_revision(
        db_session,
        metric_entry,
        mutation_kind="user_confirmed",
        actor_source="user",
        expected_active_revision_id=metric_entry.active_revision_id,
    )
    await db_session.commit()
    confirmed_revision_id = metric_entry.active_revision_id

    ignored = await client.post(
        f"/api/v1/projects/{project.id}/knowledge/batch",
        json={
            "action": "ignore",
            "items": [
                {
                    "entry_id": dimension["id"],
                    "expected_active_revision_id": dimension["active_revision_id"],
                }
            ],
        },
    )
    assert ignored.status_code == 200, ignored.text
    ignored_revision_id = ignored.json()["data"]["items"][0]["active_revision_id"]

    third_response = await _recommend(client, project.id, source.id)
    assert third_response.status_code == 200, third_response.text
    third = third_response.json()["data"]
    assert metric["id"] not in {item["id"] for item in third["items"]}
    assert dimension["id"] not in {item["id"] for item in third["items"]}

    db_session.expire_all()
    stored_metric = await db_session.get(SemanticEntry, UUID(metric["id"]))
    stored_dimension = await db_session.get(SemanticEntry, UUID(dimension["id"]))
    assert stored_metric is not None and stored_metric.state == "confirmed"
    assert stored_metric.active_revision_id == confirmed_revision_id
    assert stored_metric.recommendation_batch_id == metric_batch_id
    assert stored_dimension is not None and stored_dimension.is_active is False
    assert str(stored_dimension.active_revision_id) == ignored_revision_id
    assert stored_dimension.recommendation_batch_id == UUID(second["batch_id"])


@pytest.mark.asyncio
async def test_role_change_retires_only_the_untouched_previous_field_suggestion(
    client,
    db_session: AsyncSession,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    project, source = await _project_with_orders(db_session, tmp_path)
    await _disable_model_enhancement(monkeypatch)
    first_response = await _recommend(client, project.id, source.id)
    assert first_response.status_code == 200, first_response.text
    first_metric = next(
        item
        for item in first_response.json()["data"]["items"]
        if item["entry_type"] == "metric"
        and item["definition"]["source"]["action_column"] == "amount"
    )

    updated_profile = _profile()
    updated_profile["schema"]["columns"][0]["dtype"] = "object"
    source.profile_data = updated_profile
    await db_session.commit()

    second_response = await _recommend(client, project.id, source.id)
    assert second_response.status_code == 200, second_response.text
    replacement = next(
        item
        for item in second_response.json()["data"]["items"]
        if item["entry_type"] == "dimension"
        and item["definition"]["source"]["action_column"] == "amount"
    )
    assert replacement["id"] != first_metric["id"]

    db_session.expire_all()
    retired = await db_session.get(SemanticEntry, UUID(first_metric["id"]))
    assert retired is not None
    assert retired.is_active is False
    assert retired.validity == "stale"
    assert retired.execution_state == "blocked"
    assert retired.evidence[-1]["kind"] == "semantic_recommendation_superseded"
    assert retired.evidence[-1]["replacement_entry_id"] == replacement["id"]
    revision = await db_session.get(SemanticEntryRevision, retired.active_revision_id)
    assert revision is not None
    assert revision.mutation_kind == "recommendation_superseded"


@pytest.mark.asyncio
async def test_model_enhancement_is_reported_only_after_valid_complete_output(
    client,
    db_session: AsyncSession,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    project, source = await _project_with_orders(db_session, tmp_path)

    async def enhancer_factory(*_args, **_kwargs):
        async def enhance(items):
            return [
                {
                    "candidate_id": item["candidate_id"],
                    "business_name": f"AI {item['business_name']}",
                    "description": item["description"],
                    "example_questions": item["example_questions"],
                }
                for item in reversed(items)
            ]

        return enhance

    monkeypatch.setattr(
        projects_api,
        "_semantic_recommendation_enhancer",
        enhancer_factory,
    )

    response = await _recommend(client, project.id, source.id)

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["generated_by"] == "ai"
    assert all(item["definition"]["business_name"].startswith("AI ") for item in data["items"])
    assert all(
        any(evidence.get("kind") == "model_presentation_enhancement" for evidence in item["evidence"])
        for item in data["items"]
    )


@pytest.mark.asyncio
async def test_recommendation_can_close_through_independent_validation_job(
    client,
    db_session: AsyncSession,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    project, source = await _project_with_orders(db_session, tmp_path)
    await _disable_model_enhancement(monkeypatch)
    recommendation = await _recommend(client, project.id, source.id)
    metric = next(
        item
        for item in recommendation.json()["data"]["items"]
        if item["entry_type"] == "metric"
        and item["definition"]["kind"] == "aggregate_metric"
    )

    queued = await client.post(
        f"/api/v1/projects/{project.id}/knowledge/batch",
        json={
            "action": "queue_validation",
            "items": [
                {
                    "entry_id": metric["id"],
                    "expected_active_revision_id": metric["active_revision_id"],
                }
            ],
        },
    )

    assert queued.status_code == 200, queued.text
    job_id = queued.json()["data"]["validation_job_id"]
    job = await client.get(
        f"/api/v1/projects/{project.id}/knowledge/validation-jobs/{job_id}"
    )
    assert job.status_code == 200, job.text
    job_data = job.json()["data"]
    assert job_data["status"] == "completed"
    assert job_data["progress"]["verified"] == 1
    assert job_data["items"][0]["code"] == "semantic_validation_verified"

    stored = await client.get(
        f"/api/v1/projects/{project.id}/knowledge/{metric['id']}"
    )
    assert stored.status_code == 200, stored.text
    stored_data = stored.json()["data"]
    assert stored_data["execution_state"] == "verified"
    assert "remember" in stored_data["allowed_actions"]
    assert (
        int(await db_session.scalar(select(func.count()).select_from(AnalysisRun)) or 0)
        == 0
    )
