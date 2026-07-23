"""Append-only history for reversible project sanitation recipes."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.tables import SanitationRecipeRecord, SanitationRecipeRevisionRecord
from app.services.sanitation_contract import canonicalize_sanitation_operations

SanitationRevisionState = Literal["candidate", "confirmed", "reverted"]
_VALID_STATES = frozenset({"candidate", "confirmed", "reverted"})


@dataclass(frozen=True)
class SanitationRevisionConflictError(Exception):
    expected_revision_id: UUID | None
    active_revision_id: UUID | None

    def __str__(self) -> str:
        return "清洗方法已被其他操作更新，请刷新后重试"


class SanitationRevisionIntegrityError(RuntimeError):
    """The materialized recipe head and immutable history disagree."""


def sanitation_fingerprint_contract(fingerprint: str | None) -> dict[str, Any]:
    """Build the minimal durable contract used when only a fingerprint is known."""

    return {"version": 1, "fingerprint": fingerprint}


def _state_for_materialized_recipe(recipe: SanitationRecipeRecord) -> SanitationRevisionState:
    if recipe.status == "reverted":
        return "reverted"
    if recipe.status in {"needs_attention", "candidate"}:
        return "candidate"
    return "confirmed"


def _fingerprint_from_contract(contract: dict[str, Any], *, label: str) -> str | None:
    value = contract.get("fingerprint")
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError(f"{label} fingerprint must be a string of at most 64 characters")
    return value


def _is_sqlite_busy(db: AsyncSession, exc: OperationalError) -> bool:
    return (
        db.bind is not None
        and db.bind.dialect.name == "sqlite"
        and any(
            marker in str(exc).casefold()
            for marker in ("database is locked", "database table is locked", "sqlite_busy")
        )
    )


async def ensure_sanitation_revision_head(
    db: AsyncSession,
    recipe: SanitationRecipeRecord,
) -> SanitationRecipeRevisionRecord:
    """Safely create revision 1 for a legacy/new materialized recipe, once.

    Call this before mutating an existing recipe. New recipes can first be
    populated with their initial operations and contracts, then initialized
    through this function so revision 1 is the true first head.
    """

    if recipe.id is None:
        db.add(recipe)
        await db.flush()

    with db.no_autoflush:
        current = await db.execute(
            select(SanitationRecipeRecord.active_revision_id)
            .where(SanitationRecipeRecord.id == recipe.id)
            .with_for_update()
        )
    active_revision_id = current.scalar_one_or_none()
    if active_revision_id is not None:
        with db.no_autoflush:
            active = await db.execute(
                select(SanitationRecipeRevisionRecord).where(
                    SanitationRecipeRevisionRecord.id == active_revision_id,
                    SanitationRecipeRevisionRecord.recipe_id == recipe.id,
                )
            )
        revision = active.scalar_one_or_none()
        if revision is None:
            raise SanitationRevisionIntegrityError(
                "sanitation recipe points to a missing or foreign revision"
            )
        recipe.active_revision_id = revision.id
        return revision

    with db.no_autoflush:
        prior = await db.execute(
            select(SanitationRecipeRevisionRecord.id).where(
                SanitationRecipeRevisionRecord.recipe_id == recipe.id
            )
        )
    if prior.first() is not None:
        raise SanitationRevisionIntegrityError(
            "sanitation recipe has revisions but no active revision pointer"
        )

    revision = SanitationRecipeRevisionRecord(
        id=uuid4(),
        recipe_id=recipe.id,
        revision_number=1,
        parent_revision_id=None,
        state=_state_for_materialized_recipe(recipe),
        operations=deepcopy(recipe.operations or []),
        input_contract=sanitation_fingerprint_contract(recipe.input_fingerprint),
        output_contract=sanitation_fingerprint_contract(recipe.output_fingerprint),
        actor_source="system",
        reason="建立清洗配方版本历史",
        source_correction_id=None,
    )
    recipe.active_revision_id = revision.id
    db.add(revision)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise SanitationRevisionConflictError(
            expected_revision_id=None,
            active_revision_id=None,
        ) from exc
    except OperationalError as exc:
        if not _is_sqlite_busy(db, exc):
            raise
        raise SanitationRevisionConflictError(
            expected_revision_id=None,
            active_revision_id=None,
        ) from exc
    return revision


async def append_sanitation_revision(
    db: AsyncSession,
    recipe: SanitationRecipeRecord,
    *,
    expected_active_revision_id: UUID,
    state: SanitationRevisionState,
    operations: list[dict[str, Any]],
    input_contract: dict[str, Any],
    output_contract: dict[str, Any],
    actor_source: str,
    reason: str | None = None,
    source_correction_id: UUID | str | None = None,
) -> SanitationRecipeRevisionRecord:
    """Append a revision and atomically advance the materialized recipe head."""

    if state not in _VALID_STATES:
        raise ValueError(f"unsupported sanitation revision state: {state}")
    if recipe.id is None:
        raise ValueError("sanitation recipe is not persisted")
    canonical_operations = canonicalize_sanitation_operations(operations)
    input_fingerprint = _fingerprint_from_contract(input_contract, label="input")
    output_fingerprint = _fingerprint_from_contract(output_contract, label="output")

    with db.no_autoflush:
        current = await db.execute(
            select(SanitationRecipeRecord.active_revision_id)
            .where(SanitationRecipeRecord.id == recipe.id)
            .with_for_update()
        )
    database_active_revision_id = current.scalar_one_or_none()
    if database_active_revision_id != expected_active_revision_id:
        raise SanitationRevisionConflictError(
            expected_revision_id=expected_active_revision_id,
            active_revision_id=database_active_revision_id,
        )
    if database_active_revision_id is None:
        raise SanitationRevisionIntegrityError(
            "sanitation recipe has no revision head; initialize it before appending"
        )

    with db.no_autoflush:
        parent_result = await db.execute(
            select(SanitationRecipeRevisionRecord).where(
                SanitationRecipeRevisionRecord.id == database_active_revision_id,
                SanitationRecipeRevisionRecord.recipe_id == recipe.id,
            )
        )
    parent = parent_result.scalar_one_or_none()
    if parent is None:
        raise SanitationRevisionIntegrityError(
            "sanitation recipe points to a missing or foreign revision"
        )

    revision = SanitationRecipeRevisionRecord(
        id=uuid4(),
        recipe_id=recipe.id,
        revision_number=parent.revision_number + 1,
        parent_revision_id=parent.id,
        state=state,
        operations=deepcopy(canonical_operations),
        input_contract=deepcopy(input_contract),
        output_contract=deepcopy(output_contract),
        actor_source=actor_source[:30],
        reason=reason,
        source_correction_id=(str(source_correction_id) if source_correction_id else None),
    )
    recipe.operations = deepcopy(canonical_operations)
    recipe.input_fingerprint = input_fingerprint
    recipe.output_fingerprint = output_fingerprint
    recipe.active_revision_id = revision.id
    db.add(revision)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise SanitationRevisionConflictError(
            expected_revision_id=expected_active_revision_id,
            active_revision_id=database_active_revision_id,
        ) from exc
    except OperationalError as exc:
        if not _is_sqlite_busy(db, exc):
            raise
        raise SanitationRevisionConflictError(
            expected_revision_id=expected_active_revision_id,
            active_revision_id=database_active_revision_id,
        ) from exc
    return revision


async def restore_sanitation_revision(
    db: AsyncSession,
    recipe: SanitationRecipeRecord,
    target: SanitationRecipeRevisionRecord,
    *,
    expected_active_revision_id: UUID,
    reason: str | None = None,
    actor_source: str = "user",
    source_correction_id: UUID | str | None = None,
) -> SanitationRecipeRevisionRecord:
    """Restore old cleaning behavior by appending a new ``reverted`` head."""

    if target.recipe_id != recipe.id:
        raise ValueError("revision does not belong to sanitation recipe")
    return await append_sanitation_revision(
        db,
        recipe,
        expected_active_revision_id=expected_active_revision_id,
        state="reverted",
        operations=deepcopy(target.operations or []),
        input_contract=deepcopy(target.input_contract or {}),
        output_contract=deepcopy(target.output_contract or {}),
        actor_source=actor_source,
        reason=reason or f"恢复清洗配方版本 {target.revision_number}",
        source_correction_id=source_correction_id,
    )


async def sanitation_revision_or_none(
    db: AsyncSession,
    *,
    recipe_id: UUID,
    revision_id: UUID,
) -> SanitationRecipeRevisionRecord | None:
    result = await db.execute(
        select(SanitationRecipeRevisionRecord).where(
            SanitationRecipeRevisionRecord.id == revision_id,
            SanitationRecipeRevisionRecord.recipe_id == recipe_id,
        )
    )
    return result.scalar_one_or_none()
