"""retire legacy multi-user ownership columns

Revision ID: 0022_retire_legacy_user_scope
Revises: 0021_semantic_inventory_jobs
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0022_retire_legacy_user_scope"
down_revision: str | None = "0021_semantic_inventory_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_USER_SCOPED_TABLES: tuple[str, ...] = ("connections", "models", "conversations")
_LEGACY_AUTH_TABLES: tuple[str, ...] = ("refresh_tokens", "users")
_TIMESTAMPED_TABLES: tuple[str, ...] = (
    "analysis_corrections",
    "analysis_runs",
    "artifacts",
    "preflight_reports",
    "project_data_sources",
    "projects",
    "sanitation_recipes",
    "semantic_entries",
)


def _drop_user_scope(table_name: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns(table_name)}
    if "user_id" not in columns:
        return

    indexes = {index["name"] for index in inspector.get_indexes(table_name) if index.get("name")}
    user_index = f"ix_{table_name}_user_id"

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(
            table_name,
            recreate="always",
            naming_convention={"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"},
        ) as batch_op:
            if user_index in indexes:
                batch_op.drop_index(user_index)
            batch_op.drop_column("user_id")
        return

    if user_index in indexes:
        op.drop_index(user_index, table_name=table_name)
    op.drop_column(table_name, "user_id")


def _harden_timestamps(table_name: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return

    columns = {column["name"]: column for column in inspector.get_columns(table_name)}
    nullable_columns = [
        column_name
        for column_name in ("created_at", "updated_at")
        if column_name in columns and columns[column_name]["nullable"]
    ]
    if not nullable_columns:
        return

    table = sa.table(
        table_name,
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    bind.execute(
        table.update().values(
            created_at=sa.func.coalesce(table.c.created_at, sa.func.now()),
            updated_at=sa.func.coalesce(
                table.c.updated_at,
                table.c.created_at,
                sa.func.now(),
            ),
        )
    )

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(table_name, recreate="always") as batch_op:
            for column_name in nullable_columns:
                batch_op.alter_column(
                    column_name,
                    existing_type=sa.DateTime(timezone=True),
                    nullable=False,
                )
        return

    for column_name in nullable_columns:
        op.alter_column(
            table_name,
            column_name,
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
        )


def upgrade() -> None:
    for table_name in _USER_SCOPED_TABLES:
        _drop_user_scope(table_name)
    for table_name in _LEGACY_AUTH_TABLES:
        if table_name in sa.inspect(op.get_bind()).get_table_names():
            op.drop_table(table_name)
    for table_name in _TIMESTAMPED_TABLES:
        _harden_timestamps(table_name)


def downgrade() -> None:
    # Ownership data cannot be reconstructed after the product moved to a
    # single-workspace model. A destructive downgrade would invent owners.
    raise RuntimeError("0022_retire_legacy_user_scope cannot be downgraded safely")
