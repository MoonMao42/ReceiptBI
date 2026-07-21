"""track whether project knowledge has a verified execution path

Revision ID: 0006_semantic_execution_state
Revises: 0005_correction_target_key
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_semantic_execution_state"
down_revision: str | None = "0005_correction_target_key"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "semantic_entries",
        sa.Column(
            "execution_state",
            sa.String(30),
            nullable=False,
            server_default="definition_only",
        ),
    )
    op.add_column(
        "semantic_entries",
        sa.Column("execution_details", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.execute(
        "UPDATE semantic_entries "
        "SET execution_state = 'needs_validation' "
        "WHERE definition IS NOT NULL AND validity != 'stale'"
    )


def downgrade() -> None:
    op.drop_column("semantic_entries", "execution_details")
    op.drop_column("semantic_entries", "execution_state")
