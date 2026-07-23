"""retire obsolete name-only semantic candidates

Revision ID: 0019_retire_legacy_candidates
Revises: 0018_semantic_scope_nodes
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0019_retire_legacy_candidates"
down_revision: str | None = "0018_semantic_scope_nodes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SNAPSHOT_FIELDS = (
    "scope_id",
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
_RELATIONSHIP_USER_GOVERNANCE_MUTATIONS = frozenset(
    {
        "created",
        "user_upsert",
        "user_updated",
        "candidate_restored",
        "explicit_confirmation",
        "verified_candidate_remembered",
    }
)


def _uuid() -> sa.types.TypeEngine:
    return postgresql.UUID(as_uuid=True)


semantic_entries = sa.table(
    "semantic_entries",
    sa.column("id", _uuid()),
    sa.column("project_id", _uuid()),
    sa.column("scope_id", _uuid()),
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


def _is_legacy_column_candidate(row: Mapping[str, Any]) -> bool:
    key = str(row.get("key") or "")
    if not (key.startswith("metric_candidate:") or key.startswith("grain:")):
        return False
    definition = row.get("definition")
    return definition is None or (
        isinstance(definition, dict)
        and definition.get("kind") in {"column_metric", "grain_key"}
    )


def _is_legacy_name_match_relationship(row: Mapping[str, Any]) -> bool:
    evidence = row.get("evidence")
    if not isinstance(evidence, list):
        return False
    kinds = {
        str(item.get("kind") or "")
        for item in evidence
        if isinstance(item, dict)
    }
    return "matching_column_names" in kinds and "declared_foreign_key" not in kinds


def _snapshot(row: Mapping[str, Any], updates: Mapping[str, Any]) -> dict[str, Any]:
    snapshot = {
        field: updates.get(field, row.get(field))
        for field in _SNAPSHOT_FIELDS
    }
    if snapshot.get("scope_id") is not None:
        snapshot["scope_id"] = str(snapshot["scope_id"])
    return snapshot


def _retire_candidate(
    bind: sa.Connection,
    row: Mapping[str, Any],
    *,
    revision_heads: Mapping[str, tuple[str, int]],
    revision_maxima: Mapping[str, int],
    mutation_kind: str,
    reason: str,
    evidence_kind: str,
    evidence_reason: str,
    code: str,
    summary: str,
) -> bool:
    entry_id = _id(row["id"])
    current_revision_number = int(row.get("revision_number") or 0)
    active_revision_id = _id(row.get("active_revision_id"))
    if revision_maxima.get(entry_id, 0) != current_revision_number:
        return False
    if active_revision_id:
        if revision_heads.get(active_revision_id) != (
            entry_id,
            current_revision_number,
        ):
            return False
    elif current_revision_number != 0:
        return False

    evidence = [
        *list(row.get("evidence") or []),
        {"kind": evidence_kind, "reason": evidence_reason},
    ]
    updates = {
        "is_active": False,
        "validity": "stale",
        "execution_state": "blocked",
        "execution_details": {
            "version": 1,
            "status": "blocked",
            "code": code,
            "summary": summary,
        },
        "evidence": evidence,
    }
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
    return True


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
    relationship_user_governed_ids = {
        _id(value)
        for value in bind.execute(
            sa.select(semantic_entry_revisions.c.semantic_entry_id).where(
                semantic_entry_revisions.c.mutation_kind.in_(
                    _RELATIONSHIP_USER_GOVERNANCE_MUTATIONS
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

    candidates = list(
        bind.execute(
            sa.select(semantic_entries).where(
                semantic_entries.c.state == "candidate",
                semantic_entries.c.source == "inferred",
                semantic_entries.c.is_active.is_(True),
                semantic_entries.c.entry_type.in_(("metric", "dimension")),
                sa.or_(
                    semantic_entries.c.key.like("metric_candidate:%"),
                    semantic_entries.c.key.like("grain:%"),
                ),
            )
        ).mappings()
    )
    for row in candidates:
        entry_id = _id(row["id"])
        if entry_id in user_touched_ids or not _is_legacy_column_candidate(row):
            continue
        _retire_candidate(
            bind,
            row,
            revision_heads=revision_heads,
            revision_maxima=revision_maxima,
            mutation_kind="legacy_candidate_retired",
            reason="淘汰旧版仅凭字段名生成的列候选",
            evidence_kind="legacy_preflight_candidate_retired",
            evidence_reason="旧版候选没有类型化定义，已由表级语义推荐流程取代",
            code="legacy_preflight_candidate_retired",
            summary="旧版候选已停用；如仍需要，请从对应数据表重新生成推荐。",
        )

    relationship_candidates = list(
        bind.execute(
            sa.select(semantic_entries).where(
                semantic_entries.c.state == "candidate",
                semantic_entries.c.is_active.is_(True),
                semantic_entries.c.entry_type == "relationship",
                sa.or_(
                    semantic_entries.c.execution_state.is_(None),
                    semantic_entries.c.execution_state != "verified",
                ),
            )
        ).mappings()
    )
    for row in relationship_candidates:
        entry_id = _id(row["id"])
        if (
            entry_id in relationship_user_governed_ids
            or not _is_legacy_name_match_relationship(row)
        ):
            continue
        _retire_candidate(
            bind,
            row,
            revision_heads=revision_heads,
            revision_maxima=revision_maxima,
            mutation_kind="legacy_relationship_retired",
            reason="淘汰旧版仅凭同名字段生成的数据关联候选",
            evidence_kind="legacy_name_match_relationship_retired",
            evidence_reason="同名字段不足以证明数据表可以安全关联",
            code="legacy_name_match_relationship_retired",
            summary="旧版同名字段关联已停用；请从有明确约束或验证依据的建议重新确认。",
        )


def downgrade() -> None:
    # Retirement is append-only governance history. Restoring it automatically
    # could overwrite later user decisions, so downgrade intentionally keeps it.
    pass
