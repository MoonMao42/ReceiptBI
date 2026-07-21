"""Sanitation recipe revisions are append-only and restore by creating a new head."""

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.tables import (
    Project,
    ProjectDataSource,
    SanitationRecipeRecord,
    SanitationRecipeRevisionRecord,
)
from app.services.sanitation_contract import SanitationContractError
from app.services.sanitation_revisions import (
    SanitationRevisionConflictError,
    append_sanitation_revision,
    ensure_sanitation_revision_head,
    restore_sanitation_revision,
    sanitation_fingerprint_contract,
)


async def _recipe(db_session) -> SanitationRecipeRecord:
    project = Project(name="清洗版本测试")
    db_session.add(project)
    await db_session.flush()
    source = ProjectDataSource(
        project_id=project.id,
        kind="file",
        name="orders.csv",
        format="csv",
        status="ready",
    )
    db_session.add(source)
    await db_session.flush()
    recipe = SanitationRecipeRecord(
        project_id=project.id,
        data_source_id=source.id,
        name="订单自动整理",
        status="applied",
        operations=[{"operation": "trim_text", "column": "store_id"}],
        input_fingerprint="a" * 64,
        output_fingerprint="b" * 64,
    )
    db_session.add(recipe)
    await db_session.flush()
    return recipe


@pytest.mark.asyncio
async def test_lazy_backfill_preserves_materialized_recipe_and_is_idempotent(db_session):
    recipe = await _recipe(db_session)

    first = await ensure_sanitation_revision_head(db_session, recipe)
    again = await ensure_sanitation_revision_head(db_session, recipe)

    assert again.id == first.id == recipe.active_revision_id
    assert first.revision_number == 1
    assert first.parent_revision_id is None
    assert first.state == "confirmed"
    assert first.operations == [{"operation": "trim_text", "column": "store_id"}]
    assert first.input_contract == {"version": 1, "fingerprint": "a" * 64}
    assert first.output_contract == {"version": 1, "fingerprint": "b" * 64}
    revisions = await db_session.execute(
        select(SanitationRecipeRevisionRecord).where(
            SanitationRecipeRevisionRecord.recipe_id == recipe.id
        )
    )
    assert len(list(revisions.scalars())) == 1


@pytest.mark.asyncio
async def test_append_uses_optimistic_head_and_keeps_prior_revision_immutable(db_session):
    recipe = await _recipe(db_session)
    first = await ensure_sanitation_revision_head(db_session, recipe)
    changed_operations = [
        {
            "operation": "trim_text",
            "contract_version": 1,
            "column": "store_id",
            "error_policy": "preserve_original",
        },
        {
            "operation": "drop_exact_duplicates",
            "contract_version": 1,
            "count": 1,
        },
    ]

    second = await append_sanitation_revision(
        db_session,
        recipe,
        expected_active_revision_id=first.id,
        state="confirmed",
        operations=changed_operations,
        input_contract={"version": 1, "fingerprint": "c" * 64, "columns": ["order_id"]},
        output_contract={"version": 1, "fingerprint": "d" * 64, "row_count": 12},
        actor_source="user",
        reason="订单号重复时只保留一条",
        source_correction_id=uuid4(),
    )

    assert second.revision_number == 2
    assert second.parent_revision_id == first.id
    assert recipe.active_revision_id == second.id
    assert recipe.operations == changed_operations
    assert recipe.input_fingerprint == "c" * 64
    assert recipe.output_fingerprint == "d" * 64
    await db_session.refresh(first)
    assert first.operations == [{"operation": "trim_text", "column": "store_id"}]
    assert first.input_contract["fingerprint"] == "a" * 64

    with pytest.raises(SanitationRevisionConflictError) as conflict:
        await append_sanitation_revision(
            db_session,
            recipe,
            expected_active_revision_id=first.id,
            state="candidate",
            operations=[],
            input_contract=sanitation_fingerprint_contract(None),
            output_contract=sanitation_fingerprint_contract(None),
            actor_source="agent",
        )
    assert conflict.value.active_revision_id == second.id


@pytest.mark.asyncio
async def test_restore_appends_reverted_head_without_rewriting_target(db_session):
    recipe = await _recipe(db_session)
    first = await ensure_sanitation_revision_head(db_session, recipe)
    second = await append_sanitation_revision(
        db_session,
        recipe,
        expected_active_revision_id=first.id,
        state="confirmed",
        operations=[{"operation": "drop_exact_duplicates", "count": 1}],
        input_contract=sanitation_fingerprint_contract("c" * 64),
        output_contract=sanitation_fingerprint_contract("d" * 64),
        actor_source="user",
    )

    restored = await restore_sanitation_revision(
        db_session,
        recipe,
        first,
        expected_active_revision_id=second.id,
        reason="恢复到首次确认的方法",
    )
    restored_operations = [
        {
            "operation": "trim_text",
            "contract_version": 1,
            "column": "store_id",
            "error_policy": "preserve_original",
        }
    ]

    assert restored.revision_number == 3
    assert restored.parent_revision_id == second.id
    assert restored.state == "reverted"
    assert restored.operations == restored_operations
    assert recipe.active_revision_id == restored.id
    assert recipe.operations == restored_operations
    await db_session.refresh(first)
    await db_session.refresh(second)
    assert first.revision_number == 1
    assert first.operations == [{"operation": "trim_text", "column": "store_id"}]
    assert second.revision_number == 2
    assert second.state == "confirmed"
    assert second.operations == [
        {
            "operation": "drop_exact_duplicates",
            "contract_version": 1,
            "count": 1,
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "illegal_operation",
    [
        {"operation": "drop_duplicates", "columns": ["order_id"]},
        {
            "operation": "trim_text",
            "column": "store_id",
            "contract_version": 2,
        },
        {
            "operation": "trim_text",
            "column": "store_id",
            "sql": "DROP TABLE orders",
        },
        {
            "operation": "trim_text",
            "column": "store_id",
            "python": "open('/tmp/x', 'w')",
        },
    ],
)
async def test_append_rejects_illegal_operations_without_persisting(
    db_session,
    illegal_operation,
):
    recipe = await _recipe(db_session)
    first = await ensure_sanitation_revision_head(db_session, recipe)
    original_operations = list(recipe.operations)

    with pytest.raises(SanitationContractError):
        await append_sanitation_revision(
            db_session,
            recipe,
            expected_active_revision_id=first.id,
            state="confirmed",
            operations=[illegal_operation],
            input_contract=sanitation_fingerprint_contract("c" * 64),
            output_contract=sanitation_fingerprint_contract("d" * 64),
            actor_source="user",
        )

    assert recipe.active_revision_id == first.id
    assert recipe.operations == original_operations
    revisions = await db_session.execute(
        select(SanitationRecipeRevisionRecord).where(
            SanitationRecipeRevisionRecord.recipe_id == recipe.id
        )
    )
    assert len(list(revisions.scalars())) == 1
