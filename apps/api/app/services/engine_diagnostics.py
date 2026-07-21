"""Diagnostics helpers for the chat execution engine."""

from typing import TypedDict


class DiagnosticEntry(TypedDict, total=False):
    attempt: int
    phase: str
    status: str
    message: str
    error_code: str | None
    error_category: str | None
    recoverable: bool | None
    sql: str | None
    python: str | None


def truncate_text(value: str | None, limit: int = 400) -> str | None:
    if not value:
        return None
    normalized = value.strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def build_diagnostic_entry(
    *,
    attempt: int,
    phase: str,
    status: str,
    message: str,
    error_code: str | None = None,
    error_category: str | None = None,
    recoverable: bool | None = None,
    sql: str | None = None,
    python: str | None = None,
) -> DiagnosticEntry:
    return {
        "attempt": attempt,
        "phase": phase,
        "status": status,
        "message": message,
        "error_code": error_code,
        "error_category": error_category,
        "recoverable": recoverable,
        "sql": truncate_text(sql),
        "python": truncate_text(python),
    }


def categorize_sql_error(message: str) -> tuple[str, str, bool]:
    normalized = message.lower()
    if any(
        token in normalized
        for token in (
            "password authentication failed",
            "access denied",
            "authentication failed",
            "login failed",
        )
    ):
        return "DB_AUTH_ERROR", "connection", False
    if any(
        token in normalized
        for token in (
            "connection refused",
            "could not connect",
            "can't connect",
            "server closed the connection",
            "timed out",
            "name or service not known",
            "network is unreachable",
        )
    ):
        return "DB_CONNECTION_ERROR", "connection", False
    if any(token in normalized for token in ("syntax", "parse error", "sql syntax", "near ")):
        return "SQL_SYNTAX_ERROR", "sql", True
    if any(
        token in normalized
        for token in ("no such table", "doesn't exist", "undefined table", "unknown table")
    ):
        return "SQL_TABLE_ERROR", "schema", True
    if any(
        token in normalized
        for token in (
            "no such column",
            "unknown column",
            "undefined column",
            "ambiguous column",
        )
    ):
        return "SQL_COLUMN_ERROR", "schema", True
    if any(
        token in normalized
        for token in ("只允许执行只读查询", "危险关键字", "多语句", "sql 注释", "只读查询")
    ):
        return "SQL_SAFETY_ERROR", "safety", False
    return "SQL_EXECUTION_ERROR", "sql", True
