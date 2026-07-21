"""Backend i18n support for user-visible SSE messages."""

from __future__ import annotations

LANG = {"en", "zh"}

MESSAGES: dict[str, dict[str, str]] = {
    "zh": {
        "progress.start": "开始处理请求...",
        "progress.context_ready": "执行上下文已准备",
        "progress.analyzing": "正在分析...",
        "progress.routing": "正在路由...",
        "progress.generating_sql": "正在生成 SQL...",
        "progress.executing": "正在执行...",
        "progress.processing": "正在处理...",
        "progress.visualizing": "正在生成图表...",
        "progress.summarizing": "正在总结...",
        "error.not_found": "对话不存在",
        "error.cancelled": "查询已取消",
        "error.execution": "执行出错",
        "stop.sent": "查询停止请求已发送",
        "stop.not_found": "没有找到正在执行的查询",
    },
    "en": {
        "progress.start": "Processing request...",
        "progress.context_ready": "Execution context ready",
        "progress.analyzing": "Analyzing...",
        "progress.routing": "Routing...",
        "progress.generating_sql": "Generating SQL...",
        "progress.executing": "Executing...",
        "progress.processing": "Processing...",
        "progress.visualizing": "Generating chart...",
        "progress.summarizing": "Summarizing...",
        "error.not_found": "Conversation not found",
        "error.cancelled": "Query cancelled",
        "error.execution": "Execution error",
        "stop.sent": "Stop request sent",
        "stop.not_found": "No active query found",
    },
}


def _t(key: str, lang: str) -> str:
    """Translate a key to the requested language."""

    if lang not in LANG:
        lang = "zh"
    return MESSAGES[lang].get(key, MESSAGES["zh"].get(key, key))


def t(key: str, lang: str = "zh") -> str:
    """Translate a message key."""

    return _t(key, lang)


def get_progress_message(stage: str, lang: str = "zh") -> str:
    """Get a localized progress message for a given stage."""

    key = f"progress.{stage}"
    message = _t(key, lang)
    return stage.replace("_", " ").title() if message == key else message
