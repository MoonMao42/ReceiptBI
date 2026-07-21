"""persist opaque report-correction target references

Revision ID: 0011_correction_target_ref
Revises: 0010_defer_sanitation_parent_fk
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_correction_target_ref"
down_revision: str | None = "0010_defer_sanitation_parent_fk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "analysis_corrections",
        sa.Column("target_ref", sa.String(96), nullable=True),
    )
    op.create_index(
        "ix_analysis_corrections_target_ref",
        "analysis_corrections",
        ["target_ref"],
    )


def downgrade() -> None:
    op.drop_index("ix_analysis_corrections_target_ref", table_name="analysis_corrections")
    op.drop_column("analysis_corrections", "target_ref")
