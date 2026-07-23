"""bound accumulated inferred relationship candidates

Revision ID: 0014_candidate_hygiene
Revises: 0013_model_health
"""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0014_candidate_hygiene"
down_revision: str | None = "0013_model_health"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PER_COLUMN_CAP = 6
_PER_PROJECT_CAP = 80
_SNAPSHOT_FIELDS = (
    "key",
    "value",
    "entry_type",
    "state",
    "confidence",
    "definition",
    "validity",
    "execution_state",
    "execution_details",
    "evidence",
    "source",
    "is_active",
)


def _uuid() -> sa.types.TypeEngine:
    return postgresql.UUID(as_uuid=True)


semantic_entries = sa.table(
    "semantic_entries",
    sa.column("id", _uuid()),
    sa.column("project_id", _uuid()),
    sa.column("key", sa.String()),
    sa.column("value", sa.Text()),
    sa.column("entry_type", sa.String()),
    sa.column("state", sa.String()),
    sa.column("confidence", sa.Float()),
    sa.column("definition", sa.JSON()),
    sa.column("validity", sa.String()),
    sa.column("execution_state", sa.String()),
    sa.column("execution_details", sa.JSON()),
    sa.column("evidence", sa.JSON()),
    sa.column("source", sa.String()),
    sa.column("is_active", sa.Boolean()),
    sa.column("revision_number", sa.Integer()),
    sa.column("active_revision_id", _uuid()),
    sa.column("updated_at", sa.DateTime(timezone=True)),
)
semantic_entry_revisions = sa.table(
    "semantic_entry_revisions",
    sa.column("id", _uuid()),
    sa.column("project_id", _uuid()),
    sa.column("semantic_entry_id", _uuid()),
    sa.column("revision_number", sa.Integer()),
    sa.column("parent_revision_id", _uuid()),
    sa.column("restored_from_revision_id", _uuid()),
    sa.column("mutation_kind", sa.String()),
    sa.column("actor_source", sa.String()),
    sa.column("reason", sa.Text()),
    sa.column("source_correction_id", sa.String()),
    sa.column("snapshot", sa.JSON()),
    sa.column("created_at", sa.DateTime(timezone=True)),
)


def _id(value: object) -> str:
    return str(value or "")


def _pure_name_match(evidence: object) -> bool:
    return (
        bool(evidence)
        and isinstance(evidence, list)
        and all(
            isinstance(item, dict) and item.get("kind") == "matching_column_names"
            for item in evidence
        )
    )


def _canonical_column(value: object) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]", "", str(value or "").lower())
    aliases = {
        "门店id": "storeid",
        "门店编号": "storeid",
        "店铺id": "storeid",
        "shopid": "storeid",
        "订单id": "orderid",
        "订单编号": "orderid",
        "商品id": "productid",
        "产品id": "productid",
    }
    return aliases.get(normalized, normalized)


def _definition_endpoints(
    definition: object,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    if not isinstance(definition, dict):
        return None
    left = definition.get("left")
    right = definition.get("right")
    if not isinstance(left, dict) or not isinstance(right, dict):
        return None
    if not left.get("column") or not right.get("column"):
        return None
    return left, right


def _discovery_score(left: Mapping[str, Any], right: Mapping[str, Any]) -> float:
    score = 0.55
    left_column = str(left.get("column") or "")
    right_column = str(right.get("column") or "")
    if left_column.casefold() == right_column.casefold():
        score += 0.08
    if left_column.casefold().endswith("id") and right_column.casefold().endswith("id"):
        score += 0.04
    left_type = str(left.get("data_type") or "unknown").casefold()
    right_type = str(right.get("data_type") or "unknown").casefold()
    if left_type == right_type and left_type not in {"", "unknown"}:
        score += 0.04
    if left.get("table_or_view") != right.get("table_or_view"):
        score += 0.02
    if left.get("source_logical_name") != right.get("source_logical_name"):
        score += 0.02
    return round(min(score, 0.75), 6)


def _candidate_group(row: Mapping[str, Any], left: Mapping[str, Any]) -> str:
    evidence = row.get("evidence")
    if isinstance(evidence, list) and evidence and isinstance(evidence[0], dict):
        group = evidence[0].get("candidate_group")
        if isinstance(group, dict) and group.get("canonical_column"):
            return _canonical_column(group["canonical_column"])
    key_parts = str(row.get("key") or "").split(":")
    if len(key_parts) >= 3 and key_parts[0] == "relationship_candidate":
        from_key = _canonical_column(key_parts[1])
        if from_key and from_key != "fk":
            return from_key
    return _canonical_column(left.get("column"))


def _candidate_identity(
    row: Mapping[str, Any],
    left: Mapping[str, Any],
    right: Mapping[str, Any],
) -> str:
    return json.dumps(
        [left, right, {"key": str(row.get("key") or "")}],
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _snapshot(row: Mapping[str, Any], updates: Mapping[str, Any]) -> dict[str, Any]:
    return {field: updates.get(field, row.get(field)) for field in _SNAPSHOT_FIELDS}


def _append_revision(
    bind: sa.Connection,
    row: Mapping[str, Any],
    *,
    updates: dict[str, Any],
    mutation_kind: str,
    reason: str,
    revision_heads: Mapping[str, tuple[str, int]],
    revision_maxima: Mapping[str, int],
) -> None:
    entry_id = _id(row["id"])
    current_revision_number = int(row.get("revision_number") or 0)
    active_revision_id = _id(row.get("active_revision_id"))
    if revision_maxima.get(entry_id, 0) != current_revision_number:
        return
    if active_revision_id:
        active_head = revision_heads.get(active_revision_id)
        if active_head != (entry_id, current_revision_number):
            # Preserve a suspicious history chain instead of guessing a new head.
            return
    elif current_revision_number != 0:
        return

    next_revision_number = current_revision_number + 1
    next_revision_id = uuid4()
    now = datetime.now(UTC)
    bind.execute(
        semantic_entry_revisions.insert().values(
            id=next_revision_id,
            project_id=row["project_id"],
            semantic_entry_id=row["id"],
            revision_number=next_revision_number,
            parent_revision_id=row.get("active_revision_id"),
            restored_from_revision_id=None,
            mutation_kind=mutation_kind,
            actor_source="system",
            reason=reason,
            source_correction_id=None,
            snapshot=_snapshot(row, updates),
            created_at=now,
        )
    )
    bind.execute(
        semantic_entries.update()
        .where(semantic_entries.c.id == row["id"])
        .values(
            **updates,
            active_revision_id=next_revision_id,
            revision_number=next_revision_number,
            updated_at=now,
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    user_touched_ids = {
        _id(value)
        for value in bind.execute(
            sa.select(semantic_entry_revisions.c.semantic_entry_id).where(
                sa.or_(
                    semantic_entry_revisions.c.actor_source == "user",
                    semantic_entry_revisions.c.mutation_kind == "created",
                )
            )
        ).scalars()
    }
    revision_rows = list(
        bind.execute(
            sa.select(
                semantic_entry_revisions.c.id,
                semantic_entry_revisions.c.semantic_entry_id,
                semantic_entry_revisions.c.revision_number,
            )
        ).mappings()
    )
    revision_heads = {
        _id(row["id"]): (_id(row["semantic_entry_id"]), int(row["revision_number"]))
        for row in revision_rows
    }
    revision_maxima: dict[str, int] = defaultdict(int)
    for row in revision_rows:
        entry_id = _id(row["semantic_entry_id"])
        revision_maxima[entry_id] = max(
            revision_maxima[entry_id],
            int(row["revision_number"]),
        )
    rows = list(
        bind.execute(
            sa.select(semantic_entries).where(
                semantic_entries.c.entry_type == "relationship",
                semantic_entries.c.state == "candidate",
                semantic_entries.c.source == "inferred",
                semantic_entries.c.is_active.is_(True),
            )
        ).mappings()
    )

    by_project: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if _id(row["id"]) in user_touched_ids or not _pure_name_match(row["evidence"]):
            continue
        endpoints = _definition_endpoints(row["definition"])
        if endpoints is None:
            # Historical malformed heads are intentionally left for manual review.
            continue
        left, right = endpoints
        group = _candidate_group(row, left)
        if not group:
            continue
        by_project[_id(row["project_id"])].append(
            {
                "row": row,
                "group": group,
                "score": _discovery_score(left, right),
                "identity": _candidate_identity(row, left, right),
            }
        )

    retained_ids: set[str] = set()
    eligible: list[dict[str, Any]] = []
    for candidates in by_project.values():
        by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for candidate in candidates:
            by_group[candidate["group"]].append(candidate)
        per_column_retained: list[dict[str, Any]] = []
        for group_candidates in by_group.values():
            group_candidates.sort(key=lambda item: (-item["score"], item["identity"]))
            per_column_retained.extend(group_candidates[:_PER_COLUMN_CAP])
        per_column_retained.sort(key=lambda item: (-item["score"], item["group"], item["identity"]))
        retained_ids.update(
            _id(item["row"]["id"]) for item in per_column_retained[:_PER_PROJECT_CAP]
        )
        eligible.extend(candidates)

    for candidate in eligible:
        row = candidate["row"]
        entry_id = _id(row["id"])
        if entry_id not in retained_ids:
            _append_revision(
                bind,
                row,
                updates={
                    "is_active": False,
                    "validity": "stale",
                    "execution_state": "blocked",
                    "execution_details": {
                        "version": 1,
                        "status": "blocked",
                        "summary": "这项定义当前未启用，或数据字段已经变化，需要重新核对。",
                    },
                },
                mutation_kind="candidate_pruned",
                reason="迁移时收敛历史累计的低证据关联候选",
                revision_heads=revision_heads,
                revision_maxima=revision_maxima,
            )
            continue
        current_confidence = float(row.get("confidence") or 0)
        score = float(candidate["score"])
        if math.isclose(current_confidence, 0.55, abs_tol=1e-9) and not math.isclose(
            current_confidence,
            score,
            abs_tol=1e-9,
        ):
            _append_revision(
                bind,
                row,
                updates={"confidence": score},
                mutation_kind="candidate_rescored",
                reason="按当前候选定义重算发现可信度",
                revision_heads=revision_heads,
                revision_maxima=revision_maxima,
            )


def downgrade() -> None:
    # The cleanup is append-only business history. Reversing it automatically
    # could overwrite later user governance, so downgrade intentionally keeps it.
    pass
