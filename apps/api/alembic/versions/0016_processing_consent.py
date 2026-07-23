"""add explicit processing consent settings

Revision ID: 0016_processing_consent
Revises: 0015_editable_reports
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016_processing_consent"
down_revision: str | None = "0015_editable_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "app_settings",
        sa.Column(
            "preprocessing_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "app_settings",
        sa.Column(
            "self_analysis_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("app_settings", "self_analysis_enabled")
    op.drop_column("app_settings", "preprocessing_enabled")
