"""Immutable runtime capability and disclosure policy.

The settings row describes user intent.  This module turns that mutable row into
one strict snapshot that can be passed through an investigation without tools
re-reading settings midway through a run.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


class ExecutionPolicyError(RuntimeError):
    """Raised when a disabled capability reaches a defensive runtime boundary."""


_MISSING = object()
_PYTHON_TOOL_KINDS = frozenset({"python", "dependency"})
_BUSINESS_EVIDENCE_KINDS = frozenset(
    {
        "analysis_playbook_execution",
        "business_rule_application",
        "confirmation_application",
        "correction_application",
        "golden_regression_validation",
        "minimal_verified_report_fallback",
        "relationship_application",
        "relationship_validation",
        "semantic_execution_verification",
        "semantic_revision_transition",
        "validation",
    }
)
_BUSINESS_EVIDENCE_FIELDS = frozenset(
    {
        "active_revision_id",
        "analysis_run_id",
        "checks",
        "columns",
        "contract_id",
        "correction_id",
        "definition_hash",
        "kind",
        "materialized_rows",
        "purpose",
        "relationship_key",
        "result_hash",
        "result_name",
        "rows_count",
        "rule_key",
        "semantic_entry_id",
        "status",
        "summary",
        "summary_code",
        "truncated",
    }
)
_BUSINESS_PROFILE_FIELDS = frozenset(
    {
        "cardinality",
        "columns",
        "duplicate_keys",
        "keys",
        "left_match_rate",
        "materialized_rows",
        "numeric",
        "right_match_rate",
        "row_multiplier",
        "truncated",
    }
)
_SENSITIVE_PERSISTENCE_KEYS = frozenset(
    {
        "code",
        "diagnostic_entry",
        "diagnostics",
        "last_error",
        "planned_sql",
        "python",
        "python_images",
        "python_output",
        "replay_journal",
        "sql",
        "stderr",
        "stdout",
        "technical_error",
        "tool_history",
        "tool_plan",
        "traceback",
    }
)
_PUBLIC_RESULT_KEYS = frozenset(
    {
        "diagnostics",
        "python",
        "python_output",
        "sql",
        "tool_history",
    }
)


def _strict_flag(
    source: Mapping[str, Any] | object | None,
    key: str,
    *,
    default: bool,
) -> bool:
    """Read only real booleans; malformed persisted values fail closed."""

    if source is None:
        return default
    if isinstance(source, Mapping):
        raw = source.get(key, _MISSING)
    else:
        raw = getattr(source, key, _MISSING)
    if raw is _MISSING:
        return default
    return raw if type(raw) is bool else False


@dataclass(frozen=True, slots=True)
class ExecutionPolicy:
    """Capability and disclosure snapshot for one execution service/runtime."""

    python_enabled: bool = True
    auto_repair_enabled: bool = True
    diagnostics_enabled: bool = True

    @classmethod
    def from_settings(
        cls,
        source: Mapping[str, Any] | object | None,
    ) -> ExecutionPolicy:
        """Derive a strict immutable policy while preserving product defaults."""

        return cls(
            python_enabled=_strict_flag(source, "python_enabled", default=True),
            auto_repair_enabled=_strict_flag(
                source,
                "auto_repair_enabled",
                default=True,
            ),
            diagnostics_enabled=_strict_flag(
                source,
                "diagnostics_enabled",
                default=True,
            ),
        )

    @property
    def retry_budget(self) -> dict[str, int]:
        """PydanticAI retry budgets; validators still run when both are zero."""

        if not self.auto_repair_enabled:
            return {"tools": 0, "output": 0}
        return {"tools": 5, "output": 4}

    def require_python(self, operation: str) -> None:
        if not self.python_enabled:
            raise ExecutionPolicyError(f"Python 能力已关闭，不能执行{operation}。")

    def require_auto_repair(self, operation: str) -> None:
        if not self.auto_repair_enabled:
            raise ExecutionPolicyError(f"自动修复已关闭，不能执行{operation}。")

    def validate_result_boundary(self, result_data: Mapping[str, Any]) -> None:
        """Reject Python-derived payloads that bypassed the advertised tool set."""

        if self.python_enabled:
            return
        raw_history = result_data.get("tool_history")
        tool_history = raw_history if isinstance(raw_history, list) else []
        has_python_receipt = any(
            isinstance(item, Mapping) and item.get("kind") in _PYTHON_TOOL_KINDS
            for item in tool_history
        )
        has_python_payload = any(
            bool(result_data.get(key)) for key in ("python", "python_output", "python_images")
        )
        if has_python_receipt or has_python_payload:
            raise ExecutionPolicyError("Python 能力已关闭，拒绝写入 Python 或依赖安装产生的结果。")

    def public_event_data(
        self,
        event_type: str,
        data: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        """Return the ordinary-client payload allowed by the disclosure setting."""

        copied = dict(data)
        if self.diagnostics_enabled:
            return copied
        if event_type == "python_output":
            return None
        if event_type == "result":
            for key in _PUBLIC_RESULT_KEYS:
                copied.pop(key, None)
        elif event_type == "progress":
            copied.pop("diagnostic_entry", None)
            copied.pop("diagnostics", None)
        elif event_type == "error":
            copied.pop("diagnostic_entry", None)
            copied.pop("diagnostics", None)
        return copied

    def business_evidence(
        self,
        tool_history: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Reduce internal tool history to bounded business validation receipts."""

        evidence: list[dict[str, Any]] = []
        for raw_item in tool_history:
            kind = str(raw_item.get("kind") or "")
            if kind not in _BUSINESS_EVIDENCE_KINDS:
                continue
            item = {
                key: self.sanitize_for_persistence(value)
                for key, value in raw_item.items()
                if key in _BUSINESS_EVIDENCE_FIELDS
            }
            raw_profile = raw_item.get("profile")
            if isinstance(raw_profile, Mapping):
                profile = {
                    key: self.sanitize_for_persistence(value)
                    for key, value in raw_profile.items()
                    if key in _BUSINESS_PROFILE_FIELDS
                }
                if profile:
                    item["profile"] = profile
            if item:
                evidence.append(item)
        return evidence[-50:]

    def sanitize_for_persistence(self, value: Any) -> Any:
        """Recursively remove raw execution material while retaining business state."""

        if self.diagnostics_enabled:
            return value
        if isinstance(value, Mapping):
            return {
                str(key): self.sanitize_for_persistence(item)
                for key, item in value.items()
                if str(key).casefold() not in _SENSITIVE_PERSISTENCE_KEYS
                and not str(key).casefold().endswith("_sql")
            }
        if isinstance(value, list):
            return [self.sanitize_for_persistence(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self.sanitize_for_persistence(item) for item in value)
        return value

    def checkpoint_payload(
        self,
        current: Mapping[str, Any] | None,
        *,
        tool_history: list[dict[str, Any]] | None = None,
        updates: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build a checkpoint without ever persisting disabled diagnostics."""

        checkpoint = dict(self.sanitize_for_persistence(dict(current or {})))
        if tool_history is not None:
            if self.diagnostics_enabled:
                checkpoint["tool_history"] = tool_history
            else:
                evidence = self.business_evidence(tool_history)
                if evidence:
                    checkpoint["business_evidence"] = evidence
        if updates:
            checkpoint.update(dict(self.sanitize_for_persistence(dict(updates))))
        if not self.diagnostics_enabled:
            checkpoint["resumable"] = False
            checkpoint.pop("last_error", None)
            checkpoint.pop("validations", None)
        return checkpoint

    def technical_details(
        self,
        details: Mapping[str, Any],
        *,
        tool_history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Build artifact details honoring the disclosure policy."""

        sanitized = dict(self.sanitize_for_persistence(dict(details)))
        if not self.diagnostics_enabled and tool_history is not None:
            evidence = self.business_evidence(tool_history)
            if evidence:
                sanitized["business_evidence"] = evidence
        return sanitized
