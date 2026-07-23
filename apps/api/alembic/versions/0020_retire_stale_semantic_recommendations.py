"""retire untouched recommendations created before localized governance

Revision ID: 0020_retire_stale_recos
Revises: 0019_retire_legacy_candidates
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

revision: str = "0020_retire_stale_recos"
down_revision: str | None = "0019_retire_legacy_candidates"
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
_USER_GOVERNANCE_MUTATIONS = frozenset(
    {
        "created",
        "user_upsert",
        "user_updated",
        "candidate_restored",
        "explicit_confirmation",
        "verified_candidate_remembered",
        "human_attested",
        "validation_queued",
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


def _evidence_items(row: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    evidence = row.get("evidence")
    if not isinstance(evidence, list):
        return []
    return [item for item in evidence if isinstance(item, Mapping)]


def _is_old_preflight_recommendation(row: Mapping[str, Any]) -> bool:
    if not str(row.get("key") or "").startswith("semantic_recommendation:"):
        return False
    evidence = _evidence_items(row)
    if any(item.get("kind") == "model_presentation_enhancement" for item in evidence):
        return False
    return any(
        (
            item.get("kind") == "semantic_recommendation_batch"
            and item.get("generated_by") == "preflight"
        )
        or str(item.get("generated_by") or "").startswith("deterministic_")
        for item in evidence
    )


def _snapshot(row: Mapping[str, Any], updates: Mapping[str, Any]) -> dict[str, Any]:
    snapshot = {field: updates.get(field, row.get(field)) for field in _SNAPSHOT_FIELDS}
    if snapshot.get("scope_id") is not None:
        snapshot["scope_id"] = str(snapshot["scope_id"])
    return snapshot


def upgrade() -> None:
    bind = op.get_bind()
    protected_entry_ids = {
        _id(row["semantic_entry_id"])
        for row in bind.execute(
            sa.select(
                semantic_entry_revisions.c.semantic_entry_id,
                semantic_entry_revisions.c.actor_source,
                semantic_entry_revisions.c.mutation_kind,
            )
        ).mappings()
        if row["actor_source"] == "user" or row["mutation_kind"] in _USER_GOVERNANCE_MUTATIONS
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
        revision_maxima[entry_id] = max(revision_maxima[entry_id], int(row["revision_number"]))

    candidates = list(
        bind.execute(
            sa.select(semantic_entries).where(
                semantic_entries.c.state == "candidate",
                semantic_entries.c.source == "inferred",
                semantic_entries.c.is_active.is_(True),
                sa.or_(
                    semantic_entries.c.execution_state.is_(None),
                    semantic_entries.c.execution_state != "verified",
                ),
                semantic_entries.c.key.like("semantic_recommendation:%"),
            )
        ).mappings()
    )
    for row in candidates:
        entry_id = _id(row["id"])
        current_revision_number = int(row.get("revision_number") or 0)
        active_revision_id = _id(row.get("active_revision_id"))
        if entry_id in protected_entry_ids or not _is_old_preflight_recommendation(row):
            continue
        if revision_maxima.get(entry_id, 0) != current_revision_number:
            continue
        if active_revision_id:
            if revision_heads.get(active_revision_id) != (
                entry_id,
                current_revision_number,
            ):
                continue
        elif current_revision_number != 0:
            continue

        evidence = [
            *list(row.get("evidence") or []),
            {
                "kind": "stale_recommendation_retired",
                "reason": "旧建议缺少新的中文业务命名与范围上下文",
            },
        ]
        updates = {
            "is_active": False,
            "validity": "stale",
            "execution_state": "blocked",
            "execution_details": {
                "version": 1,
                "status": "blocked",
                "code": "stale_recommendation_retired",
                "summary": "旧建议已停用；需要时请从对应数据范围重新发现。",
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
                mutation_kind="stale_recommendation_retired",
                actor_source="system",
                reason="停用旧版未治理的语义建议",
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


def downgrade() -> None:
    # Retirement is append-only governance history. Automatic restoration could
    # overwrite later user decisions, so downgrade intentionally keeps it.
    pass
