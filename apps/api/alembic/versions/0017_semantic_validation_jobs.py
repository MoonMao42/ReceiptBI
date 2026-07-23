"""add semantic recommendation batches and validation jobs

Revision ID: 0017_semantic_validation_jobs
Revises: 0016_processing_consent
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0017_semantic_validation_jobs"
down_revision: str | None = "0016_processing_consent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> sa.types.TypeEngine:
    return postgresql.UUID(as_uuid=True)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    ]


def upgrade() -> None:
    op.add_column(
        "semantic_entries",
        sa.Column("recommendation_batch_id", _uuid(), nullable=True),
    )
    op.create_index(
        "ix_semantic_entries_recommendation_batch_id",
        "semantic_entries",
        ["recommendation_batch_id"],
    )

    op.create_table(
        "semantic_validation_jobs",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("requested_by", sa.String(30), nullable=False, server_default="user"),
        sa.Column("reason", sa.Text()),
        sa.Column(
            "cancel_requested",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')",
            name="ck_semantic_validation_job_status",
        ),
        *_timestamps(),
    )
    op.create_index(
        "ix_semantic_validation_jobs_project_id",
        "semantic_validation_jobs",
        ["project_id"],
    )
    op.create_index(
        "ix_semantic_validation_jobs_status",
        "semantic_validation_jobs",
        ["status"],
    )

    op.create_table(
        "semantic_validation_job_items",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("job_id", _uuid(), nullable=False),
        sa.Column("semantic_entry_id", _uuid(), nullable=False),
        sa.Column("semantic_revision_id", _uuid(), nullable=False),
        sa.Column("definition_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("code", sa.String(80)),
        sa.Column("facts", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["semantic_validation_jobs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["semantic_entry_id"],
            ["semantic_entries.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["semantic_revision_id"],
            ["semantic_entry_revisions.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "job_id",
            "semantic_entry_id",
            name="uq_semantic_validation_job_entry",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'verified', 'blocked', 'failed')",
            name="ck_semantic_validation_item_status",
        ),
        *_timestamps(),
    )
    for column in (
        "job_id",
        "semantic_entry_id",
        "semantic_revision_id",
        "status",
    ):
        op.create_index(
            f"ix_semantic_validation_job_items_{column}",
            "semantic_validation_job_items",
            [column],
        )


def downgrade() -> None:
    op.drop_table("semantic_validation_job_items")
    op.drop_table("semantic_validation_jobs")
    op.drop_index(
        "ix_semantic_entries_recommendation_batch_id",
        table_name="semantic_entries",
    )
    op.drop_column("semantic_entries", "recommendation_batch_id")
