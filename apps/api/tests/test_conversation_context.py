"""Conversation continuity keeps useful report state without technical payloads."""

from __future__ import annotations

import json

import pytest

from app.db.tables import AnalysisRun, Conversation, Message, Project
from app.services.conversation_context import build_conversation_context, compact_report_context
from app.services.execution_context import ExecutionContextResolver
from app.services.project_context import load_project_context


@pytest.mark.asyncio
async def test_follow_up_receives_previous_request_and_actual_report_delivery(
    db_session,
) -> None:
    conversation = Conversation(title="企业销售复核")
    db_session.add(conversation)
    await db_session.flush()
    db_session.add_all(
        [
            Message(
                conversation_id=conversation.id,
                role="user",
                content="先复核企业销售额，然后再出饼图",
            ),
            Message(
                conversation_id=conversation.id,
                role="assistant",
                content="已经完成销售额复核。",
                extra_data={
                    "analysis_run_id": "run-previous",
                    "original_query": "先复核企业销售额，然后再出饼图",
                    "report": {
                        "status": "completed",
                        "title": "企业销售额复核",
                        "summary": "头部企业占比较高。",
                        "findings": ["第一名与其余企业差距明显。"],
                        "metrics": [{"label": "头部销售额", "value": "140,616 元"}],
                        "visualization": {
                            "type": "bar",
                            "title": "企业销售额对比",
                            "result_name": "company_sales",
                        },
                        "data": [{"raw_secret": "must-not-leak"}],
                    },
                    "sql": "SELECT secret FROM private_table",
                    "tool_history": [{"password": "must-not-leak"}],
                    "python_images": ["base64-must-not-leak"],
                },
            ),
        ]
    )
    await db_session.commit()

    history = await ExecutionContextResolver(db_session).get_conversation_history(
        conversation.id,
        limit=10,
    )
    assistant = history[-1]

    assert assistant["analysis_run_id"] == "run-previous"
    assert assistant["original_query"] == "先复核企业销售额，然后再出饼图"
    assert assistant["report_context"]["metrics"] == [
        {"label": "头部销售额", "value": "140,616 元"}
    ]
    assert assistant["report_context"]["visualization"]["type"] == "bar"

    context = build_conversation_context(history, current_query="懂什么叫饼图吗")

    assert context["continuation_likely"] is True
    assert context["unmet_requests"] == [
        {
            "kind": "presentation_request",
            "status": "unmet",
            "requested_output": "pie",
            "actual_output": "bar",
            "request": "先复核企业销售额，然后再出饼图",
            "source_analysis_run_id": "run-previous",
        }
    ]
    assert context["current_turn_contract"]["mode"] == "complete_unmet_request"
    assert context["current_turn_contract"]["request"]["requested_output"] == "pie"
    serialized = json.dumps(context, ensure_ascii=False)
    assert "must-not-leak" not in serialized
    assert "private_table" not in serialized
    assert "base64" not in serialized


def test_conversation_context_respects_loaded_rounds_beyond_four() -> None:
    history: list[dict[str, object]] = []
    for index in range(1, 7):
        history.extend(
            [
                {"role": "user", "content": f"第 {index} 轮问题"},
                {
                    "role": "assistant",
                    "content": f"第 {index} 轮回答",
                    "analysis_run_id": f"run-{index}",
                    "report_context": {
                        "status": "completed",
                        "title": f"第 {index} 轮报告",
                        "summary": "已完成。",
                    },
                },
            ]
        )

    context = build_conversation_context(
        history,
        current_query="继续第一轮",
        char_budget=100_000,
    )

    assert context["budget"] == {
        "available_messages": 12,
        "included_messages": 12,
        "truncated": False,
        "char_budget": 100_000,
    }
    assert context["messages"][0]["content"] == "第 1 轮问题"
    assert context["messages"][-1]["content"] == "第 6 轮回答"


def test_chart_spec_v1_context_keeps_only_bounded_business_fields() -> None:
    visualization = {
        "version": 1,
        "type": "bar",
        "title": "月度销售趋势",
        "data_ref": {
            "result_name": "monthly_sales",
            "result_hash": "must-not-leak",
        },
        "encoding": {
            "x": {"field": "月份", "kind": "temporal", "private": "must-not-leak"},
            "y": [
                {
                    "field": "销售额",
                    "label": "销售收入",
                    "format": "currency",
                    "aggregate": "sum",
                },
                {
                    "field": "订单数",
                    "format": "arbitrary-model-format",
                },
                *({"field": f"额外指标 {index}"} for index in range(20)),
            ],
        },
        "presentation": {"palette": "receiptbi"},
        "data": [{"raw_secret": "must-not-leak"}],
        "rows": [{"raw_secret": "must-not-leak"}],
        "javascript": "must-not-leak",
    }

    compact = compact_report_context({"visualization": visualization})

    assert compact is not None
    chart = compact["visualization"]
    assert chart == {
        "version": 1,
        "type": "bar",
        "title": "月度销售趋势",
        "encoding": {
            "x": {"field": "月份"},
            "y": [
                {"field": "销售额", "label": "销售收入", "format": "currency"},
                {"field": "订单数"},
                *({"field": f"额外指标 {index}"} for index in range(10)),
            ],
        },
        "data_ref": {"result_name": "monthly_sales"},
    }
    serialized = json.dumps(chart, ensure_ascii=False)
    assert "must-not-leak" not in serialized
    assert "result_hash" not in serialized
    assert "rows" not in serialized


@pytest.mark.asyncio
async def test_project_context_retrieves_bounded_recent_reports_across_conversations(
    db_session,
) -> None:
    project = Project(name="长期经营分析")
    current_conversation = Conversation(title="当前调查")
    older_conversation = Conversation(title="上一份调查")
    db_session.add_all([project, current_conversation, older_conversation])
    await db_session.flush()
    db_session.add_all(
        [
            AnalysisRun(
                project_id=project.id,
                conversation_id=current_conversation.id,
                query="继续核对企业销售",
                state="completed",
                stage="completed",
                report={
                    "status": "completed",
                    "title": "当前会话上一份报告",
                    "summary": "企业销售已核对。",
                },
            ),
            AnalysisRun(
                project_id=project.id,
                conversation_id=older_conversation.id,
                query="把企业销售结构做成饼图",
                state="completed",
                stage="completed",
                report={
                    "status": "completed",
                    "title": "企业销售结构",
                    "summary": "此前交付的是柱状图。",
                    "visualization": {"type": "bar", "title": "企业销售对比"},
                    "data": [{"raw_secret": "must-not-leak"}],
                    "tool_history": [{"sql": "must-not-leak"}],
                },
            ),
        ]
    )
    await db_session.commit()

    runtime_context = await load_project_context(
        db_session,
        project.id,
        conversation_id=current_conversation.id,
    )
    summary = runtime_context.public_summary(query="刚才的饼图呢")

    assert len(summary["recent_analyses"]) == 2
    assert any(item["same_conversation"] for item in summary["recent_analyses"])
    pie_history = next(item for item in summary["recent_analyses"] if "饼图" in item["query"])
    assert pie_history["report"]["visualization"]["type"] == "bar"
    assert pie_history["requires_current_revalidation"] is True
    assert summary["recent_analysis_context"]["policy"] == (
        "historical_context_only_revalidate_current_data"
    )
    assert "must-not-leak" not in json.dumps(summary["recent_analyses"], ensure_ascii=False)
