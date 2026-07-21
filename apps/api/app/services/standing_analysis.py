"""Deterministic domain logic for project-level standing analyses.

This module deliberately accepts only validated, complete numeric result tables. It does not
extract metrics from report prose and does not use a model to decide whether a change matters.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from app.models.workspace import (
    StandingChangeBrief,
    StandingDriverDelta,
    StandingKeyDelta,
    StandingMaterialityPolicy,
    StandingMaterialityRule,
    StandingMetricDelta,
    StandingScalar,
    ValidatedResultSnapshot,
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_RESULT_ROWS = 20000
_MAX_CELL_TEXT = 10000
_MAX_SNAPSHOT_CELLS = 250000
_MAX_NUMERIC_CELLS = 50000
_MAX_SNAPSHOT_TEXT_BYTES = 16 * 1024 * 1024


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("standing analysis inputs must be canonical JSON values") from exc


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _bounded_text(value: str, *, name: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise ValueError(f"{name} must be non-empty and at most {maximum} characters")
    return normalized


def _canonical_text_mapping(
    values: Mapping[str, str],
    *,
    name: str,
    minimum: int,
    maximum: int,
    value_maximum: int,
) -> dict[str, str]:
    if not isinstance(values, Mapping):
        raise ValueError(f"{name} must be a mapping")
    if not minimum <= len(values) <= maximum:
        raise ValueError(f"{name} must contain between {minimum} and {maximum} entries")
    normalized: dict[str, str] = {}
    for raw_key, raw_value in values.items():
        key = _bounded_text(raw_key, name=f"{name} key", maximum=255)
        value = _bounded_text(raw_value, name=f"{name} value", maximum=value_maximum)
        if key in normalized:
            raise ValueError(f"{name} contains duplicate keys after normalization")
        normalized[key] = value
    return dict(sorted(normalized.items()))


def canonical_input_token(
    *,
    standing_analysis_id: str,
    playbook_id: str,
    playbook_shape_hash: str,
    source_fingerprints: Mapping[str, str],
    semantic_versions: Mapping[str, str] | None = None,
    recipe_fingerprints: Mapping[str, str] | None = None,
) -> str:
    """Return the idempotency token for one exact standing-analysis input state.

    Mapping order is intentionally irrelevant. The token binds the standing analysis, reusable
    playbook identity and shape, current source versions, confirmed semantic versions, and
    sanitation recipes.
    """

    if not isinstance(playbook_shape_hash, str) or not _SHA256_RE.fullmatch(playbook_shape_hash):
        raise ValueError("playbook_shape_hash must be a lowercase SHA-256 digest")

    payload = {
        "version": 1,
        "standing_analysis_id": _bounded_text(
            standing_analysis_id,
            name="standing_analysis_id",
            maximum=80,
        ),
        "playbook_id": _bounded_text(playbook_id, name="playbook_id", maximum=80),
        "playbook_shape_hash": playbook_shape_hash,
        "source_fingerprints": _canonical_text_mapping(
            source_fingerprints,
            name="source_fingerprints",
            minimum=1,
            maximum=100,
            value_maximum=128,
        ),
        "semantic_versions": _canonical_text_mapping(
            semantic_versions or {},
            name="semantic_versions",
            minimum=0,
            maximum=100,
            value_maximum=256,
        ),
        "recipe_fingerprints": _canonical_text_mapping(
            recipe_fingerprints or {},
            name="recipe_fingerprints",
            minimum=0,
            maximum=100,
            value_maximum=128,
        ),
    }
    return _sha256(payload)


def _canonical_columns(values: Sequence[str], *, name: str, maximum: int) -> list[str]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ValueError(f"{name} must be a sequence of column names")
    normalized = [_bounded_text(value, name=name, maximum=255) for value in values]
    if not normalized or len(normalized) > maximum:
        raise ValueError(f"{name} must contain between 1 and {maximum} columns")
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{name} must not contain duplicate columns")
    return sorted(normalized)


def _canonical_scalar(value: object) -> StandingScalar:
    if value is None or isinstance(value, (str, bool, int)):
        if isinstance(value, str) and len(value) > _MAX_CELL_TEXT:
            raise ValueError(f"text result cells cannot exceed {_MAX_CELL_TEXT} characters")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("result cells cannot contain NaN or infinity")
        return 0.0 if value == 0 else value
    raise ValueError("result cells must be JSON scalar values")


def _shape_hash(
    *,
    columns: Sequence[str],
    key_columns: Sequence[str],
    numeric_columns: Sequence[str],
) -> str:
    return _sha256(
        {
            "version": 1,
            "columns": sorted(columns),
            "key_columns": sorted(key_columns),
            "numeric_columns": sorted(numeric_columns),
        }
    )


def build_validated_result_snapshot(
    *,
    analysis_run_id: UUID,
    result_name: str,
    input_token: str,
    rows: Sequence[Mapping[str, object]],
    key_columns: Sequence[str],
    numeric_columns: Sequence[str],
    truncated: bool,
    expected_columns: Sequence[str] | None = None,
    expected_shape_hash: str | None = None,
) -> ValidatedResultSnapshot:
    """Build a complete, uniquely keyed, numeric result snapshot or reject it.

    `expected_shape_hash` is the baseline contract gate. Supplying it makes shape drift an error
    before a candidate snapshot can be compared with or replace a trusted baseline.
    """

    if not isinstance(analysis_run_id, UUID):
        raise ValueError("analysis_run_id must be a UUID")
    result_name = _bounded_text(result_name, name="result_name", maximum=255)
    if not isinstance(input_token, str) or not _SHA256_RE.fullmatch(input_token):
        raise ValueError("input_token must be a lowercase SHA-256 digest")
    if truncated:
        raise ValueError("standing analyses require a complete, non-truncated result")
    if isinstance(rows, (str, bytes)) or not isinstance(rows, Sequence):
        raise ValueError("rows must be a sequence of mappings")
    if len(rows) > _MAX_RESULT_ROWS:
        raise ValueError(f"standing analysis results cannot exceed {_MAX_RESULT_ROWS} rows")

    keys = _canonical_columns(key_columns, name="key_columns", maximum=20)
    metrics = _canonical_columns(numeric_columns, name="numeric_columns", maximum=100)
    if set(keys) & set(metrics):
        raise ValueError("key_columns and numeric_columns must not overlap")
    if len(rows) * len(metrics) > _MAX_NUMERIC_CELLS:
        raise ValueError("standing analysis result has too many numeric cells to compare safely")

    if expected_columns is None:
        if not rows:
            raise ValueError("expected_columns are required for an empty result")
        first_row = rows[0]
        if not isinstance(first_row, Mapping):
            raise ValueError("every result row must be a mapping")
        columns = _canonical_columns(list(first_row), name="columns", maximum=500)
    else:
        columns = _canonical_columns(expected_columns, name="expected_columns", maximum=500)
    if not set(keys + metrics).issubset(columns):
        raise ValueError("all key and numeric columns must exist in the result shape")
    if len(rows) * len(columns) > _MAX_SNAPSHOT_CELLS:
        raise ValueError("standing analysis result is too large to snapshot safely")

    canonical_rows: list[dict[str, StandingScalar]] = []
    expected_column_set = set(columns)
    text_bytes = 0
    for raw_row in rows:
        if not isinstance(raw_row, Mapping):
            raise ValueError("every result row must be a mapping")
        if set(raw_row) != expected_column_set:
            raise ValueError("result shape drift: every row must match expected_columns exactly")
        row = {column: _canonical_scalar(raw_row[column]) for column in columns}
        text_bytes += sum(
            len(value.encode("utf-8")) for value in row.values() if isinstance(value, str)
        )
        if text_bytes > _MAX_SNAPSHOT_TEXT_BYTES:
            raise ValueError("standing analysis result text is too large to snapshot safely")
        canonical_rows.append(row)

    def row_sort_key(row: Mapping[str, StandingScalar]) -> str:
        return _canonical_json({column: row[column] for column in keys})

    canonical_rows.sort(key=row_sort_key)
    shape_hash = _shape_hash(columns=columns, key_columns=keys, numeric_columns=metrics)
    if expected_shape_hash is not None:
        if not isinstance(expected_shape_hash, str) or not _SHA256_RE.fullmatch(
            expected_shape_hash
        ):
            raise ValueError("expected_shape_hash must be a lowercase SHA-256 digest")
        if expected_shape_hash != shape_hash:
            raise ValueError(
                "result shape drift: current shape does not match the trusted baseline"
            )

    snapshot_payload = {
        "schema_version": 1,
        "analysis_run_id": str(analysis_run_id),
        "result_name": result_name,
        "input_token": input_token,
        "shape_hash": shape_hash,
        "columns": columns,
        "key_columns": keys,
        "numeric_columns": metrics,
        "row_count": len(canonical_rows),
        "truncated": False,
        "rows": canonical_rows,
    }
    return ValidatedResultSnapshot(
        snapshot_id=f"snap_{_sha256(snapshot_payload)[:20]}",
        **snapshot_payload,
    )


def _metric_delta(metric: str, before: float, after: float) -> StandingMetricDelta:
    delta = after - before
    if delta == 0:
        delta = 0.0
    baseline_zero = before == 0
    if baseline_zero:
        percent_change = 0.0 if after == 0 else None
    else:
        percent_change = delta / abs(before)
    return StandingMetricDelta(
        metric=metric,
        before=before,
        after=after,
        delta=delta,
        absolute_change=abs(delta),
        percent_change=percent_change,
        baseline_zero=baseline_zero,
    )


def _index_rows(
    snapshot: ValidatedResultSnapshot,
) -> dict[tuple[StandingScalar, ...], dict[str, StandingScalar]]:
    return {tuple(row[column] for column in snapshot.key_columns): row for row in snapshot.rows}


def _rule_matches(
    rule: StandingMaterialityRule,
    change: StandingMetricDelta,
    *,
    scope: str,
) -> bool:
    if rule.metric != change.metric or rule.scope not in {scope, "either"}:
        return False
    if change.delta == 0:
        return False
    if rule.direction == "increase" and change.delta <= 0:
        return False
    if rule.direction == "decrease" and change.delta >= 0:
        return False
    if rule.change_kind == "absolute":
        return change.absolute_change >= rule.threshold
    return change.percent_change is not None and abs(change.percent_change) >= rule.threshold


def compare_validated_result_snapshots(
    baseline: ValidatedResultSnapshot,
    current: ValidatedResultSnapshot,
    policy: StandingMaterialityPolicy,
) -> StandingChangeBrief:
    """Deterministically compare two compatible validated result tables.

    Overall metric totals and every keyed numeric cell are both compared. Materiality is an
    explicit any-match over typed rules; top drivers use a stable absolute-change ordering.
    """

    if baseline.shape_hash != current.shape_hash:
        raise ValueError("result shape drift: snapshots cannot be compared")
    if baseline.result_name != current.result_name:
        raise ValueError("snapshots must refer to the same validated result")
    if (
        baseline.columns != current.columns
        or baseline.key_columns != current.key_columns
        or baseline.numeric_columns != current.numeric_columns
    ):
        raise ValueError("snapshot contracts differ despite sharing a shape hash")

    baseline_index = _index_rows(baseline)
    current_index = _index_rows(current)
    metrics = baseline.numeric_columns

    overall = [
        _metric_delta(
            metric,
            math.fsum(float(row[metric]) for row in baseline.rows),
            math.fsum(float(row[metric]) for row in current.rows),
        )
        for metric in metrics
    ]

    key_names = baseline.key_columns
    all_keys = set(baseline_index) | set(current_index)
    sorted_keys = sorted(
        all_keys,
        key=lambda values: _canonical_json(dict(zip(key_names, values, strict=True))),
    )
    by_key: list[StandingKeyDelta] = []
    for key_values in sorted_keys:
        baseline_row = baseline_index.get(key_values)
        current_row = current_index.get(key_values)
        changes = [
            _metric_delta(
                metric,
                float(baseline_row[metric]) if baseline_row is not None else 0.0,
                float(current_row[metric]) if current_row is not None else 0.0,
            )
            for metric in metrics
        ]
        changes = [change for change in changes if change.delta != 0]
        if not changes:
            continue
        if baseline_row is None:
            row_state = "added"
        elif current_row is None:
            row_state = "removed"
        else:
            row_state = "changed"
        by_key.append(
            StandingKeyDelta(
                key=dict(zip(key_names, key_values, strict=True)),
                row_state=row_state,
                changes=changes,
            )
        )

    matched_rule_ids = {
        rule.id
        for rule in policy.rules
        if any(_rule_matches(rule, change, scope="overall") for change in overall)
        or any(
            _rule_matches(rule, change, scope="by_key")
            for keyed_delta in by_key
            for change in keyed_delta.changes
        )
    }

    driver_candidates = [
        (keyed_delta.key, keyed_delta.row_state, change)
        for keyed_delta in by_key
        for change in keyed_delta.changes
    ]
    driver_candidates.sort(
        key=lambda item: (
            -item[2].absolute_change,
            item[2].metric,
            _canonical_json(item[0]),
        )
    )
    top_drivers = [
        StandingDriverDelta(
            rank=rank,
            key=key,
            row_state=row_state,
            change=change,
        )
        for rank, (key, row_state, change) in enumerate(
            driver_candidates[: policy.top_driver_limit],
            start=1,
        )
    ]

    brief_payload = {
        "schema_version": 1,
        "baseline_snapshot_id": baseline.snapshot_id,
        "current_snapshot_id": current.snapshot_id,
        "current_input_token": current.input_token,
        "shape_hash": current.shape_hash,
        "status": "material_change" if matched_rule_ids else "no_material_change",
        "matched_rule_ids": sorted(matched_rule_ids),
        "overall": [change.model_dump(mode="json") for change in overall],
        "by_key": [change.model_dump(mode="json") for change in by_key],
        "top_drivers": [driver.model_dump(mode="json") for driver in top_drivers],
    }
    return StandingChangeBrief(
        brief_id=f"brief_{_sha256(brief_payload)[:20]}",
        **brief_payload,
    )


# Short aliases for callers that already operate inside the standing-analysis domain.
build_validated_snapshot = build_validated_result_snapshot
diff_validated_snapshots = compare_validated_result_snapshots


__all__ = [
    "build_validated_result_snapshot",
    "build_validated_snapshot",
    "canonical_input_token",
    "compare_validated_result_snapshots",
    "diff_validated_snapshots",
]
