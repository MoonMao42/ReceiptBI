"""Append-only version history for materialized project knowledge heads."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.tables import SemanticEntry, SemanticEntryRevision
from app.models.workspace import is_executable_semantic_definition

_UNSET = object()
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


@dataclass(frozen=True)
class SemanticRevisionConflictError(Exception):
    expected_revision_id: UUID | None
    active_revision_id: UUID | None

    def __str__(self) -> str:
        return "业务定义已被其他操作更新，请刷新后重试"


def semantic_entry_snapshot(entry: SemanticEntry) -> dict[str, Any]:
    """Copy the current materialized head into an immutable JSON snapshot."""

    snapshot = {field: deepcopy(getattr(entry, field)) for field in _SNAPSHOT_FIELDS}
    snapshot["scope_id"] = str(entry.scope_id) if entry.scope_id is not None else None
    return snapshot


def reset_semantic_execution_proof(entry: SemanticEntry) -> None:
    """A changed or restored meaning must earn fresh execution evidence."""

    if entry.is_active is False or entry.validity == "stale":
        entry.execution_state = "blocked"
        entry.execution_details = {
            "version": 1,
            "status": "blocked",
            "summary": "这项定义当前未启用，或数据字段已经变化，需要重新核对。",
        }
    elif is_executable_semantic_definition(entry.definition):
        entry.execution_state = "needs_validation"
        entry.execution_details = {
            "version": 1,
            "status": "needs_validation",
            "summary": "定义已更新，等待下一次真实调查验证。",
        }
    else:
        entry.execution_state = "definition_only"
        entry.execution_details = {
            "version": 1,
            "status": "definition_only",
            "summary": "已记住业务定义；当前没有可安全自动执行的方式。",
        }


async def append_semantic_revision(
    db: AsyncSession,
    entry: SemanticEntry,
    *,
    mutation_kind: str,
    actor_source: str,
    reason: str | None = None,
    source_correction_id: UUID | str | None = None,
    restored_from_revision_id: UUID | None = None,
    expected_active_revision_id: UUID | None | object = _UNSET,
) -> SemanticEntryRevision:
    """Append one immutable revision and advance the materialized head atomically."""

    if entry.id is None:
        db.add(entry)
        await db.flush()

    with db.no_autoflush:
        current = await db.execute(
            select(SemanticEntry.active_revision_id, SemanticEntry.revision_number)
            .where(SemanticEntry.id == entry.id)
            .with_for_update()
        )
    row = current.one_or_none()
    if row is None:
        raise ValueError("semantic entry is not persisted")
    database_active_revision_id, database_revision_number = row
    if (
        expected_active_revision_id is not _UNSET
        and database_active_revision_id != expected_active_revision_id
    ):
        raise SemanticRevisionConflictError(
            expected_revision_id=expected_active_revision_id,
            active_revision_id=database_active_revision_id,
        )

    revision = SemanticEntryRevision(
        project_id=entry.project_id,
        semantic_entry_id=entry.id,
        revision_number=int(database_revision_number or 0) + 1,
        parent_revision_id=database_active_revision_id,
        restored_from_revision_id=restored_from_revision_id,
        mutation_kind=mutation_kind[:40],
        actor_source=actor_source[:30],
        reason=reason,
        source_correction_id=(str(source_correction_id) if source_correction_id else None),
        snapshot=semantic_entry_snapshot(entry),
    )
    db.add(revision)
    try:
        await db.flush()
    except IntegrityError as exc:
        # PostgreSQL serializes this path with FOR UPDATE. SQLite removes that
        # clause, so the unique (entry, revision_number) constraint is the
        # final compare-and-swap guard under concurrent writers.
        raise SemanticRevisionConflictError(
            expected_revision_id=(
                expected_active_revision_id
                if expected_active_revision_id is not _UNSET
                else database_active_revision_id
            ),
            active_revision_id=database_active_revision_id,
        ) from exc
    except OperationalError as exc:
        # A competing SQLite writer may surface as SQLITE_BUSY before it can
        # reach the unique constraint. Treat that as a refreshable conflict,
        # while preserving unrelated database failures.
        if (
            db.bind is None
            or db.bind.dialect.name != "sqlite"
            or not any(
                marker in str(exc).casefold()
                for marker in ("database is locked", "database table is locked", "sqlite_busy")
            )
        ):
            raise
        raise SemanticRevisionConflictError(
            expected_revision_id=(
                expected_active_revision_id
                if expected_active_revision_id is not _UNSET
                else database_active_revision_id
            ),
            active_revision_id=database_active_revision_id,
        ) from exc
    entry.active_revision_id = revision.id
    entry.revision_number = revision.revision_number
    await db.flush()
    return revision


async def restore_semantic_revision(
    db: AsyncSession,
    entry: SemanticEntry,
    target: SemanticEntryRevision,
    *,
    expected_active_revision_id: UUID,
    reason: str | None = None,
    mutation_kind: str = "restored",
    actor_source: str = "user",
    source_correction_id: UUID | str | None = None,
) -> SemanticEntryRevision:
    """Restore history by creating a new head; the target stays immutable."""

    if target.semantic_entry_id != entry.id or target.project_id != entry.project_id:
        raise ValueError("revision does not belong to semantic entry")
    snapshot = deepcopy(target.snapshot or {})
    for field in _SNAPSHOT_FIELDS:
        if field == "key" or field not in snapshot:
            continue
        value = snapshot[field]
        if field == "scope_id" and value is not None:
            value = UUID(str(value))
        setattr(entry, field, value)
    entry.is_active = True
    reset_semantic_execution_proof(entry)
    entry.evidence = [
        *list(entry.evidence or []),
        {
            "kind": "semantic_revision_restore",
            "restored_from_revision_id": str(target.id),
            "reason": reason,
        },
    ]
    return await append_semantic_revision(
        db,
        entry,
        mutation_kind=mutation_kind,
        actor_source=actor_source,
        reason=reason or "恢复历史业务定义",
        source_correction_id=source_correction_id,
        restored_from_revision_id=target.id,
        expected_active_revision_id=expected_active_revision_id,
    )


async def deactivate_semantic_entry(
    db: AsyncSession,
    entry: SemanticEntry,
    *,
    expected_active_revision_id: UUID,
    source_correction_id: UUID | str,
) -> SemanticEntryRevision:
    """Represent removal as a tombstone revision without deleting history."""

    entry.is_active = False
    entry.validity = "stale"
    reset_semantic_execution_proof(entry)
    entry.evidence = [
        *list(entry.evidence or []),
        {
            "kind": "semantic_entry_deactivated",
            "correction_id": str(source_correction_id),
        },
    ]
    return await append_semantic_revision(
        db,
        entry,
        mutation_kind="correction_detached",
        actor_source="user",
        reason="撤销创建这项定义的项目修正",
        source_correction_id=source_correction_id,
        expected_active_revision_id=expected_active_revision_id,
    )


async def semantic_revision_or_none(
    db: AsyncSession,
    *,
    project_id: UUID,
    entry_id: UUID,
    revision_id: UUID,
) -> SemanticEntryRevision | None:
    result = await db.execute(
        select(SemanticEntryRevision).where(
            SemanticEntryRevision.id == revision_id,
            SemanticEntryRevision.project_id == project_id,
            SemanticEntryRevision.semantic_entry_id == entry_id,
        )
    )
    return result.scalar_one_or_none()
