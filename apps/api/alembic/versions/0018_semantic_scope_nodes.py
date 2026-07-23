"""add hierarchical semantic scope nodes

Revision ID: 0018_semantic_scope_nodes
Revises: 0017_semantic_validation_jobs
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0018_semantic_scope_nodes"
down_revision: str | None = "0017_semantic_validation_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> sa.types.TypeEngine:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "semantic_scope_nodes",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("parent_id", _uuid()),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("stable_key", sa.String(255), nullable=False),
        sa.Column("business_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("source_logical_name", sa.String(255)),
        sa.Column("table_or_view", sa.String(255)),
        sa.Column("context_facts", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
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
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["semantic_scope_nodes.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "project_id",
            "stable_key",
            name="uq_semantic_scope_project_stable_key",
        ),
        sa.CheckConstraint(
            "kind IN ('project', 'source', 'table', 'context', 'period')",
            name="ck_semantic_scope_kind",
        ),
        sa.CheckConstraint(
            "(kind = 'project' AND parent_id IS NULL) OR "
            "(kind != 'project' AND parent_id IS NOT NULL)",
            name="ck_semantic_scope_parent_shape",
        ),
        sa.CheckConstraint(
            "kind != 'table' OR "
            "(source_logical_name IS NOT NULL AND table_or_view IS NOT NULL)",
            name="ck_semantic_scope_table_binding",
        ),
    )
    op.create_index(
        "ix_semantic_scope_nodes_project_id",
        "semantic_scope_nodes",
        ["project_id"],
    )
    op.create_index(
        "ix_semantic_scope_nodes_parent_id",
        "semantic_scope_nodes",
        ["parent_id"],
    )
    op.create_index(
        "ix_semantic_scope_nodes_kind",
        "semantic_scope_nodes",
        ["kind"],
    )
    op.create_index(
        "ix_semantic_scope_nodes_is_active",
        "semantic_scope_nodes",
        ["is_active"],
    )

    bind = op.get_bind()
    recreate = "always" if bind.dialect.name == "sqlite" else "auto"
    with op.batch_alter_table(
        "semantic_entries",
        recreate=recreate,
        naming_convention={
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
        },
    ) as batch_op:
        batch_op.add_column(sa.Column("scope_id", _uuid()))
        batch_op.create_foreign_key(
            "fk_semantic_entries_scope_id",
            "semantic_scope_nodes",
            ["scope_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_semantic_entries_scope_id", ["scope_id"])


def downgrade() -> None:
    bind = op.get_bind()
    recreate = "always" if bind.dialect.name == "sqlite" else "auto"
    with op.batch_alter_table(
        "semantic_entries",
        recreate=recreate,
        naming_convention={
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
        },
    ) as batch_op:
        batch_op.drop_index("ix_semantic_entries_scope_id")
        batch_op.drop_constraint("fk_semantic_entries_scope_id", type_="foreignkey")
        batch_op.drop_column("scope_id")
    op.drop_table("semantic_scope_nodes")
