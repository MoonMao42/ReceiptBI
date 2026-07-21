"""Low-coupling process boundary for the trusted Rust SQLite executor."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

REQUEST_CONTRACT = "receiptbi-sqlite-execute@1"
RESULT_CONTRACT = "receiptbi-sqlite-result@1"
SIDECAR_ENV = "RECEIPTBI_SQLITE_EXECUTOR_PATH"
MAX_CORE_ROWS = 50_000
MAX_CORE_BYTES = 32 * 1024 * 1024
CORE_TIMEOUT_SECONDS = 60.0


class TrustedSQLiteExecutorError(RuntimeError):
    """A structured rejection or failure returned by the Rust boundary."""

    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class TrustedSQLiteExecutionCancelledError(TrustedSQLiteExecutorError):
    def __init__(self) -> None:
        super().__init__("query_cancelled", "SQLite query cancelled", retryable=True)


@dataclass(frozen=True, slots=True)
class TrustedSQLiteExecutionResult:
    data: list[dict[str, Any]]
    truncated: bool
    source_identity: dict[str, int]
    duration_ms: int
    byte_count: int
    truncation_reason: str | None


def configured_sidecar_path() -> Path | None:
    """Return an explicitly configured sidecar path, if one exists."""

    configured = os.environ.get(SIDECAR_ENV, "").strip()
    return Path(configured).expanduser() if configured else None


class RustSQLiteSidecarExecutor:
    """Execute one SQLite query in an isolated Rust process."""

    def __init__(self, executable: Path):
        path = executable.expanduser().resolve()
        if not path.is_file() or not os.access(path, os.X_OK):
            raise RuntimeError(f"Trusted SQLite executor is not executable: {path}")
        self.executable = path

    def execute(
        self,
        *,
        database_path: Path,
        sql: str,
        allowed_relations: list[str],
        max_rows: int,
        cancellation_event: threading.Event | None = None,
        timeout_seconds: float = CORE_TIMEOUT_SECONDS,
    ) -> TrustedSQLiteExecutionResult:
        query_id = f"api-{uuid4().hex}"
        effective_timeout = max(0.01, min(float(timeout_seconds), CORE_TIMEOUT_SECONDS))
        request = {
            "contract": REQUEST_CONTRACT,
            "queryId": query_id,
            "databasePath": str(database_path.expanduser().resolve()),
            "sql": sql,
            "allowedRelations": allowed_relations or ["__receiptbi_no_relation__"],
            "maxRows": max(1, min(int(max_rows), MAX_CORE_ROWS)),
            "maxBytes": MAX_CORE_BYTES,
            "timeoutMs": int(effective_timeout * 1000),
        }
        payload = json.dumps(request, ensure_ascii=False, separators=(",", ":"))
        process = subprocess.Popen(
            [str(self.executable)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        deadline = time.monotonic() + effective_timeout + 2.0
        pending_input: str | None = payload
        stdout = ""
        stderr = ""
        while True:
            try:
                stdout, stderr = process.communicate(input=pending_input, timeout=0.05)
                break
            except subprocess.TimeoutExpired:
                pending_input = None
                if cancellation_event is not None and cancellation_event.is_set():
                    self._terminate(process)
                    raise TrustedSQLiteExecutionCancelledError() from None
                if time.monotonic() >= deadline:
                    self._terminate(process)
                    raise TrustedSQLiteExecutorError(
                        "query_timed_out",
                        "Trusted SQLite executor timed out",
                        retryable=True,
                    ) from None

        try:
            response = json.loads(stdout)
        except json.JSONDecodeError as exc:
            detail = stderr.strip()[-500:]
            raise TrustedSQLiteExecutorError(
                "invalid_sidecar_response",
                f"Trusted SQLite executor returned invalid output: {detail}",
            ) from exc
        if not isinstance(response, dict):
            raise TrustedSQLiteExecutorError(
                "invalid_sidecar_response",
                "Trusted SQLite executor returned an invalid response object",
            )
        if response.get("contract") != RESULT_CONTRACT or response.get("queryId") != query_id:
            raise TrustedSQLiteExecutorError(
                "invalid_sidecar_response",
                "Trusted SQLite executor response identity did not match the request",
            )
        if not response.get("ok"):
            error = response.get("error") if isinstance(response.get("error"), dict) else {}
            raise TrustedSQLiteExecutorError(
                str(error.get("code") or "query_execution_failed"),
                str(error.get("message") or "Trusted SQLite query failed"),
                retryable=bool(error.get("retryable")),
            )
        if process.returncode != 0:
            raise TrustedSQLiteExecutorError(
                "invalid_sidecar_response",
                "Trusted SQLite executor exited unsuccessfully after reporting success",
            )

        columns = response.get("columns")
        rows = response.get("rows")
        source_identity = response.get("sourceIdentity")
        if (
            not isinstance(columns, list)
            or not columns
            or not all(isinstance(column, str) and column for column in columns)
            or len(set(columns)) != len(columns)
        ):
            raise TrustedSQLiteExecutorError(
                "invalid_sidecar_response",
                "Trusted SQLite executor returned invalid columns",
            )
        if not isinstance(rows, list) or not all(
            isinstance(row, dict)
            and set(row) == set(columns)
            and all(value is None or type(value) in (int, float, str) for value in row.values())
            for row in rows
        ):
            raise TrustedSQLiteExecutorError(
                "invalid_sidecar_response",
                "Trusted SQLite executor returned invalid rows",
            )
        identity_keys = ("dev", "ino", "ctimeNs", "mtimeNs", "size")
        if not isinstance(source_identity, dict) or not all(
            type(source_identity.get(key)) is int for key in identity_keys
        ):
            raise TrustedSQLiteExecutorError(
                "invalid_sidecar_response",
                "Trusted SQLite executor omitted the source identity",
            )
        truncation_reason = response.get("truncatedBy")
        if truncation_reason not in (None, "row_limit", "byte_limit"):
            raise TrustedSQLiteExecutorError(
                "invalid_sidecar_response",
                "Trusted SQLite executor returned an unknown truncation reason",
            )
        return TrustedSQLiteExecutionResult(
            data=rows,
            truncated=truncation_reason is not None,
            source_identity={key: int(source_identity[key]) for key in identity_keys},
            duration_ms=int(response.get("durationMs") or 0),
            byte_count=int(response.get("byteCount") or 0),
            truncation_reason=truncation_reason,
        )

    @staticmethod
    def _terminate(process: subprocess.Popen[str]) -> None:
        process.terminate()
        try:
            process.communicate(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
