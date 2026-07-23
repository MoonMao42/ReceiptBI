from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration_module() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0022_retire_legacy_user_scope.py"
    )
    spec = importlib.util.spec_from_file_location("retire_legacy_user_scope", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _legacy_metadata() -> sa.MetaData:
    metadata = sa.MetaData()
    users = sa.Table(
        "users",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
    )
    sa.Table(
        "connections",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey(users.c.id), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
    )
    sa.Table(
        "models",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey(users.c.id), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
    )
    conversations = sa.Table(
        "conversations",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey(users.c.id), nullable=False),
        sa.Column("title", sa.String()),
    )
    sa.Index("ix_conversations_user_id", conversations.c.user_id)
    sa.Table(
        "refresh_tokens",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey(users.c.id), nullable=False),
    )
    sa.Table(
        "projects",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    return metadata


def test_upgrade_removes_legacy_ownership_without_losing_rows() -> None:
    migration = _migration_module()
    engine = sa.create_engine("sqlite://")
    metadata = _legacy_metadata()
    metadata.create_all(engine)

    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys = OFF")
        user_id = uuid4()
        row_ids = {
            "connections": uuid4(),
            "models": uuid4(),
            "conversations": uuid4(),
        }
        connection.execute(metadata.tables["users"].insert().values(id=user_id))
        connection.execute(
            metadata.tables["connections"]
            .insert()
            .values(id=row_ids["connections"], user_id=user_id, name="Warehouse")
        )
        connection.execute(
            metadata.tables["models"]
            .insert()
            .values(id=row_ids["models"], user_id=user_id, name="Analysis service")
        )
        connection.execute(
            metadata.tables["conversations"]
            .insert()
            .values(id=row_ids["conversations"], user_id=user_id, title="Investigation")
        )
        project_id = uuid4()
        connection.execute(metadata.tables["projects"].insert().values(id=project_id))

        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        migration.upgrade()

        inspector = sa.inspect(connection)
        for table_name, row_id in row_ids.items():
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            assert "user_id" not in columns
            assert (
                connection.scalar(
                    sa.select(sa.func.count())
                    .select_from(sa.table(table_name, sa.column("id")))
                    .where(sa.column("id") == row_id)
                )
                == 1
            )
        assert "ix_conversations_user_id" not in {
            index["name"] for index in inspector.get_indexes("conversations")
        }
        assert {"users", "refresh_tokens"}.isdisjoint(inspector.get_table_names())
        project_columns = {column["name"]: column for column in inspector.get_columns("projects")}
        assert project_columns["created_at"]["nullable"] is False
        assert project_columns["updated_at"]["nullable"] is False
        project_timestamps = connection.execute(
            sa.select(
                metadata.tables["projects"].c.created_at,
                metadata.tables["projects"].c.updated_at,
            ).where(metadata.tables["projects"].c.id == project_id)
        ).one()
        assert project_timestamps.created_at is not None
        assert project_timestamps.updated_at is not None

    engine.dispose()


def test_upgrade_is_a_noop_for_the_single_workspace_schema() -> None:
    migration = _migration_module()
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    for table_name in migration._USER_SCOPED_TABLES:
        sa.Table(
            table_name,
            metadata,
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("name", sa.String()),
        )
    metadata.create_all(engine)

    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

        inspector = sa.inspect(connection)
        for table_name in migration._USER_SCOPED_TABLES:
            assert {column["name"] for column in inspector.get_columns(table_name)} == {
                "id",
                "name",
            }

    engine.dispose()


def test_downgrade_fails_before_recording_a_false_legacy_schema() -> None:
    migration = _migration_module()

    with pytest.raises(RuntimeError, match="cannot be downgraded safely"):
        migration.downgrade()
