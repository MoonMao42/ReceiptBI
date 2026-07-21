"""clean orphan sanitation revision history

Revision ID: 0009_cleanup_orphan_sanitation
Revises: 0008_sanitation_recipe_revisions
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "0009_cleanup_orphan_sanitation"
down_revision: str | None = "0008_sanitation_recipe_revisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _load_rows(bind) -> tuple[dict[Any, Any | None], dict[Any, dict[str, Any]]]:
    recipes = {
        row["id"]: row["active_revision_id"]
        for row in bind.execute(
            sa.text("SELECT id, active_revision_id FROM sanitation_recipes")
        ).mappings()
    }
    revisions = {
        row["id"]: dict(row)
        for row in bind.execute(
            sa.text(
                "SELECT id, recipe_id, revision_number, parent_revision_id "
                "FROM sanitation_recipe_revisions"
            )
        ).mappings()
    }
    return recipes, revisions


def _delete_orphan_revisions(bind) -> None:
    recipes, revisions = _load_rows(bind)
    orphan_ids = {
        revision_id for revision_id, row in revisions.items() if row["recipe_id"] not in recipes
    }
    if not orphan_ids:
        return

    external_children = [
        revision_id
        for revision_id, row in revisions.items()
        if revision_id not in orphan_ids and row["parent_revision_id"] in orphan_ids
    ]
    if external_children:
        raise RuntimeError(
            "sanitation revision history crosses an orphan recipe boundary; refusing cleanup"
        )

    remaining = set(orphan_ids)
    delete_revision = sa.text("DELETE FROM sanitation_recipe_revisions WHERE id = :revision_id")
    while remaining:
        referenced_parents = {
            revisions[revision_id]["parent_revision_id"]
            for revision_id in remaining
            if revisions[revision_id]["parent_revision_id"] in remaining
        }
        leaves = remaining - referenced_parents
        if not leaves:
            raise RuntimeError(
                "orphan sanitation revision history contains a cycle; refusing cleanup"
            )
        for revision_id in leaves:
            bind.execute(delete_revision, {"revision_id": revision_id})
        remaining.difference_update(leaves)


def _assert_remaining_history_is_linked(bind) -> None:
    recipes, revisions = _load_rows(bind)
    revisions_by_recipe: dict[Any, set[Any]] = {recipe_id: set() for recipe_id in recipes}
    for revision_id, row in revisions.items():
        recipe_id = row["recipe_id"]
        if recipe_id not in recipes:
            raise RuntimeError("orphan sanitation revision cleanup did not complete")
        revisions_by_recipe[recipe_id].add(revision_id)

    for recipe_id, active_revision_id in recipes.items():
        owned_revision_ids = revisions_by_recipe[recipe_id]
        if active_revision_id is None:
            raise RuntimeError(
                f"sanitation recipe {recipe_id} has no active revision; refusing migration"
            )
        active = revisions.get(active_revision_id)
        if active is None or active["recipe_id"] != recipe_id:
            raise RuntimeError(
                f"sanitation recipe {recipe_id} has an invalid active revision; refusing migration"
            )
        active_number = int(active["revision_number"])
        maximum_number = max(
            int(revisions[revision_id]["revision_number"]) for revision_id in owned_revision_ids
        )
        if active_number != maximum_number:
            raise RuntimeError(
                f"sanitation recipe {recipe_id} active revision is not the final revision; "
                "refusing migration"
            )

        visited: set[Any] = set()
        current_revision_id: Any | None = active_revision_id
        expected_number = active_number
        while current_revision_id is not None:
            if current_revision_id in visited:
                raise RuntimeError(
                    f"sanitation recipe {recipe_id} revision history contains a cycle; "
                    "refusing migration"
                )
            current = revisions.get(current_revision_id)
            if current is None:
                raise RuntimeError(
                    f"sanitation recipe {recipe_id} revision history is broken; refusing migration"
                )
            if current["recipe_id"] != recipe_id:
                raise RuntimeError(
                    f"sanitation recipe {recipe_id} revision history crosses recipes; "
                    "refusing migration"
                )
            if int(current["revision_number"]) != expected_number:
                raise RuntimeError(
                    f"sanitation recipe {recipe_id} revision numbers are not contiguous; "
                    "refusing migration"
                )
            visited.add(current_revision_id)
            parent_revision_id = current["parent_revision_id"]
            if expected_number == 1:
                if parent_revision_id is not None:
                    raise RuntimeError(
                        f"sanitation recipe {recipe_id} revision 1 has a parent; refusing migration"
                    )
                current_revision_id = None
                continue
            if parent_revision_id is None:
                raise RuntimeError(
                    f"sanitation recipe {recipe_id} revision history is broken; refusing migration"
                )
            current_revision_id = parent_revision_id
            expected_number -= 1

        if visited != owned_revision_ids:
            raise RuntimeError(
                f"sanitation recipe {recipe_id} has revisions outside its active chain; "
                "refusing migration"
            )


def upgrade() -> None:
    bind = op.get_bind()
    _delete_orphan_revisions(bind)
    _assert_remaining_history_is_linked(bind)


def downgrade() -> None:
    # Deleted orphan rows had no owning recipe and cannot be restored safely.
    pass
