"""Column-level proof that a confirmed metric survives into the final result."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

_METRIC_OPERATIONS = {"sum", "mean", "min", "max"}


def prove_metric_application_lineage(
    tool_history: list[dict[str, Any]],
    application: dict[str, Any],
    *,
    final_result: str,
    final_columns: Iterable[str] | None = None,
) -> dict[str, Any] | None:
    """Return the final metric state only when every producer preserves it.

    Result ancestry alone is insufficient: a later ``count`` can remain downstream
    of a valid Decimal sum while replacing the metric value.  This interpreter
    replays only system-authored column metadata and drops the proof at the first
    destructive or inconsistent producer.
    """

    application_index = next(
        (index for index, item in enumerate(tool_history) if item is application),
        None,
    )
    application_result = str(application.get("result_name") or "")
    base_column = str(application.get("column") or "")
    definition_hash = str(application.get("definition_hash") or "")
    action_kind = str(application.get("action_kind") or "")
    if (
        application_index is None
        or not application_result
        or not base_column
        or not definition_hash
        or action_kind not in {"metric_column", "metric_formula"}
    ):
        return None

    states: dict[str, dict[str, Any]] = {
        application_result: {
            "base_column": base_column,
            "metric_output_column": base_column,
            "definition_hash": definition_hash,
            "action_kind": action_kind,
            "metric_policy_satisfied": False,
            "result_name": application_result,
        }
    }

    for step in tool_history[application_index + 1 :]:
        result_name = str(step.get("result_name") or "")
        if not result_name:
            continue
        kind = str(step.get("kind") or "")
        if kind == "validation" or (
            kind == "python"
            and [str(value) for value in step.get("input_results") or []] == [result_name]
        ):
            continue
        if kind == "aggregate":
            source_state = states.get(str(step.get("source_result") or ""))
            if source_state is None:
                continue
            input_column = str(source_state["metric_output_column"])
            output_column = str(step.get("output_column") or "")
            valid = (
                step.get("operation") in _METRIC_OPERATIONS
                and str(step.get("value_column") or "") == input_column
                and str(step.get("metric_input_column") or "") == input_column
                and output_column
                and str(step.get("metric_output_column") or "") == output_column
                and bool(step.get("metric_policy_satisfied"))
                and str(step.get("required_metric_column") or "") == base_column
                and str(step.get("required_metric_definition_hash") or "")
                == definition_hash
            )
            if action_kind == "metric_formula":
                valid = valid and (
                    step.get("numeric_backend") == "decimal"
                    and isinstance(step.get("decimal_aggregate_evidence"), dict)
                    and (step.get("decimal_aggregate_evidence") or {}).get("kind")
                    == "decimal_aggregate"
                )
            if valid:
                states[result_name] = {
                    **source_state,
                    "metric_output_column": output_column,
                    "metric_policy_satisfied": True,
                    "result_name": result_name,
                }
            else:
                states.pop(result_name, None)
            continue

        if kind == "join":
            dependency_states = [
                states[dependency]
                for dependency in (
                    str(step.get("left_result") or ""),
                    str(step.get("right_result") or ""),
                )
                if dependency in states
            ]
            if len(dependency_states) != 1:
                if dependency_states:
                    states.pop(result_name, None)
                continue
            source_state = dependency_states[0]
            valid = (
                str(step.get("required_metric_column") or "") == base_column
                and str(step.get("required_metric_definition_hash") or "")
                == definition_hash
                and str(step.get("metric_output_column") or "")
                == str(source_state["metric_output_column"])
                and bool(step.get("metric_policy_satisfied"))
                == bool(source_state["metric_policy_satisfied"])
            )
            if valid:
                states[result_name] = {**source_state, "result_name": result_name}
            else:
                states.pop(result_name, None)
            continue

        if kind == "business_rule_application":
            source_state = states.get(str(step.get("source_result") or ""))
            if source_state is None:
                continue
            valid = (
                step.get("action_kind") in {"value_filter", "identity"}
                and str(step.get("required_metric_column") or "") == base_column
                and str(step.get("required_metric_definition_hash") or "")
                == definition_hash
                and str(step.get("metric_output_column") or "")
                == str(source_state["metric_output_column"])
                and bool(step.get("metric_policy_satisfied"))
                == bool(source_state["metric_policy_satisfied"])
            )
            if valid:
                states[result_name] = {**source_state, "result_name": result_name}
            else:
                states.pop(result_name, None)
            continue

        dependencies = {
            str(step.get(key) or "")
            for key in ("source_result", "left_result", "right_result")
            if str(step.get(key) or "")
        }
        if dependencies.intersection(states):
            states.pop(result_name, None)
        elif result_name in states:
            # A fresh query or other producer reused the same alias and replaced
            # the retained rows without carrying the metric contract.
            states.pop(result_name, None)

    final_state = states.get(final_result)
    if final_state is None or not final_state.get("metric_policy_satisfied"):
        return None
    if final_columns is not None and str(final_state["metric_output_column"]) not in {
        str(column) for column in final_columns
    }:
        return None
    return dict(final_state)
