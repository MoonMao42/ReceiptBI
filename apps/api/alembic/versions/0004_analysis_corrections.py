"""persist report corrections

Revision ID: 0004_analysis_corrections
Revises: 0003_typed_semantic_relationships
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004_analysis_corrections"
down_revision: str | None = "0003_typed_semantic_relationships"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> sa.types.TypeEngine:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "analysis_corrections",
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("analysis_run_id", _uuid(), nullable=False),
        sa.Column("semantic_entry_id", _uuid(), nullable=True),
        sa.Column("correction_type", sa.String(30), server_default="business_rule", nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("scope", sa.String(20), server_default="run", nullable=False),
        sa.Column("state", sa.String(20), server_default="recorded", nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("evidence", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["analysis_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["semantic_entry_id"], ["semantic_entries.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "project_id",
            "analysis_run_id",
            "fingerprint",
            name="uq_analysis_correction_run_fingerprint",
        ),
    )
    op.create_index(
        "ix_analysis_corrections_project_id", "analysis_corrections", ["project_id"]
    )
    op.create_index(
        "ix_analysis_corrections_analysis_run_id",
        "analysis_corrections",
        ["analysis_run_id"],
    )
    op.create_index(
        "ix_analysis_corrections_semantic_entry_id",
        "analysis_corrections",
        ["semantic_entry_id"],
    )
    op.create_index("ix_analysis_corrections_state", "analysis_corrections", ["state"])


def downgrade() -> None:
    op.drop_index("ix_analysis_corrections_state", table_name="analysis_corrections")
    op.drop_index("ix_analysis_corrections_semantic_entry_id", table_name="analysis_corrections")
    op.drop_index("ix_analysis_corrections_analysis_run_id", table_name="analysis_corrections")
    op.drop_index("ix_analysis_corrections_project_id", table_name="analysis_corrections")
    op.drop_table("analysis_corrections")
