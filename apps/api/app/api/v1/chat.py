"""聊天 API."""

import asyncio
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.db import get_db
from app.db.tables import Conversation, Message
from app.i18n import get_progress_message, t
from app.models import APIResponse, ChatStopRequest, MessagePaginatedResponse, MessageResponse, SSEEvent
from app.services.app_settings import get_or_create_app_settings, settings_to_dict
from app.services.chat_runtime import (
    ActiveQueryRegistry,
    ChatEventAccumulator,
    apply_runtime_snapshot,
    create_user_message,
    get_or_create_conversation,
    mark_conversation_completed,
    mark_conversation_error,
    mark_conversation_exception,
    resolve_chat_request,
)
from app.services.execution import ExecutionService

router = APIRouter()
active_query_registry = ActiveQueryRegistry()


@router.get("/stream")
async def chat_stream(
    query: str = Query(..., min_length=1, max_length=10000, description="查询内容"),
    model: str | None = Query(default=None, description="模型 ID"),
    conversation_id: UUID | None = Query(default=None, description="对话 ID"),
    connection_id: UUID | None = Query(default=None, description="数据库连接 ID"),
    language: str = Query(default="zh", description="语言"),
    context_rounds: int | None = Query(default=None, ge=1, le=20, description="上下文轮数"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """SSE 流式聊天 - 单工作区模式."""
    current_conversation_id: UUID | None = conversation_id

    async def event_generator() -> AsyncGenerator[dict[str, str], None]:
        nonlocal current_conversation_id

        settings_record = await get_or_create_app_settings(db)
        settings_data = settings_to_dict(settings_record)

        conversation = await get_or_create_conversation(
            db,
            conversation_id=current_conversation_id,
            query=query,
            connection_id=connection_id,
        )
        if not conversation:
            yield SSEEvent.error("NOT_FOUND", t("error.not_found", language)).to_sse()
            return

        current_conversation_id = UUID(str(conversation.id))
        user_message = await create_user_message(
            db,
            conversation_id=current_conversation_id,
            query=query,
        )
        query_key = active_query_registry.start(current_conversation_id)

        try:
            yield SSEEvent.progress(
                "start",
                get_progress_message("start", language),
                conversation_id=str(current_conversation_id),
            ).to_sse()

            request_config = resolve_chat_request(
                requested_model=model,
                requested_connection_id=connection_id,
                requested_context_rounds=context_rounds,
                conversation=conversation,
                settings_data=settings_data,
            )
            execution_service = ExecutionService(
                db=db,
                model_name=request_config.model_name,
                connection_id=request_config.connection_id,
                language=language,
                context_rounds=request_config.context_rounds,
                settings_data=settings_data,
            )

            runtime_snapshot = await execution_service.get_runtime_snapshot()
            yield SSEEvent.progress(
                "context_ready",
                get_progress_message("context_ready", language),
                conversation_id=str(current_conversation_id),
                execution_context=runtime_snapshot,
            ).to_sse()

            apply_runtime_snapshot(conversation, runtime_snapshot)
            await db.commit()

            accumulator = ChatEventAccumulator(
                original_query=query,
                runtime_snapshot=runtime_snapshot,
            )
            async for event in execution_service.execute_stream(
                query=query,
                conversation_id=current_conversation_id,
                exclude_message_id=UUID(str(user_message.id)),
                stop_checker=active_query_registry.stop_checker(query_key),
            ):
                yield event.to_sse()
                accumulator.consume(event)

            metadata = accumulator.build_metadata()
            assistant_message = Message(
                conversation_id=current_conversation_id,
                role="assistant",
                content=accumulator.build_assistant_content(),
                extra_data=metadata,
            )
            db.add(assistant_message)

            if accumulator.has_error:
                mark_conversation_error(
                    conversation,
                    runtime_snapshot=runtime_snapshot,
                    query=query,
                    error_payload=accumulator.error_payload,
                )
                await db.commit()
                await db.refresh(assistant_message)
                return

            mark_conversation_completed(
                conversation,
                runtime_snapshot=runtime_snapshot,
                query=query,
                metadata=metadata,
            )
            await db.commit()
            await db.refresh(assistant_message)

            yield SSEEvent.done(str(current_conversation_id), str(assistant_message.id)).to_sse()
        except asyncio.CancelledError:
            mark_conversation_exception(conversation, t("error.cancelled", language))
            await db.commit()
            yield SSEEvent.error(
                "CANCELLED",
                t("error.cancelled", language),
                conversation_id=str(current_conversation_id) if current_conversation_id else None,
            ).to_sse()
        except Exception as exc:
            mark_conversation_exception(conversation, str(exc))
            await db.commit()
            yield SSEEvent.error(
                "EXECUTION_ERROR",
                str(exc),
                conversation_id=str(current_conversation_id) if current_conversation_id else None,
            ).to_sse()
        finally:
            active_query_registry.release(query_key)

    return EventSourceResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/stop", response_model=APIResponse[dict[str, Any]])
async def stop_chat(request: ChatStopRequest) -> APIResponse[dict[str, Any]]:
    """停止正在执行的查询."""
    if active_query_registry.stop(request.conversation_id):
        return APIResponse.ok(
            data={"stopped": True},
            message=t("stop.sent", "zh"),
        )

    return APIResponse.ok(
        data={"stopped": False},
        message=t("stop.not_found", "zh"),
    )


@router.get("/{conversation_id}/messages", response_model=APIResponse[MessagePaginatedResponse])
async def list_messages(
    conversation_id: str,
    cursor: str | None = Query(None, description="游标（ISO datetime），获取此之前的消息"),
    limit: int = Query(50, ge=1, le=100, description="返回数量"),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[MessagePaginatedResponse]:
    """
    分页获取对话消息。

    Args:
        conversation_id: 对话 UUID
        cursor: ISO datetime 格式的游标，用于获取更早的消息。为 null 时获取最新消息。
        limit: 返回消息数量（1-100，默认 50）

    Returns:
        消息分页响应，包含 items、total 和 next_cursor
    """
    try:
        conv_id = UUID(conversation_id)
    except ValueError:
        return APIResponse.fail(
            code="INVALID_UUID",
            message="无效的对话 ID 格式",
        )

    # 验证对话存在
    conv_query = select(Conversation).where(Conversation.id == conv_id)
    result = await db.execute(conv_query)
    conversation = result.scalar_one_or_none()
    if not conversation:
        return APIResponse.fail(
            code="NOT_FOUND",
            message="对话不存在",
        )

    # 统计总消息数
    count_query = select(func.count(Message.id)).where(Message.conversation_id == conv_id)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # 构建消息查询
    messages_query = select(Message).where(Message.conversation_id == conv_id)

    # 应用游标过滤（获取此时间之前的消息，用于向后翻页）
    if cursor:
        try:
            cursor_dt = datetime.fromisoformat(cursor.replace("Z", "+00:00"))
            messages_query = messages_query.where(Message.created_at < cursor_dt)
        except ValueError:
            return APIResponse.fail(
                code="INVALID_CURSOR",
                message="无效的游标格式，应为 ISO datetime",
            )

    # 按创建时间降序排列（最新的在前），再加载 limit+1 个来判断是否有下一页
    messages_query = messages_query.order_by(desc(Message.created_at)).limit(limit + 1)

    result = await db.execute(messages_query)
    messages = list(result.scalars())

    # 判断是否有更多消息
    next_cursor = None
    if len(messages) > limit:
        # 有更多消息，截取到 limit 个，设置 next_cursor 为最后一条消息的时间
        messages = messages[:limit]
        next_cursor = messages[-1].created_at.isoformat()

    # 将 Message 对象转换为 MessageResponse
    message_responses = [
        MessageResponse(
            id=msg.id,
            role=msg.role,
            content=msg.content,
            metadata=msg.extra_data,
            created_at=msg.created_at,
        )
        for msg in messages
    ]

    return APIResponse.ok(
        data=MessagePaginatedResponse(
            items=message_responses,
            total=total,
            next_cursor=next_cursor,
        )
    )
