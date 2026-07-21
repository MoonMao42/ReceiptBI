"""typed semantic relationships

Revision ID: 0003_typed_semantic_relationships
Revises: 0002_zero_config_analyst
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_typed_semantic_relationships"
down_revision: str | None = "0002_zero_config_analyst"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("semantic_entries", sa.Column("definition", sa.JSON(), nullable=True))
    op.add_column(
        "semantic_entries",
        sa.Column("validity", sa.String(20), server_default="active", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("semantic_entries", "validity")
    op.drop_column("semantic_entries", "definition")
