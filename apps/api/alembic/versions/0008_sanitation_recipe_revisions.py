"""append-only sanitation recipe revisions

Revision ID: 0008_sanitation_recipe_revisions
Revises: 0007_semantic_revisions
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008_sanitation_recipe_revisions"
down_revision: str | None = "0007_semantic_revisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> sa.types.TypeEngine:
    return postgresql.UUID(as_uuid=True)


def _fingerprint_contract(fingerprint: str | None) -> dict[str, object]:
    return {"version": 1, "fingerprint": fingerprint}


def _legacy_state(status: str | None) -> str:
    if status == "reverted":
        return "reverted"
    if status in {"needs_attention", "candidate"}:
        return "candidate"
    return "confirmed"


def upgrade() -> None:
    op.add_column(
        "sanitation_recipes",
        sa.Column("active_revision_id", _uuid(), nullable=True),
    )
    op.create_index(
        "ix_sanitation_recipes_active_revision_id",
        "sanitation_recipes",
        ["active_revision_id"],
    )

    op.create_table(
        "sanitation_recipe_revisions",
        sa.Column("recipe_id", _uuid(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("parent_revision_id", _uuid(), nullable=True),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("operations", sa.JSON(), nullable=False),
        sa.Column("input_contract", sa.JSON(), nullable=False),
        sa.Column("output_contract", sa.JSON(), nullable=False),
        sa.Column("actor_source", sa.String(30), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("source_correction_id", sa.String(36), nullable=True),
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('candidate', 'confirmed', 'reverted')",
            name="ck_sanitation_recipe_revision_state",
        ),
        sa.ForeignKeyConstraint(
            ["recipe_id"],
            ["sanitation_recipes.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_revision_id"],
            ["sanitation_recipe_revisions.id"],
            name="fk_sanitation_recipe_revisions_parent_revision_id",
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.UniqueConstraint(
            "recipe_id",
            "revision_number",
            name="uq_sanitation_recipe_revision_number",
        ),
    )
    for column in (
        "recipe_id",
        "parent_revision_id",
        "source_correction_id",
        "created_at",
    ):
        op.create_index(
            f"ix_sanitation_recipe_revisions_{column}",
            "sanitation_recipe_revisions",
            [column],
        )

    recipes = sa.table(
        "sanitation_recipes",
        sa.column("id", _uuid()),
        sa.column("status", sa.String()),
        sa.column("operations", sa.JSON()),
        sa.column("input_fingerprint", sa.String()),
        sa.column("output_fingerprint", sa.String()),
        sa.column("active_revision_id", _uuid()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    revisions = sa.table(
        "sanitation_recipe_revisions",
        sa.column("id", _uuid()),
        sa.column("recipe_id", _uuid()),
        sa.column("revision_number", sa.Integer()),
        sa.column("parent_revision_id", _uuid()),
        sa.column("state", sa.String()),
        sa.column("operations", sa.JSON()),
        sa.column("input_contract", sa.JSON()),
        sa.column("output_contract", sa.JSON()),
        sa.column("actor_source", sa.String()),
        sa.column("reason", sa.Text()),
        sa.column("source_correction_id", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    bind = op.get_bind()
    for row in bind.execute(sa.select(recipes)).mappings():
        revision_id = uuid4()
        bind.execute(
            revisions.insert().values(
                id=revision_id,
                recipe_id=row["id"],
                revision_number=1,
                parent_revision_id=None,
                state=_legacy_state(row["status"]),
                operations=row["operations"] or [],
                input_contract=_fingerprint_contract(row["input_fingerprint"]),
                output_contract=_fingerprint_contract(row["output_fingerprint"]),
                actor_source="system",
                reason="建立清洗配方版本历史",
                source_correction_id=None,
                created_at=row["created_at"] or datetime.now(UTC),
            )
        )
        bind.execute(
            recipes.update().where(recipes.c.id == row["id"]).values(active_revision_id=revision_id)
        )


def downgrade() -> None:
    op.drop_index(
        "ix_sanitation_recipe_revisions_created_at",
        table_name="sanitation_recipe_revisions",
    )
    op.drop_index(
        "ix_sanitation_recipe_revisions_source_correction_id",
        table_name="sanitation_recipe_revisions",
    )
    op.drop_index(
        "ix_sanitation_recipe_revisions_parent_revision_id",
        table_name="sanitation_recipe_revisions",
    )
    op.drop_index(
        "ix_sanitation_recipe_revisions_recipe_id",
        table_name="sanitation_recipe_revisions",
    )
    op.drop_table("sanitation_recipe_revisions")
    op.drop_index(
        "ix_sanitation_recipes_active_revision_id",
        table_name="sanitation_recipes",
    )
    op.drop_column("sanitation_recipes", "active_revision_id")
