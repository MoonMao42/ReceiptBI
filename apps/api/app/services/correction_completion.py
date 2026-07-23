"""Server-owned proof that a report correction affected the delivered result."""

from __future__ import annotations

import re
from typing import Any

from app.services.metric_lineage import prove_metric_application_lineage


class CorrectionCompletionError(ValueError):
    """The run cannot prove that its required correction reached the final result."""


def _dependencies(step: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("source_result", "left_result", "right_result"):
        value = str(step.get(key) or "").strip()
        if value:
            values.append(value)
    values.extend(
        str(value).strip() for value in step.get("input_results") or [] if str(value).strip()
    )
    return values


def _is_ancestor(
    tool_history: list[dict[str, Any]],
    *,
    ancestor: str,
    descendant: str,
) -> bool:
    if not ancestor or not descendant:
        return False
    if ancestor == descendant:
        return True
    by_result: dict[str, dict[str, Any]] = {}
    for step in tool_history:
        if not isinstance(step, dict) or not step.get("result_name"):
            continue
        # Validation and receipt records refer to an existing result; they must
        # not replace the transformation that produced its lineage.
        if not _dependencies(step):
            continue
        by_result[str(step["result_name"])] = step
    pending = [descendant]
    visited: set[str] = set()
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        for dependency in _dependencies(by_result.get(current) or {}):
            if dependency == ancestor:
                return True
            pending.append(dependency)
    return False


def _last_index(
    tool_history: list[dict[str, Any]],
    predicate: Any,
) -> int | None:
    for index in range(len(tool_history) - 1, -1, -1):
        if predicate(tool_history[index]):
            return index
    return None


def _relationship_evidence_matches(
    item: dict[str, Any],
    *,
    rule_key: str,
    definition_hash: str,
) -> bool:
    evidence_key = str(item.get("candidate_relationship_key") or item.get("relationship_key") or "")
    return evidence_key == rule_key and str(item.get("definition_hash") or "") == definition_hash


def is_reusable_full_relationship_evidence(item: dict[str, Any]) -> bool:
    """Accept only system-scoped proof over complete, table-bound relation inputs."""

    source_refs = item.get("source_refs")
    profile = item.get("profile")
    if not isinstance(source_refs, list) or not isinstance(profile, dict):
        return False
    valid_refs = [
        ref
        for ref in source_refs
        if isinstance(ref, dict)
        and str(ref.get("source_id") or "")
        and str(ref.get("table_or_view") or "")
        and ref.get("query_scope") == "full"
    ]
    endpoints = {
        (str(ref.get("source_id") or ""), str(ref.get("table_or_view") or "")) for ref in valid_refs
    }
    return (
        item.get("evidence_origin") == "system"
        and item.get("evidence_scope") == "full_relation"
        and item.get("completeness") == "complete"
        and item.get("reusable_proof_eligible") is True
        and profile.get("truncated") is False
        and len(source_refs) == len(valid_refs) == 2
        and len(endpoints) == 2
    )


def _build_relationship_receipt(
    base: dict[str, Any],
    required: dict[str, Any],
    tool_history: list[dict[str, Any]],
    *,
    final_result: str,
) -> dict[str, Any]:
    """Prove a candidate relationship was tested, joined, and delivered."""

    rule_key = str(required.get("target_key") or "")
    definition_hash = str(required.get("definition_hash") or "")
    joins = [
        (index, item)
        for index, item in enumerate(tool_history)
        if item.get("kind") == "join"
        and _relationship_evidence_matches(
            item,
            rule_key=rule_key,
            definition_hash=definition_hash,
        )
        and _is_ancestor(
            tool_history,
            ancestor=str(item.get("result_name") or ""),
            descendant=final_result,
        )
    ]
    if not joins:
        raise CorrectionCompletionError("这条关联修正尚未真正生成最终结果")
    join_index, join = joins[-1]
    join_result = str(join.get("result_name") or "")
    join_profile = join.get("profile")
    join_input_hashes = join.get("input_hashes")
    if (
        not join_result
        or not isinstance(join_profile, dict)
        or not isinstance(join_input_hashes, dict)
        or not join_input_hashes
        or len(str(join.get("result_hash") or "")) != 64
        or not isinstance(join.get("source_refs"), list)
        or not join.get("source_refs")
    ):
        raise CorrectionCompletionError("这条关联修正缺少完整的真实关联证据")
    if not is_reusable_full_relationship_evidence(join):
        raise CorrectionCompletionError(
            "这次关联只证明了当前结果，尚未形成完整且可复用的全局关系证据"
        )

    relationship_validation = next(
        (
            item
            for item in reversed(tool_history[:join_index])
            if item.get("kind") in {"relationship_validation", "relationship_application"}
            and _relationship_evidence_matches(
                item,
                rule_key=rule_key,
                definition_hash=definition_hash,
            )
            and item.get("left_result") == join.get("left_result")
            and item.get("right_result") == join.get("right_result")
            and item.get("profile") == join_profile
            and item.get("input_hashes") == join_input_hashes
            and is_reusable_full_relationship_evidence(item)
        ),
        None,
    )
    if relationship_validation is None:
        raise CorrectionCompletionError("这条关联修正没有通过当前数据的关联验收")

    validation_index = _last_index(
        tool_history,
        lambda item: (
            item.get("kind") == "validation"
            and str(item.get("result_name") or "") == final_result
            and bool(item.get("result_hash"))
        ),
    )
    if validation_index is None or validation_index <= join_index:
        raise CorrectionCompletionError("最终结果需要在应用关联修正后重新核对")

    return {
        **base,
        "status": "verified",
        "summary_code": "correction_relationship_verified",
        "action_kind": "relationship",
        "application_result_name": join_result,
        "source_result_names": [join.get("left_result"), join.get("right_result")],
        "source_refs": list(join.get("source_refs") or []),
        "input_hashes": dict(join_input_hashes),
        "result_hash": join.get("result_hash"),
        "relationship_profile": dict(join_profile),
        "evidence_origin": "system",
        "evidence_scope": "full_relation",
        "completeness": "complete",
        "reusable_proof_eligible": True,
        "checks": [
            "current_relationship_definition_tested",
            "relationship_validation_passed",
            "full_relation_reusable_proof",
            "join_reaches_final_result",
            "final_result_revalidated_after_join",
        ],
        "summary": "这条关联修正已在当前数据中通过验收，并进入重新核对后的最终结果。",
    }


def build_correction_application_receipt(
    required: dict[str, Any] | None,
    tool_history: list[dict[str, Any]],
    *,
    final_result: str | None,
) -> dict[str, Any] | None:
    """Return a deterministic receipt or reject an unproven executable correction."""

    if not required:
        return None
    base = {
        "version": 1,
        "kind": "correction_application",
        "correction_id": required.get("id"),
        "source_run_id": required.get("source_run_id"),
        "semantic_entry_id": required.get("semantic_entry_id"),
        "rule_key": required.get("target_key"),
        "rule_value": required.get("text"),
        "definition_hash": required.get("definition_hash"),
        "final_result_name": final_result,
    }
    if not required.get("executable"):
        return {
            **base,
            "status": "definition_only",
            "summary_code": "correction_definition_only",
            "checks": ["business_definition_recorded"],
            "summary": "已按这条修正重新调查；它目前只作为业务定义保存，尚不能自动验证执行。",
        }
    if not final_result:
        raise CorrectionCompletionError("修正后的调查没有可核对的最终结果")

    if required.get("correction_type") == "relationship_rule":
        return _build_relationship_receipt(
            base,
            required,
            tool_history,
            final_result=final_result,
        )

    semantic_entry_id = str(required.get("semantic_entry_id") or "")
    definition_hash = str(required.get("definition_hash") or "")
    rule_key = str(required.get("target_key") or "")
    candidates = [
        item
        for item in tool_history
        if item.get("kind") == "business_rule_application"
        and str(item.get("semantic_entry_id") or "") == semantic_entry_id
        and str(item.get("definition_hash") or "") == definition_hash
        and str(item.get("rule_key") or "") == rule_key
        and _is_ancestor(
            tool_history,
            ancestor=str(item.get("result_name") or ""),
            descendant=final_result,
        )
    ]
    if not candidates:
        raise CorrectionCompletionError("这条修正尚未真正应用到最终结果")
    application = candidates[-1]
    application_result = str(application.get("result_name") or "")
    application_index = _last_index(tool_history, lambda item: item is application)
    validation_index = _last_index(
        tool_history,
        lambda item: (
            item.get("kind") == "validation"
            and str(item.get("result_name") or "") == final_result
            and bool(item.get("result_hash"))
        ),
    )
    if validation_index is None or (
        application_index is not None and validation_index <= application_index
    ):
        raise CorrectionCompletionError("最终结果需要在应用修正后重新核对")

    checks = [
        "current_definition_applied",
        "application_reaches_final_result",
        "final_result_revalidated",
    ]
    action_kind = str(application.get("action_kind") or "")
    final_metric_state: dict[str, Any] | None = None
    if action_kind in {"metric_column", "metric_formula"}:
        final_columns = {
            str(column)
            for column in (
                (tool_history[validation_index].get("profile") or {}).get("columns") or []
            )
        }
        if action_kind == "metric_formula":
            try:
                before_rows = int(application.get("before_rows"))
                after_rows = int(application.get("after_rows"))
                excluded_rows = int(application.get("excluded_rows"))
            except (TypeError, ValueError) as exc:
                raise CorrectionCompletionError("已修正的指标公式缺少完整执行证据") from exc
            if (
                before_rows != after_rows
                or excluded_rows != 0
                or not application.get("input_hash")
                or application.get("input_hash") == application.get("output_hash")
                or re.fullmatch(r"[0-9a-f]{64}", str(application.get("formula_hash") or "")) is None
            ):
                raise CorrectionCompletionError("已修正的指标公式没有形成可靠派生结果")
        final_metric_state = prove_metric_application_lineage(
            tool_history[: validation_index + 1],
            application,
            final_result=final_result,
            final_columns=final_columns,
        )
        if final_metric_state is None:
            if action_kind == "metric_formula" and any(
                item.get("kind") == "aggregate"
                and item.get("operation") in {"sum", "mean", "min", "max"}
                and str(item.get("required_metric_definition_hash") or "") == definition_hash
                and item.get("numeric_backend") != "decimal"
                and _is_ancestor(
                    tool_history,
                    ancestor=application_result,
                    descendant=str(item.get("result_name") or ""),
                )
                and _is_ancestor(
                    tool_history,
                    ancestor=str(item.get("result_name") or ""),
                    descendant=final_result,
                )
                for item in tool_history[: validation_index + 1]
            ):
                raise CorrectionCompletionError("已修正的指标公式没有通过 Decimal 安全汇总")
            raise CorrectionCompletionError("已修正的指标字段没有用于最终汇总")
        checks.append("required_metric_used_by_final_aggregate")

    return {
        **base,
        "status": "verified",
        "summary_code": "correction_verified",
        "action_kind": action_kind,
        "application_result_name": application_result,
        "source_result_name": application.get("source_result"),
        "source_refs": list(application.get("source_refs") or []),
        "before_rows": application.get("before_rows"),
        "after_rows": application.get("after_rows"),
        "excluded_rows": application.get("excluded_rows"),
        "input_hash": application.get("input_hash"),
        "result_hash": application.get("output_hash"),
        "formula_hash": application.get("formula_hash"),
        "metric_output_column": (
            final_metric_state.get("metric_output_column")
            if action_kind in {"metric_column", "metric_formula"}
            else None
        ),
        "checks": checks,
        "summary": "这条修正已应用到当前数据，并在最终结果中重新核对。",
    }
