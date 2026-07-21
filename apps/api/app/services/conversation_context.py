"""Build bounded, business-facing context for multi-turn investigations."""

from __future__ import annotations

import json
import re
from typing import Any

_MESSAGE_TEXT_LIMIT = 1_600
_REPORT_SUMMARY_LIMIT = 1_000
_REPORT_FINDING_LIMIT = 420
_REPORT_METRIC_LIMIT = 12
_REPORT_FINDINGS_LIMIT = 8
_CONVERSATION_CHAR_BUDGET = 16_000
_VISUALIZATION_SERIES_LIMIT = 12
_VISUALIZATION_FORMATS = {
    "auto",
    "number",
    "integer",
    "compact",
    "currency",
    "percent",
}

_VISUALIZATION_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("pie", ("饼图", "pie chart", "pie-chart")),
    ("bar", ("柱状图", "条形图", "bar chart", "column chart")),
    ("line", ("折线图", "趋势图", "line chart")),
    ("scatter", ("散点图", "scatter plot", "scatter chart")),
    ("area", ("面积图", "area chart")),
    ("table", ("明细表", "数据表", "表格", "table")),
)


def _bounded_text(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"\s+", " ", str(value)).strip()
    if not normalized:
        return None
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: max(limit - 1, 1)].rstrip()}…"


def _compact_metric(value: Any) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    metric = {
        key: bounded
        for key, limit in (("label", 160), ("value", 160), ("context", 240))
        if (bounded := _bounded_text(value.get(key), limit)) is not None
    }
    return metric or None


def _compact_visualization(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None

    if value.get("version") == 1:
        compact: dict[str, Any] = {"version": 1}
        for key, limit in (("type", 40), ("title", 240)):
            bounded = _bounded_text(value.get(key), limit)
            if bounded is not None:
                compact[key] = bounded

        raw_encoding = value.get("encoding")
        if isinstance(raw_encoding, dict):
            encoding: dict[str, Any] = {}
            raw_x = raw_encoding.get("x")
            if isinstance(raw_x, dict):
                x_field = _bounded_text(raw_x.get("field"), 160)
                if x_field is not None:
                    encoding["x"] = {"field": x_field}

            raw_y = raw_encoding.get("y")
            if isinstance(raw_y, list):
                y_series: list[dict[str, str]] = []
                for item in raw_y[:_VISUALIZATION_SERIES_LIMIT]:
                    if not isinstance(item, dict):
                        continue
                    field = _bounded_text(item.get("field"), 160)
                    if field is None:
                        continue
                    series = {"field": field}
                    label = _bounded_text(item.get("label"), 160)
                    if label is not None:
                        series["label"] = label
                    number_format = _bounded_text(item.get("format"), 40)
                    if number_format in _VISUALIZATION_FORMATS:
                        series["format"] = number_format
                    y_series.append(series)
                if y_series:
                    encoding["y"] = y_series
            if encoding:
                compact["encoding"] = encoding

        raw_data_ref = value.get("data_ref")
        if isinstance(raw_data_ref, dict):
            result_name = _bounded_text(raw_data_ref.get("result_name"), 160)
            if result_name is not None:
                compact["data_ref"] = {"result_name": result_name}
        return compact

    # Reports written before ChartSpec v1 used a flat renderer contract. Keep
    # only its established business-facing fields for conversation continuity.
    compact: dict[str, Any] = {}
    for key, limit in (
        ("type", 40),
        ("title", 240),
        ("x", 120),
        ("y", 120),
        ("value", 120),
        ("color", 120),
        ("result_name", 120),
    ):
        bounded = _bounded_text(value.get(key), limit)
        if bounded is not None:
            compact[key] = bounded
    return compact or None


def compact_report_context(
    report: Any,
    *,
    fallback_visualization: Any = None,
) -> dict[str, Any] | None:
    """Whitelist the small part of a report that is useful in the next turn.

    Raw rows, SQL, Python, tool history, images and technical diagnostics are
    intentionally not accepted by this function.
    """

    if not isinstance(report, dict):
        report = {}
    compact: dict[str, Any] = {}
    for key, limit in (
        ("status", 40),
        ("title", 240),
        ("summary", _REPORT_SUMMARY_LIMIT),
    ):
        bounded = _bounded_text(report.get(key), limit)
        if bounded is not None:
            compact[key] = bounded

    findings = [
        bounded
        for item in list(report.get("findings") or [])[:_REPORT_FINDINGS_LIMIT]
        if (bounded := _bounded_text(item, _REPORT_FINDING_LIMIT)) is not None
    ]
    if findings:
        compact["findings"] = findings

    metrics = [
        metric
        for item in list(report.get("metrics") or [])[:_REPORT_METRIC_LIMIT]
        if (metric := _compact_metric(item)) is not None
    ]
    if metrics:
        compact["metrics"] = metrics

    visualization = _compact_visualization(report.get("visualization") or fallback_visualization)
    if visualization is not None:
        compact["visualization"] = visualization

    return compact or None


def compact_assistant_message_context(extra_data: Any) -> dict[str, Any]:
    """Extract durable report identity and actual delivery from one message."""

    if not isinstance(extra_data, dict):
        return {}
    compact: dict[str, Any] = {}
    for key, limit in (("analysis_run_id", 64), ("original_query", 1_000)):
        bounded = _bounded_text(extra_data.get(key), limit)
        if bounded is not None:
            compact[key] = bounded
    report_context = compact_report_context(
        extra_data.get("report"),
        fallback_visualization=extra_data.get("visualization"),
    )
    if report_context is not None:
        compact["report_context"] = report_context
    return compact


def _requested_visualization(text: str) -> str | None:
    normalized = text.casefold()
    for kind, terms in _VISUALIZATION_TERMS:
        for term in terms:
            position = normalized.find(term)
            if position < 0:
                continue
            prefix = normalized[max(0, position - 8) : position]
            if re.search(r"(?:不要|不用|别|无需|不需要).{0,4}$", prefix):
                continue
            return kind
    return None


def _visualization_family(value: Any) -> str | None:
    normalized = str(value or "").strip().casefold()
    aliases = {
        "donut": "pie",
        "doughnut": "pie",
        "column": "bar",
        "horizontal_bar": "bar",
        "trend": "line",
        "data_table": "table",
    }
    return aliases.get(normalized, normalized or None)


def _likely_follow_up(query: str) -> bool:
    normalized = re.sub(r"\s+", "", query).casefold()
    if not normalized:
        return False
    return bool(
        re.search(
            r"(?:刚才|上次|上一|继续|这个|那个|还是|不对|不是|怎么|为什么|懂|"
            r"改成|换成|重新|哪个|哪家|再来|刚刚|吗$|呢$|吧$)",
            normalized,
        )
    )


def _unmet_presentation_requests(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pending: list[dict[str, Any]] = []
    for index in range(len(messages) - 1, -1, -1):
        user = messages[index]
        if user.get("role") != "user":
            continue
        request_text = str(user.get("content") or "")
        requested = _requested_visualization(request_text)
        if requested is None:
            continue
        assistant = next(
            (item for item in messages[index + 1 :] if item.get("role") == "assistant"),
            None,
        )
        if assistant is None:
            delivered = None
        else:
            report = assistant.get("report_context") or {}
            delivered = _visualization_family((report.get("visualization") or {}).get("type"))
        if delivered == requested:
            continue
        pending.append(
            {
                "kind": "presentation_request",
                "status": "unmet",
                "requested_output": requested,
                "actual_output": delivered,
                "request": _bounded_text(request_text, 500),
                "source_analysis_run_id": (
                    assistant.get("analysis_run_id") if assistant is not None else None
                ),
            }
        )
        if len(pending) >= 3:
            break
    return pending


def _safe_history_item(item: dict[str, Any]) -> dict[str, Any] | None:
    role = str(item.get("role") or "")
    if role not in {"user", "assistant"}:
        return None
    content = _bounded_text(item.get("content"), _MESSAGE_TEXT_LIMIT)
    if content is None:
        return None
    safe: dict[str, Any] = {"role": role, "content": content}
    if role == "assistant":
        for key in ("analysis_run_id", "original_query", "report_context", "confirmation"):
            value = item.get(key)
            if value not in (None, {}, []):
                safe[key] = value
    return safe


def build_conversation_context(
    history: list[dict[str, Any]],
    *,
    current_query: str,
    char_budget: int = _CONVERSATION_CHAR_BUDGET,
) -> dict[str, Any]:
    """Return newest bounded turns plus explicit continuity state.

    The caller already applies the configured round count. This second layer is
    a total-size guard, not another hidden fixed-round cutoff.
    """

    prepared = [safe for item in history if (safe := _safe_history_item(item)) is not None]
    selected_reversed: list[dict[str, Any]] = []
    used = 0
    for item in reversed(prepared):
        serialized = json.dumps(item, ensure_ascii=False, separators=(",", ":"), default=str)
        if selected_reversed and used + len(serialized) > max(char_budget, 1_000):
            continue
        selected_reversed.append(item)
        used += len(serialized)
    messages = list(reversed(selected_reversed))
    unmet_requests = _unmet_presentation_requests(messages)
    continuation_likely = _likely_follow_up(current_query)
    current_visualization = _requested_visualization(current_query)
    if unmet_requests and current_visualization == unmet_requests[0].get("requested_output"):
        continuation_likely = True
    context: dict[str, Any] = {
        "version": 1,
        "continuity_policy": (
            "Unless the user clearly changes topic, interpret follow-ups, challenges and format "
            "corrections as continuations of the latest investigation. Complete any unmet request "
            "instead of answering it as a standalone glossary question. Historical numbers remain "
            "references and must be rechecked against current data before reuse."
        ),
        "continuation_likely": continuation_likely,
        "unmet_requests": unmet_requests,
        "messages": messages,
        "budget": {
            "available_messages": len(prepared),
            "included_messages": len(messages),
            "truncated": len(messages) < len(prepared),
            "char_budget": char_budget,
        },
    }
    if continuation_likely and unmet_requests:
        context["current_turn_contract"] = {
            "mode": "complete_unmet_request",
            "request": unmet_requests[0],
            "instruction": (
                "Treat the current message as feedback on the previous delivery. Complete or "
                "correct the unmet request; do not replace the task with a standalone definition."
            ),
        }
    return context


def render_conversation_context(context: dict[str, Any]) -> str:
    """Serialize context under an explicit boundary for the model."""

    if not context.get("messages"):
        return ""
    return (
        "<conversation_context>\n"
        f"{json.dumps(context, ensure_ascii=False, separators=(',', ':'), default=str)}\n"
        "</conversation_context>"
    )
