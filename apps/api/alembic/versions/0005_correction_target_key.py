"""bind report corrections to stable project concepts

Revision ID: 0005_correction_target_key
Revises: 0004_analysis_corrections
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_correction_target_key"
down_revision: str | None = "0004_analysis_corrections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "analysis_corrections",
        sa.Column("target_key", sa.String(160), nullable=True),
    )
    op.create_index(
        "ix_analysis_corrections_target_key",
        "analysis_corrections",
        ["target_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_analysis_corrections_target_key", table_name="analysis_corrections")
    op.drop_column("analysis_corrections", "target_key")
