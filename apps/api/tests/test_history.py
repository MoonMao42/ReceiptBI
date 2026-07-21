"""Conversation history API tests"""

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.tables import AnalysisRun, ArtifactRecord, Conversation, Message, Project


async def seed_conversation(db_session, title: str = "Test Conversation") -> Conversation:
    conversation = Conversation(
        title=title,
        status="completed",
        extra_data={
            "model_name": "Test Model",
            "connection_name": "Demo DB",
            "provider_summary": "openai · openai_compatible",
            "context_rounds": 5,
        },
    )
    db_session.add(conversation)
    await db_session.flush()
    db_session.add_all(
        [
            Message(conversation_id=conversation.id, role="user", content="hello"),
            Message(conversation_id=conversation.id, role="assistant", content="world"),
        ]
    )
    await db_session.commit()
    await db_session.refresh(conversation)
    return conversation


@pytest.mark.asyncio
async def test_list_conversations_empty(client: AsyncClient):
    response = await client.get("/api/v1/conversations")
    assert response.status_code == 200
    assert response.json()["data"]["items"] == []


@pytest.mark.asyncio
async def test_list_conversations_with_pagination(client: AsyncClient, db_session):
    await seed_conversation(db_session, "Paged Conversation")
    response = await client.get("/api/v1/conversations", params={"limit": 10, "offset": 0})
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["items"]) == 1
    assert data["total"] == 1


@pytest.mark.asyncio
async def test_list_conversations_with_search(client: AsyncClient, db_session):
    await seed_conversation(db_session, "sales dashboard")
    response = await client.get("/api/v1/conversations", params={"q": "sales"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["items"]) == 1
    assert data["items"][0]["title"] == "sales dashboard"


@pytest.mark.asyncio
async def test_list_conversations_filters_by_project_without_duplicate_runs(
    client: AsyncClient,
    db_session,
):
    first_project = Project(name="First project")
    second_project = Project(name="Second project")
    db_session.add_all([first_project, second_project])
    await db_session.flush()

    first_conversation = await seed_conversation(db_session, "First investigation")
    second_conversation = await seed_conversation(db_session, "Second investigation")
    await seed_conversation(db_session, "Legacy conversation without a run")
    db_session.add_all(
        [
            AnalysisRun(
                project_id=first_project.id,
                conversation_id=first_conversation.id,
                query="first pass",
            ),
            AnalysisRun(
                project_id=first_project.id,
                conversation_id=first_conversation.id,
                query="follow-up pass",
            ),
            AnalysisRun(
                project_id=second_project.id,
                conversation_id=second_conversation.id,
                query="second pass",
            ),
        ]
    )
    await db_session.commit()

    response = await client.get(
        "/api/v1/conversations",
        params={"project_id": str(first_project.id)},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 1
    assert [item["id"] for item in data["items"]] == [str(first_conversation.id)]
    assert data["items"][0]["project_id"] == str(first_project.id)


@pytest.mark.asyncio
async def test_get_and_toggle_favorite_conversation(client: AsyncClient, db_session):
    conversation = await seed_conversation(db_session, "Favorite me")
    detail_response = await client.get(f"/api/v1/conversations/{conversation.id}")
    assert detail_response.status_code == 200
    assert len(detail_response.json()["data"]["messages"]) == 2

    favorite_response = await client.post(f"/api/v1/conversations/{conversation.id}/favorite")
    assert favorite_response.status_code == 200
    assert favorite_response.json()["data"]["is_favorite"] is True


@pytest.mark.asyncio
async def test_delete_conversation(client: AsyncClient, db_session):
    conversation = await seed_conversation(db_session, "Delete me")
    response = await client.delete(f"/api/v1/conversations/{conversation.id}")
    assert response.status_code == 200

    not_found = await client.get(f"/api/v1/conversations/{conversation.id}")
    assert not_found.status_code == 404


@pytest.mark.asyncio
async def test_delete_conversation_cleans_all_runs_and_artifacts(client: AsyncClient, db_session):
    project = Project(name="Cleanup project")
    db_session.add(project)
    await db_session.flush()
    conversation = await seed_conversation(db_session, "Delete complete investigation")
    conversation_id = conversation.id
    first_run = AnalysisRun(
        project_id=project.id,
        conversation_id=conversation_id,
        query="first pass",
    )
    second_run = AnalysisRun(
        project_id=project.id,
        conversation_id=conversation_id,
        query="second pass",
    )
    db_session.add_all([first_run, second_run])
    await db_session.flush()
    db_session.add_all(
        [
            ArtifactRecord(
                project_id=project.id,
                analysis_run_id=first_run.id,
                kind="report",
                title="First report",
            ),
            ArtifactRecord(
                project_id=project.id,
                analysis_run_id=second_run.id,
                kind="chart",
                title="Second chart",
            ),
        ]
    )
    await db_session.commit()

    response = await client.delete(f"/api/v1/conversations/{conversation_id}")

    assert response.status_code == 200
    run_count = await db_session.scalar(
        select(func.count(AnalysisRun.id)).where(AnalysisRun.conversation_id == conversation_id)
    )
    artifact_count = await db_session.scalar(
        select(func.count(ArtifactRecord.id)).where(
            ArtifactRecord.analysis_run_id.in_([first_run.id, second_run.id])
        )
    )
    assert run_count == 0
    assert artifact_count == 0


@pytest.mark.asyncio
async def test_delete_analysis_run_keeps_shared_conversation_and_sibling_run(
    client: AsyncClient,
    db_session,
):
    project = Project(name="Shared conversation project")
    db_session.add(project)
    await db_session.flush()
    conversation = await seed_conversation(db_session, "Continue this investigation")
    conversation_id = conversation.id
    deleted_run = AnalysisRun(
        project_id=project.id,
        conversation_id=conversation_id,
        query="discard this pass",
    )
    sibling_run = AnalysisRun(
        project_id=project.id,
        conversation_id=conversation_id,
        query="keep this pass",
    )
    db_session.add_all([deleted_run, sibling_run])
    await db_session.flush()
    deleted_artifact = ArtifactRecord(
        project_id=project.id,
        analysis_run_id=deleted_run.id,
        kind="report",
        title="Discarded report",
    )
    sibling_artifact = ArtifactRecord(
        project_id=project.id,
        analysis_run_id=sibling_run.id,
        kind="report",
        title="Kept report",
    )
    db_session.add_all([deleted_artifact, sibling_artifact])
    await db_session.commit()

    response = await client.delete(
        f"/api/v1/projects/{project.id}/analysis-runs/{deleted_run.id}"
    )

    assert response.status_code == 200
    assert await db_session.get(Conversation, conversation_id) is not None
    assert await db_session.get(AnalysisRun, deleted_run.id) is None
    assert await db_session.get(ArtifactRecord, deleted_artifact.id) is None
    assert await db_session.get(AnalysisRun, sibling_run.id) is not None
    assert await db_session.get(ArtifactRecord, sibling_artifact.id) is not None


@pytest.mark.asyncio
async def test_conversation_not_found(client: AsyncClient):
    fake_id = uuid4()
    response = await client.get(f"/api/v1/conversations/{fake_id}")
    assert response.status_code == 404
