"""append-only semantic entry revisions

Revision ID: 0007_semantic_revisions
Revises: 0006_semantic_execution_state
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007_semantic_revisions"
down_revision: str | None = "0006_semantic_execution_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> sa.types.TypeEngine:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column(
        "semantic_entries",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "semantic_entries",
        sa.Column("revision_number", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "semantic_entries",
        sa.Column("active_revision_id", _uuid(), nullable=True),
    )
    op.create_index("ix_semantic_entries_is_active", "semantic_entries", ["is_active"])
    op.create_index(
        "ix_semantic_entries_active_revision_id",
        "semantic_entries",
        ["active_revision_id"],
    )

    op.create_table(
        "semantic_entry_revisions",
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("semantic_entry_id", _uuid(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("parent_revision_id", _uuid(), nullable=True),
        sa.Column("restored_from_revision_id", _uuid(), nullable=True),
        sa.Column("mutation_kind", sa.String(40), nullable=False),
        sa.Column("actor_source", sa.String(30), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("source_correction_id", sa.String(36), nullable=True),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["semantic_entry_id"],
            ["semantic_entries.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["parent_revision_id"],
            ["semantic_entry_revisions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["restored_from_revision_id"],
            ["semantic_entry_revisions.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "semantic_entry_id",
            "revision_number",
            name="uq_semantic_revision_entry_number",
        ),
    )
    for column in (
        "project_id",
        "semantic_entry_id",
        "parent_revision_id",
        "restored_from_revision_id",
        "source_correction_id",
        "created_at",
    ):
        op.create_index(
            f"ix_semantic_entry_revisions_{column}",
            "semantic_entry_revisions",
            [column],
        )

    entries = sa.table(
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
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("revision_number", sa.Integer()),
        sa.column("active_revision_id", _uuid()),
    )
    revisions = sa.table(
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
    bind = op.get_bind()
    for row in bind.execute(sa.select(entries)).mappings():
        revision_id = uuid4()
        snapshot = {
            "key": row["key"],
            "value": row["value"],
            "entry_type": row["entry_type"],
            "state": row["state"],
            "confidence": row["confidence"],
            "definition": row["definition"],
            "validity": row["validity"],
            "execution_state": row["execution_state"],
            "execution_details": row["execution_details"] or {},
            "evidence": row["evidence"] or [],
            "source": row["source"],
            "is_active": True,
        }
        bind.execute(
            revisions.insert().values(
                id=revision_id,
                project_id=row["project_id"],
                semantic_entry_id=row["id"],
                revision_number=1,
                parent_revision_id=None,
                restored_from_revision_id=None,
                mutation_kind="migration_backfill",
                actor_source="system",
                reason="建立版本历史",
                source_correction_id=None,
                snapshot=snapshot,
                created_at=row["created_at"],
            )
        )
        bind.execute(
            entries.update()
            .where(entries.c.id == row["id"])
            .values(active_revision_id=revision_id, revision_number=1)
        )


def downgrade() -> None:
    op.drop_index("ix_semantic_entry_revisions_created_at", table_name="semantic_entry_revisions")
    op.drop_index(
        "ix_semantic_entry_revisions_source_correction_id",
        table_name="semantic_entry_revisions",
    )
    op.drop_index(
        "ix_semantic_entry_revisions_restored_from_revision_id",
        table_name="semantic_entry_revisions",
    )
    op.drop_index(
        "ix_semantic_entry_revisions_parent_revision_id",
        table_name="semantic_entry_revisions",
    )
    op.drop_index(
        "ix_semantic_entry_revisions_semantic_entry_id",
        table_name="semantic_entry_revisions",
    )
    op.drop_index("ix_semantic_entry_revisions_project_id", table_name="semantic_entry_revisions")
    op.drop_table("semantic_entry_revisions")
    op.drop_index("ix_semantic_entries_active_revision_id", table_name="semantic_entries")
    op.drop_index("ix_semantic_entries_is_active", table_name="semantic_entries")
    op.drop_column("semantic_entries", "active_revision_id")
    op.drop_column("semantic_entries", "revision_number")
    op.drop_column("semantic_entries", "is_active")
