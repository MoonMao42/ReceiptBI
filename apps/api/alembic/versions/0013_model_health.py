"""persist model completion health

Revision ID: 0013_model_health
Revises: 0012_retire_legacy_settings
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013_model_health"
down_revision: str | None = "0012_retire_legacy_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "models",
        sa.Column(
            "health_status",
            sa.String(length=20),
            nullable=False,
            server_default="unknown",
        ),
    )
    op.add_column(
        "models",
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "models",
        sa.Column("last_error_category", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "models",
        sa.Column("last_response_time_ms", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("models", "last_response_time_ms")
    op.drop_column("models", "last_error_category")
    op.drop_column("models", "last_checked_at")
    op.drop_column("models", "health_status")
