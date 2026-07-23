"""add durable semantic inventory jobs

Revision ID: 0021_semantic_inventory_jobs
Revises: 0020_retire_stale_recos
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0021_semantic_inventory_jobs"
down_revision: str | None = "0020_retire_stale_recos"
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
    op.create_table(
        "semantic_inventory_jobs",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("source_id", _uuid(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="queued"),
        sa.Column("depth", sa.String(20), nullable=False),
        sa.Column("locale", sa.String(5), nullable=False),
        sa.Column("model_id", _uuid()),
        sa.Column("tables", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("relation_index_hash", sa.String(64), nullable=False),
        sa.Column("selection_hash", sa.String(64), nullable=False),
        sa.Column(
            "cancel_requested",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("lease_owner", sa.String(160)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["project_data_sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["model_id"], ["models.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', "
            "'completed_with_errors', 'cancelled', 'failed')",
            name="ck_semantic_inventory_job_status",
        ),
        sa.CheckConstraint(
            "depth IN ('structure', 'sampled')",
            name="ck_semantic_inventory_job_depth",
        ),
        sa.CheckConstraint(
            "locale IN ('zh', 'en')",
            name="ck_semantic_inventory_job_locale",
        ),
        *_timestamps(),
    )
    for column in (
        "project_id",
        "source_id",
        "status",
        "model_id",
        "selection_hash",
        "lease_expires_at",
    ):
        op.create_index(
            f"ix_semantic_inventory_jobs_{column}",
            "semantic_inventory_jobs",
            [column],
        )

    op.create_table(
        "semantic_inventory_job_items",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("job_id", _uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("table_name", sa.String(512), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("phase", sa.String(20), nullable=False, server_default="structure"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column(
            "retryable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("code", sa.String(80)),
        sa.Column("message", sa.Text()),
        sa.Column("profile_result", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("recommendation_batch_id", _uuid()),
        sa.Column("candidate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["job_id"], ["semantic_inventory_jobs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "job_id",
            "table_name",
            name="uq_semantic_inventory_job_table",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_semantic_inventory_item_status",
        ),
        sa.CheckConstraint(
            "phase IN ('structure', 'sample', 'recommend', 'complete')",
            name="ck_semantic_inventory_item_phase",
        ),
        sa.CheckConstraint(
            "ordinal >= 0",
            name="ck_semantic_inventory_item_ordinal",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_semantic_inventory_item_attempt_count",
        ),
        sa.CheckConstraint(
            "candidate_count >= 0",
            name="ck_semantic_inventory_item_candidate_count",
        ),
        *_timestamps(),
    )
    for column in (
        "job_id",
        "status",
        "next_attempt_at",
        "recommendation_batch_id",
    ):
        op.create_index(
            f"ix_semantic_inventory_job_items_{column}",
            "semantic_inventory_job_items",
            [column],
        )


def downgrade() -> None:
    op.drop_table("semantic_inventory_job_items")
    op.drop_table("semantic_inventory_jobs")
