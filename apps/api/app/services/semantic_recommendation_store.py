"""Transactional storage for generated semantic recommendation batches.

The synchronous recommendation endpoint and the durable inventory worker share
this CAS-safe persistence path.  Confirmed, locked, ignored, independently
validated, or otherwise user-governed heads are never overwritten by a refresh.
"""

from __future__ import annotations

import json
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.tables import SemanticEntry, SemanticEntryRevision
from app.models.workspace import SemanticEntryCreate
from app.services.semantic_recommendations import SemanticRecommendationBatch
from app.services.semantic_revisions import (
    append_semantic_revision,
    reset_semantic_execution_proof,
)
from app.services.semantic_scopes import resolve_semantic_entry_scope

_PROTECTED_EVIDENCE = frozenset(
    {
        "semantic_candidate_ignored",
        "semantic_candidate_restored",
        "relationship_validation_requested",
        "semantic_validation_requested",
        "semantic_validation_queued",
        "semantic_validation_result",
        "semantic_human_attestation",
        "verified_candidate_remembered",
    }
)


def _is_user_governed(
    entry: SemanticEntry,
    *,
    user_revision_entry_ids: set[UUID],
) -> bool:
    is_scope_presentation = entry.entry_type == "scope_presentation"
    expected_execution_state = (
        "definition_only" if is_scope_presentation else "needs_validation"
    )
    if (
        entry.id in user_revision_entry_ids
        or entry.state in {"confirmed", "locked"}
        or not entry.is_active
        or entry.source != "inferred"
        or entry.validity != "unverified"
        or entry.execution_state != expected_execution_state
    ):
        return True
    allowed_codes = {
        None,
        (
            "semantic_scope_presentation_needs_review"
            if is_scope_presentation
            else "semantic_recommendation_needs_validation"
        ),
    }
    if (
        isinstance(entry.execution_details, dict)
        and entry.execution_details.get("code") not in allowed_codes
    ):
        return True
    return any(
        isinstance(item, dict) and item.get("kind") in _PROTECTED_EVIDENCE
        for item in (entry.evidence or [])
    )


def _binding_slot(definition: object) -> str | None:
    if not isinstance(definition, dict) or definition.get("kind") not in {
        "aggregate_metric",
        "dimension",
    }:
        return None
    source = definition.get("source")
    if not isinstance(source, dict):
        return None
    fields = (
        "source_logical_name",
        "source_kind",
        "table_or_view",
        "action_column",
    )
    if any(not str(source.get(field) or "").strip() for field in fields):
        return None
    return json.dumps(
        {field: str(source[field]).strip().casefold() for field in fields},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


async def _retire_superseded(
    db: AsyncSession,
    *,
    existing_entries: list[SemanticEntry],
    persisted_entries: list[SemanticEntry],
    user_revision_entry_ids: set[UUID],
) -> None:
    current_by_slot = {
        slot: entry
        for entry in persisted_entries
        if (slot := _binding_slot(entry.definition)) is not None
    }
    if not current_by_slot:
        return
    current_ids = {entry.id for entry in persisted_entries}
    for entry in existing_entries:
        slot = _binding_slot(entry.definition)
        if (
            entry.id in current_ids
            or slot not in current_by_slot
            or _is_user_governed(
                entry,
                user_revision_entry_ids=user_revision_entry_ids,
            )
        ):
            continue
        replacement = current_by_slot[slot]
        previous_revision_id = entry.active_revision_id
        entry.is_active = False
        entry.validity = "stale"
        reset_semantic_execution_proof(entry)
        entry.evidence = [
            *list(entry.evidence or []),
            {
                "kind": "semantic_recommendation_superseded",
                "replacement_entry_id": str(replacement.id),
                "reason": "当前字段画像产生了新的业务角色建议",
            },
        ]
        await append_semantic_revision(
            db,
            entry,
            mutation_kind="recommendation_superseded",
            actor_source="system",
            reason="停用同一字段的旧版语义建议",
            expected_active_revision_id=previous_revision_id,
        )


def _execution_details(
    batch: SemanticRecommendationBatch,
    *,
    locale: Literal["zh", "en"],
    entry_type: str,
) -> dict[str, Any]:
    if entry_type == "scope_presentation":
        return {
            "version": 1,
            "status": "definition_only",
            "code": "semantic_scope_presentation_needs_review",
            "details": {
                "recommendation_batch_id": str(batch.batch_id),
                "generated_by": batch.generated_by,
            },
            "summary": (
                "这是数据源或表的候选中文名称；人工核对并采纳后才会显示给普通分析。"
                if locale == "zh"
                else "This candidate source or table label applies only after human review and adoption."
            ),
        }
    return {
        "version": 1,
        "status": "needs_validation",
        "code": "semantic_recommendation_needs_validation",
        "details": {
            "recommendation_batch_id": str(batch.batch_id),
            "generated_by": batch.generated_by,
        },
        "summary": (
            "这是待核对的推荐；只有独立验证通过后才可记住并用于普通分析。"
            if locale == "zh"
            else "This recommendation remains a candidate until independent validation passes."
        ),
    }


def _evidence(
    item: SemanticEntryCreate,
    batch: SemanticRecommendationBatch,
) -> list[dict[str, Any]]:
    return [
        *[dict(value) for value in item.evidence],
        {
            "kind": "semantic_recommendation_batch",
            "batch_id": str(batch.batch_id),
            "candidate_id": item.key,
            "generated_by": batch.generated_by,
            "requires_validation": item.entry_type != "scope_presentation",
            "requires_human_review": item.entry_type == "scope_presentation",
        },
    ]


async def persist_semantic_recommendation_batch(
    db: AsyncSession,
    *,
    project_id: UUID,
    batch: SemanticRecommendationBatch,
    locale: Literal["zh", "en"],
) -> list[SemanticEntry]:
    """Create or CAS-refresh only untouched recommendation heads."""

    if not batch.items:
        return []
    keys = [item.key for item in batch.items]
    result = await db.execute(
        select(SemanticEntry)
        .where(
            SemanticEntry.project_id == project_id,
            or_(
                SemanticEntry.key.in_(keys),
                SemanticEntry.key.like("semantic_recommendation:%"),
            ),
        )
        .with_for_update()
    )
    existing_entries = list(result.scalars())
    existing_by_key = {entry.key: entry for entry in existing_entries}
    existing_ids = [entry.id for entry in existing_entries]
    user_revision_entry_ids: set[UUID] = set()
    if existing_ids:
        revision_result = await db.execute(
            select(SemanticEntryRevision.semantic_entry_id).where(
                SemanticEntryRevision.project_id == project_id,
                SemanticEntryRevision.semantic_entry_id.in_(existing_ids),
                SemanticEntryRevision.actor_source == "user",
            )
        )
        user_revision_entry_ids = set(revision_result.scalars())

    persisted: list[SemanticEntry] = []
    actor_source = "ai" if batch.generated_by == "ai" else "inferred"
    for item in batch.items:
        scope = await resolve_semantic_entry_scope(
            db,
            project_id=project_id,
            definition=item.model_dump(mode="json").get("definition"),
            requested_scope_id=item.scope_id,
            allow_unresolved_project_fallback=True,
        )
        existing = existing_by_key.get(item.key)
        evidence = _evidence(item, batch)
        execution_details = _execution_details(
            batch,
            locale=locale,
            entry_type=item.entry_type,
        )
        execution_state = (
            "definition_only"
            if item.entry_type == "scope_presentation"
            else "needs_validation"
        )
        definition = item.model_dump(mode="json").get("definition")
        if existing is not None:
            if _is_user_governed(
                existing,
                user_revision_entry_ids=user_revision_entry_ids,
            ):
                continue
            previous_revision_id = existing.active_revision_id
            existing.value = item.value
            existing.entry_type = item.entry_type
            existing.state = "candidate"
            existing.confidence = item.confidence
            existing.definition = definition
            existing.validity = "unverified"
            existing.execution_state = execution_state
            existing.execution_details = execution_details
            existing.evidence = evidence
            existing.source = "inferred"
            existing.is_active = True
            existing.scope_id = scope.id
            existing.recommendation_batch_id = batch.batch_id
            await append_semantic_revision(
                db,
                existing,
                mutation_kind="recommendation_refreshed",
                actor_source=actor_source,
                reason="刷新当前数据画像生成的语义推荐",
                expected_active_revision_id=previous_revision_id,
            )
            persisted.append(existing)
            continue

        entry = SemanticEntry(
            project_id=project_id,
            scope_id=scope.id,
            key=item.key,
            value=item.value,
            entry_type=item.entry_type,
            state="candidate",
            confidence=item.confidence,
            definition=definition,
            validity="unverified",
            execution_state=execution_state,
            execution_details=execution_details,
            evidence=evidence,
            source="inferred",
            is_active=True,
            recommendation_batch_id=batch.batch_id,
        )
        db.add(entry)
        await db.flush()
        await append_semantic_revision(
            db,
            entry,
            mutation_kind="recommendation_created",
            actor_source=actor_source,
            reason="根据当前数据画像生成语义推荐",
        )
        persisted.append(entry)

    await _retire_superseded(
        db,
        existing_entries=existing_entries,
        persisted_entries=persisted,
        user_revision_entry_ids=user_revision_entry_ids,
    )
    return persisted
