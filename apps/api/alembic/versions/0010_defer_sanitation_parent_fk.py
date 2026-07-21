"""defer sanitation revision parent foreign key

Revision ID: 0010_defer_sanitation_parent_fk
Revises: 0009_cleanup_orphan_sanitation
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "0010_defer_sanitation_parent_fk"
down_revision: str | None = "0009_cleanup_orphan_sanitation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "sanitation_recipe_revisions"
PARENT_COLUMN = "parent_revision_id"
PARENT_FK_NAME = "fk_sanitation_recipe_revisions_parent_revision_id"
SQLITE_REFLECTED_PARENT_FK_NAME = (
    "fk_sanitation_recipe_revisions_parent_revision_id_sanitation_recipe_revisions"
)
SQLITE_NAMING_CONVENTION = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}
SQLITE_PARENT_LINKS_TABLE = "_receiptbi_sanitation_parent_links"


def _parent_foreign_key(bind) -> dict[str, Any]:
    matches = [
        foreign_key
        for foreign_key in sa.inspect(bind).get_foreign_keys(TABLE_NAME)
        if foreign_key.get("constrained_columns") == [PARENT_COLUMN]
    ]
    if len(matches) != 1:
        raise RuntimeError(
            "sanitation revision parent foreign key is missing or ambiguous; refusing migration"
        )
    return matches[0]


def _already_deferred(foreign_key: dict[str, Any]) -> bool:
    options = foreign_key.get("options") or {}
    return bool(options.get("deferrable")) and str(options.get("initially") or "").upper() == (
        "DEFERRED"
    )


def _create_parent_foreign_key(batch_op) -> None:
    batch_op.create_foreign_key(
        PARENT_FK_NAME,
        TABLE_NAME,
        [PARENT_COLUMN],
        ["id"],
        ondelete="NO ACTION",
        deferrable=True,
        initially="DEFERRED",
    )


def _rebuild_sqlite_parent_foreign_key(
    bind,
    *,
    existing_name: str,
    deferred: bool,
) -> None:
    # SQLite cannot drop a self-referenced table while its old immediate
    # RESTRICT constraint still has live links. Preserve those links outside
    # the table, detach them, rebuild, then restore them under the new
    # constraint. The surrounding Alembic transaction makes this atomic.
    bind.exec_driver_sql(
        f"CREATE TEMPORARY TABLE {SQLITE_PARENT_LINKS_TABLE} "
        "(id PRIMARY KEY, parent_revision_id NOT NULL)"
    )
    bind.exec_driver_sql(
        f"INSERT INTO {SQLITE_PARENT_LINKS_TABLE} (id, parent_revision_id) "
        f"SELECT id, {PARENT_COLUMN} FROM {TABLE_NAME} "
        f"WHERE {PARENT_COLUMN} IS NOT NULL"
    )
    expected_links = bind.exec_driver_sql(
        f"SELECT COUNT(*) FROM {SQLITE_PARENT_LINKS_TABLE}"
    ).scalar_one()
    bind.exec_driver_sql(f"UPDATE {TABLE_NAME} SET {PARENT_COLUMN}=NULL")

    with op.batch_alter_table(
        TABLE_NAME,
        recreate="always",
        naming_convention=SQLITE_NAMING_CONVENTION,
    ) as batch_op:
        batch_op.drop_constraint(existing_name, type_="foreignkey")
        if deferred:
            _create_parent_foreign_key(batch_op)
        else:
            batch_op.create_foreign_key(
                PARENT_FK_NAME,
                TABLE_NAME,
                [PARENT_COLUMN],
                ["id"],
                ondelete="RESTRICT",
            )

    bind.exec_driver_sql(
        f"UPDATE {TABLE_NAME} "
        f"SET {PARENT_COLUMN} = ("
        f"SELECT links.parent_revision_id FROM {SQLITE_PARENT_LINKS_TABLE} AS links "
        f"WHERE links.id = {TABLE_NAME}.id"
        ") "
        f"WHERE EXISTS ("
        f"SELECT 1 FROM {SQLITE_PARENT_LINKS_TABLE} AS links "
        f"WHERE links.id = {TABLE_NAME}.id"
        ")"
    )
    restored_links = bind.exec_driver_sql(
        f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE {PARENT_COLUMN} IS NOT NULL"
    ).scalar_one()
    if restored_links != expected_links:
        raise RuntimeError("sanitation revision parent links were not fully restored")
    bind.exec_driver_sql(f"DROP TABLE {SQLITE_PARENT_LINKS_TABLE}")


def upgrade() -> None:
    bind = op.get_bind()
    parent_foreign_key = _parent_foreign_key(bind)
    if _already_deferred(parent_foreign_key):
        return

    dialect = bind.dialect.name
    if dialect == "sqlite":
        existing_name = parent_foreign_key.get("name") or SQLITE_REFLECTED_PARENT_FK_NAME
        _rebuild_sqlite_parent_foreign_key(
            bind,
            existing_name=existing_name,
            deferred=True,
        )
        return

    if dialect == "postgresql":
        existing_name = parent_foreign_key.get("name")
        if not existing_name:
            raise RuntimeError(
                "sanitation revision parent foreign key has no name; refusing migration"
            )
        op.drop_constraint(existing_name, TABLE_NAME, type_="foreignkey")
        op.create_foreign_key(
            PARENT_FK_NAME,
            TABLE_NAME,
            [PARENT_COLUMN],
            ["id"],
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        )
        return

    raise RuntimeError(
        f"metadata database dialect {dialect} does not support the required deferred "
        "sanitation parent constraint"
    )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "sqlite":
        parent_foreign_key = _parent_foreign_key(bind)
        existing_name = parent_foreign_key.get("name") or SQLITE_REFLECTED_PARENT_FK_NAME
        _rebuild_sqlite_parent_foreign_key(
            bind,
            existing_name=existing_name,
            deferred=False,
        )
        return
    if dialect == "postgresql":
        op.drop_constraint(PARENT_FK_NAME, TABLE_NAME, type_="foreignkey")
        op.create_foreign_key(
            PARENT_FK_NAME,
            TABLE_NAME,
            [PARENT_COLUMN],
            ["id"],
            ondelete="RESTRICT",
        )
        return
    raise RuntimeError(f"unsupported metadata database dialect: {dialect}")
