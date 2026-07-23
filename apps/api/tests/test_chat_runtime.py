"""Tests for chat runtime helpers."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import chat as chat_api
from app.db.tables import AnalysisRun, Conversation, Message, Model, Project
from app.models import SSEEvent
from app.services.chat_runtime import (
    ActiveQueryRegistry,
    ChatEventAccumulator,
    ModelSelectionConflictError,
    apply_runtime_snapshot,
    mark_conversation_completed,
    mark_conversation_error,
    merge_metadata,
    resolve_chat_request,
)


def test_active_query_registry_lifecycle():
    registry = ActiveQueryRegistry()
    conversation_id = uuid4()

    query_key = registry.start(conversation_id)

    assert query_key.startswith(f"{conversation_id}:")
    assert registry.is_active(conversation_id) is True
    assert registry.stop(conversation_id) is True
    assert registry.is_active(conversation_id) is False
    assert registry.stop_checker(conversation_id)() is True

    registry.release(query_key)
    assert registry.is_active(conversation_id) is False
    assert registry.stop(conversation_id) is False


def test_active_query_registry_second_start_never_reactivates_old_query():
    registry = ActiveQueryRegistry()
    conversation_id = uuid4()

    first = registry.start(conversation_id)
    first_stop_checker = registry.stop_checker(first)
    second = registry.start(conversation_id)

    assert first != second
    assert first_stop_checker() is True
    assert registry.stop_checker(second)() is False

    registry.release(first)
    assert registry.stop_checker(second)() is False
    assert registry.stop(conversation_id) is True
    assert registry.stop_checker(second)() is True


def test_active_query_registry_late_stream_stop_does_not_stop_new_owner():
    registry = ActiveQueryRegistry()
    conversation_id = uuid4()

    first = registry.start(conversation_id, client_stream_id="stream-a")
    registry.release(first)
    second = registry.start(conversation_id, client_stream_id="stream-b")

    assert registry.stop(conversation_id, client_stream_id="stream-a") is False
    assert registry.stop_checker(second)() is False
    assert registry.stop(conversation_id, client_stream_id="stream-b") is True
    assert registry.stop_checker(second)() is True

    registry.release(second)


def test_active_query_registry_remembers_exact_stop_before_start():
    registry = ActiveQueryRegistry()
    conversation_id = uuid4()

    assert registry.stop(conversation_id, client_stream_id="stream-a") is True

    query_key = registry.start(conversation_id, client_stream_id="stream-a")

    assert registry.stop_checker(query_key)() is True
    registry.release(query_key)


def test_active_query_registry_finalization_and_stop_have_one_winner():
    registry = ActiveQueryRegistry()
    conversation_id = uuid4()
    query_key = registry.start(conversation_id, client_stream_id="stream-a")

    assert registry.begin_finalization(query_key) is True
    assert registry.stop(conversation_id, client_stream_id="stream-a") is False
    assert registry.stop_checker(query_key)() is False
    assert registry.begin_finalization(query_key) is True

    registry.release(query_key)


@pytest.mark.asyncio
async def test_stop_route_targets_the_requested_stream(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    conversation_id = uuid4()
    observed: dict[str, str] = {}

    def _stop(target_conversation_id, client_stream_id=None):
        observed["conversation_id"] = str(target_conversation_id)
        observed["client_stream_id"] = str(client_stream_id)
        return True

    monkeypatch.setattr(chat_api.active_query_registry, "stop", _stop)

    response = await client.post(
        "/api/v1/chat/stop",
        json={
            "conversation_id": str(conversation_id),
            "client_stream_id": "stream-exact",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["stopped"] is True
    assert observed == {
        "conversation_id": str(conversation_id),
        "client_stream_id": "stream-exact",
    }


@pytest.mark.asyncio
async def test_stop_route_requires_exact_stream_generation(client: AsyncClient):
    response = await client.post(
        "/api/v1/chat/stop",
        json={"conversation_id": str(uuid4())},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_duplicate_resume_route_does_not_stop_the_running_owner(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="并发恢复项目")
    conversation = Conversation(title="持续调查", status="active")
    db_session.add_all([project, conversation])
    await db_session.flush()
    run = AnalysisRun(
        project_id=project.id,
        conversation_id=conversation.id,
        query="持续观察收入",
        state="understanding",
        stage="understanding",
        checkpoint={"resumable": True},
    )
    db_session.add(run)
    await db_session.commit()
    owner_key = chat_api.active_query_registry.start(conversation.id)
    try:
        response = await client.get(
            "/api/v1/chat/stream",
            params={
                "resume_run_id": str(run.id),
                "conversation_id": str(conversation.id),
                "project_id": str(project.id),
            },
        )

        assert response.status_code == 200
        assert "ANALYSIS_ALREADY_RUNNING" in response.text
        assert chat_api.active_query_registry.stop_checker(owner_key)() is False
        await db_session.refresh(run)
        assert run.state == "understanding"
        assert run.stage == "understanding"
    finally:
        chat_api.active_query_registry.release(owner_key)


def test_merge_metadata_dedupes_diagnostics_and_merges_execution_context():
    base = {
        "execution_context": {"model_id": "model-a"},
        "diagnostics": [{"attempt": 1, "phase": "sql", "status": "error", "message": "broken"}],
    }
    updates = {
        "execution_context": {"connection_id": "conn-a"},
        "diagnostics": [
            {"attempt": 1, "phase": "sql", "status": "error", "message": "broken"},
            {"attempt": 2, "phase": "sql", "status": "repaired", "message": "fixed"},
        ],
    }

    merged = merge_metadata(base, updates)

    assert merged["execution_context"] == {
        "model_id": "model-a",
        "connection_id": "conn-a",
    }
    assert merged["diagnostics"] == [
        {"attempt": 1, "phase": "sql", "status": "error", "message": "broken"},
        {"attempt": 2, "phase": "sql", "status": "repaired", "message": "fixed"},
    ]


def test_chat_event_accumulator_collects_stream_output():
    snapshot = {"model_id": "model-a", "connection_id": "conn-a"}
    accumulator = ChatEventAccumulator(original_query="show sales", runtime_snapshot=snapshot)

    progress = SSEEvent.progress(
        "sql",
        "SQL ready",
        execution_context={"connection_name": "Analytics DB"},
        diagnostic_entry={"attempt": 1, "phase": "sql", "status": "success", "message": "ok"},
    )
    result = SSEEvent.result(
        content="分析完成",
        sql="SELECT 1",
        data=[{"value": 1}],
        rows_count=1,
        execution_time=0.25,
        diagnostics=[{"attempt": 1, "phase": "sql", "status": "success", "message": "ok"}],
    )
    python_output = SSEEvent.python_output("stdout")
    python_image = SSEEvent.python_image("image-data")

    accumulator.consume(progress)
    accumulator.consume(result)
    accumulator.consume(python_output)
    accumulator.consume(python_image)

    metadata = accumulator.build_metadata()

    assert accumulator.build_assistant_content() == "分析完成"
    assert metadata["execution_context"]["model_id"] == "model-a"
    assert metadata["execution_context"]["connection_name"] == "Analytics DB"
    assert metadata["sql"] == "SELECT 1"
    assert metadata["python_output"] == "stdout"
    assert metadata["python_images"] == ["image-data"]
    assert len(metadata["diagnostics"]) == 1


def test_chat_event_accumulator_prefers_error_message_when_no_summary():
    accumulator = ChatEventAccumulator(
        original_query="show sales",
        runtime_snapshot={"model_id": "model-a"},
    )

    accumulator.consume(
        SSEEvent.error(
            "SQL_EXECUTION_FAILED",
            "syntax error",
            error_category="sql",
            failed_stage="execution",
            diagnostics=[
                {
                    "attempt": 1,
                    "phase": "execution",
                    "status": "error",
                    "message": "OperationalError: syntax error",
                }
            ],
        )
    )

    metadata = accumulator.build_metadata()

    assert accumulator.has_error is True
    assert accumulator.build_assistant_content() == "syntax error"
    assert metadata["error"] == "syntax error"
    assert metadata["error_code"] == "SQL_EXECUTION_FAILED"
    assert metadata["error_category"] == "sql"
    assert metadata["failed_stage"] == "execution"
    assert metadata["diagnostics"][0]["message"] == "OperationalError: syntax error"


def test_chat_event_accumulator_never_invents_completion_without_result():
    accumulator = ChatEventAccumulator(
        original_query="show sales",
        runtime_snapshot={"model_id": "model-a"},
    )

    accumulator.consume(SSEEvent.progress("analyzing", "still working"))

    assert accumulator.has_result is False
    assert accumulator.has_error is False
    assert accumulator.build_assistant_content() == "这次调查没有形成可用结论，请继续或重新调查。"


def test_resolve_chat_request_prefers_explicit_values():
    conversation = SimpleNamespace(
        model_id=None,
        connection_id=uuid4(),
        extra_data={"project_id": str(uuid4())},
    )
    requested_project_id = uuid4()

    resolved = resolve_chat_request(
        requested_model="custom-model",
        requested_connection_id=uuid4(),
        requested_project_id=requested_project_id,
        requested_context_rounds=7,
        conversation=conversation,
        settings_data={"context_rounds": 3},
    )

    assert resolved.model_name == "custom-model"
    assert resolved.connection_id != conversation.connection_id
    assert resolved.project_id == requested_project_id
    assert resolved.context_rounds == 7


def test_resolve_chat_request_locks_started_conversation_model():
    model_id = uuid4()
    conversation = SimpleNamespace(
        model_id=model_id,
        connection_id=None,
        extra_data={"model_identifier": "gpt-4.1"},
    )

    resolved = resolve_chat_request(
        requested_model="gpt-4.1",
        requested_connection_id=None,
        requested_project_id=None,
        requested_context_rounds=None,
        conversation=conversation,
        settings_data={"context_rounds": 5},
    )

    assert resolved.model_name == str(model_id)

    with pytest.raises(ModelSelectionConflictError, match="开始新调查"):
        resolve_chat_request(
            requested_model=str(uuid4()),
            requested_connection_id=None,
            requested_project_id=None,
            requested_context_rounds=None,
            conversation=conversation,
            settings_data={"context_rounds": 5},
        )


def test_resolve_chat_request_resumes_existing_project():
    project_id = uuid4()
    conversation = SimpleNamespace(
        model_id=None,
        connection_id=None,
        extra_data={"project_id": str(project_id)},
    )

    resolved = resolve_chat_request(
        requested_model=None,
        requested_connection_id=None,
        requested_project_id=None,
        requested_context_rounds=None,
        conversation=conversation,
        settings_data={"context_rounds": 5},
    )

    assert resolved.project_id == project_id


def test_resolve_chat_request_does_not_inherit_connection_for_project():
    old_connection_id = uuid4()
    project_id = uuid4()
    conversation = SimpleNamespace(
        model_id=None,
        connection_id=old_connection_id,
        extra_data={},
    )

    resolved = resolve_chat_request(
        requested_model=None,
        requested_connection_id=None,
        requested_project_id=project_id,
        requested_context_rounds=None,
        conversation=conversation,
        settings_data={"context_rounds": 5},
    )

    assert resolved.project_id == project_id
    assert resolved.connection_id is None


def test_apply_runtime_snapshot_and_terminal_markers():
    model_id = uuid4()
    connection_id = uuid4()
    conversation = SimpleNamespace(
        status="new",
        extra_data={"existing": True},
        model_id=None,
        connection_id=None,
    )

    apply_runtime_snapshot(
        conversation,
        {
            "model_id": str(model_id),
            "connection_id": str(connection_id),
            "provider_summary": "deepseek -> openai",
        },
    )
    assert conversation.status == "active"

    mark_conversation_error(
        conversation,
        runtime_snapshot={"api_format": "openai_compatible"},
        query="show sales",
        error_payload={"message": "boom", "error_category": "sql"},
    )
    assert conversation.status == "error"
    assert conversation.extra_data["last_error"] == "boom"
    assert conversation.extra_data["error_category"] == "sql"
    assert conversation.model_id == model_id
    assert conversation.connection_id == connection_id
    assert conversation.extra_data["provider_summary"] == "deepseek -> openai"

    mark_conversation_completed(
        conversation,
        runtime_snapshot={"api_format": "openai_compatible"},
        query="show sales",
        metadata={"execution_time": 0.5, "rows_count": 12},
    )
    assert conversation.status == "completed"
    assert conversation.extra_data["last_query"] == "show sales"
    assert conversation.extra_data["rows_count"] == 12

    mark_conversation_completed(
        conversation,
        runtime_snapshot={"api_format": "openai_compatible"},
        query="show sales",
        metadata={"analysis_state": "needs_attention"},
    )
    assert conversation.status == "active"


def test_apply_project_runtime_snapshot_clears_stale_conversation_connection():
    old_connection_id = uuid4()
    project_id = uuid4()
    conversation = SimpleNamespace(
        status="active",
        extra_data={"connection_id": str(old_connection_id)},
        model_id=None,
        connection_id=old_connection_id,
    )

    apply_runtime_snapshot(
        conversation,
        {
            "project_id": str(project_id),
            "connection_id": None,
            "connection_name": None,
        },
    )

    assert conversation.connection_id is None
    assert conversation.extra_data["project_id"] == str(project_id)
    assert conversation.extra_data["connection_id"] is None


@pytest.mark.asyncio
async def test_streaming_chat_accepts_json_body_without_url_query(client: AsyncClient):
    response = await client.post("/api/v1/chat/stream", json={})

    assert response.status_code == 200
    assert response.request.url.query == b""
    assert "INVALID_QUERY" in response.text


@pytest.mark.asyncio
async def test_streaming_chat_rejects_model_switch_and_preserves_question(
    client: AsyncClient,
    db_session: AsyncSession,
):
    first = Model(name="First", provider="openai", model_id="gpt-4.1")
    second = Model(name="Second", provider="openai", model_id="gpt-4o-mini")
    db_session.add_all([first, second])
    await db_session.flush()
    conversation = Conversation(
        title="Locked investigation",
        status="active",
        model_id=first.id,
        extra_data={"model_identifier": first.model_id},
    )
    db_session.add(conversation)
    await db_session.commit()

    response = await client.get(
        "/api/v1/chat/stream",
        params={
            "query": "继续分析收入",
            "conversation_id": str(conversation.id),
            "model": str(second.id),
        },
    )

    assert response.status_code == 200
    assert "MODEL_SELECTION_CONFLICT" in response.text
    assert "model_selection_conflict" in response.text
    await db_session.refresh(conversation)
    assert conversation.model_id == first.id
    messages = list(
        (
            await db_session.scalars(
                select(Message)
                .where(Message.conversation_id == conversation.id)
                .order_by(Message.created_at)
            )
        ).all()
    )
    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[0].content == "继续分析收入"
    assert messages[1].extra_data["error_category"] == "model_selection_conflict"


@pytest.mark.asyncio
async def test_streaming_chat_persists_visible_failure_when_engine_ends_without_result(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    class SilentExecutionService:
        def __init__(self, **_kwargs):
            pass

        async def get_runtime_snapshot(self):
            return {"provider_summary": "test"}

        async def execute_stream(self, **_kwargs):
            yield SSEEvent.progress("analyzing", "working")

    monkeypatch.setattr(chat_api, "ExecutionService", SilentExecutionService)

    response = await client.get("/api/v1/chat/stream", params={"query": "检查收入"})

    assert response.status_code == 200
    assert response.text.count("ANALYSIS_INCOMPLETE") == 1
    assert '"type": "done"' not in response.text
    messages = list((await db_session.execute(select(Message))).scalars())
    assistant_messages = [message for message in messages if message.role == "assistant"]
    assert len(assistant_messages) == 1
    assert assistant_messages[0].content == "这次调查没有形成可用结论，可以继续或重新调查。"
    assert assistant_messages[0].extra_data["error_code"] == "ANALYSIS_INCOMPLETE"
    conversation = await db_session.get(Conversation, assistant_messages[0].conversation_id)
    assert conversation is not None
    assert conversation.status == "error"


@pytest.mark.asyncio
async def test_streaming_chat_persists_one_failure_message_for_outer_exception(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    class BrokenExecutionService:
        def __init__(self, **_kwargs):
            pass

        async def get_runtime_snapshot(self):
            return {"provider_summary": "test"}

        async def execute_stream(self, **_kwargs):
            raise RuntimeError("internal token must stay hidden")
            yield  # pragma: no cover

    monkeypatch.setattr(chat_api, "ExecutionService", BrokenExecutionService)

    response = await client.get("/api/v1/chat/stream", params={"query": "检查收入"})

    assert response.status_code == 200
    assert response.text.count("EXECUTION_ERROR") == 1
    assert "internal token must stay hidden" not in response.text
    messages = list((await db_session.execute(select(Message))).scalars())
    assistant_messages = [message for message in messages if message.role == "assistant"]
    assert len(assistant_messages) == 1
    assert assistant_messages[0].content == "调查遇到意外问题，这次没有完成。请继续或重新调查。"
    assert assistant_messages[0].extra_data["error_code"] == "EXECUTION_ERROR"


@pytest.mark.asyncio
async def test_streaming_chat_does_not_duplicate_an_error_emitted_before_outer_exception(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    class ErrorThenBreakExecutionService:
        def __init__(self, **_kwargs):
            pass

        async def get_runtime_snapshot(self):
            return {"provider_summary": "test"}

        async def execute_stream(self, **_kwargs):
            yield SSEEvent.error(
                "MODEL_FAILED",
                "模型暂时不可用",
                error_category="model_provider",
            )
            raise RuntimeError("stream cleanup failed")

    monkeypatch.setattr(chat_api, "ExecutionService", ErrorThenBreakExecutionService)

    response = await client.get("/api/v1/chat/stream", params={"query": "检查收入"})

    assert response.status_code == 200
    assert response.text.count("MODEL_FAILED") == 1
    assert "EXECUTION_ERROR" not in response.text
    messages = list((await db_session.execute(select(Message))).scalars())
    assistant_messages = [message for message in messages if message.role == "assistant"]
    assert len(assistant_messages) == 1
    assert assistant_messages[0].content == "模型暂时不可用"
    assert assistant_messages[0].extra_data["error_code"] == "MODEL_FAILED"
