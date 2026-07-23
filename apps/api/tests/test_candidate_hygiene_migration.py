"""One-time bounding of untouched inferred relationship candidates."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa

from app.db.tables import Base, Project, SemanticEntry, SemanticEntryRevision


def _migration_module() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0014_candidate_hygiene.py"
    )
    spec = importlib.util.spec_from_file_location("candidate_hygiene_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _definition(column: str, suffix: str) -> dict:
    return {
        "version": 1,
        "left": {
            "source_logical_name": "经营库",
            "source_kind": "connection",
            "table_or_view": f"left_{suffix}",
            "column": column,
            "data_type": "TEXT",
            "schema_signature": "a" * 64,
        },
        "right": {
            "source_logical_name": "财务库",
            "source_kind": "connection",
            "table_or_view": f"right_{suffix}",
            "column": column,
            "data_type": "TEXT",
            "schema_signature": "b" * 64,
        },
        "normalization": "exact",
        "cardinality": None,
        "default_join": "left",
        "minimum_left_match_rate": 0.8,
        "maximum_expansion_ratio": 1.2,
    }


def _snapshot(values: dict) -> dict:
    return {
        field: values[field]
        for field in (
            "key",
            "value",
            "entry_type",
            "state",
            "confidence",
            "definition",
            "validity",
            "execution_state",
            "execution_details",
            "evidence",
            "source",
            "is_active",
        )
    }


def _insert_entry(
    connection: sa.Connection,
    *,
    project_id: UUID,
    key: str,
    definition: dict,
    state: str = "candidate",
    source: str = "inferred",
    is_active: bool = True,
    validity: str = "unverified",
    evidence: list[dict] | None = None,
    actor_source: str = "system",
    mutation_kind: str = "candidate_created",
) -> UUID:
    entry_id = uuid4()
    revision_id = uuid4()
    now = datetime.now(UTC)
    values = {
        "id": entry_id,
        "project_id": project_id,
        "key": key,
        "value": "历史自动发现的同名字段关联",
        "entry_type": "relationship",
        "state": state,
        "confidence": 0.55,
        "definition": definition,
        "validity": validity,
        "execution_state": "needs_validation" if is_active else "blocked",
        "execution_details": {
            "version": 1,
            "status": "needs_validation" if is_active else "blocked",
        },
        "evidence": evidence or [{"kind": "matching_column_names"}],
        "source": source,
        "is_active": is_active,
        "revision_number": 1,
        "active_revision_id": revision_id,
        "created_at": now,
        "updated_at": now,
    }
    connection.execute(SemanticEntry.__table__.insert().values(**values))
    connection.execute(
        SemanticEntryRevision.__table__.insert().values(
            id=revision_id,
            project_id=project_id,
            semantic_entry_id=entry_id,
            revision_number=1,
            parent_revision_id=None,
            restored_from_revision_id=None,
            mutation_kind=mutation_kind,
            actor_source=actor_source,
            reason="历史候选",
            source_correction_id=None,
            snapshot=_snapshot(values),
            created_at=now,
        )
    )
    return entry_id


def test_candidate_hygiene_migration_is_bounded_governed_and_repeat_safe(
    monkeypatch: pytest.MonkeyPatch,
):
    migration = _migration_module()
    engine = sa.create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with engine.begin() as connection:
        project_id = uuid4()
        connection.execute(
            Project.__table__.insert().values(
                id=project_id,
                name="历史候选项目",
                status="active",
                extra_data={},
            )
        )
        same_group_ids = [
            _insert_entry(
                connection,
                project_id=project_id,
                key=f"relationship_candidate:storeid:same-{index:02d}",
                definition=_definition("store_id", f"same_{index:02d}"),
            )
            for index in range(9)
        ]
        for index in range(81):
            column = f"field_{index:02d}_id"
            _insert_entry(
                connection,
                project_id=project_id,
                key=f"relationship_candidate:{column}:unique-{index:02d}",
                definition=_definition(column, f"unique_{index:02d}"),
            )

        protected = {
            "confirmed": _insert_entry(
                connection,
                project_id=project_id,
                key="relationship_candidate:protected:confirmed",
                definition=_definition("confirmed_id", "confirmed"),
                state="confirmed",
            ),
            "locked": _insert_entry(
                connection,
                project_id=project_id,
                key="relationship_candidate:protected:locked",
                definition=_definition("locked_id", "locked"),
                state="locked",
            ),
            "user": _insert_entry(
                connection,
                project_id=project_id,
                key="relationship_candidate:protected:user",
                definition=_definition("user_id", "user"),
                source="user",
            ),
            "queued": _insert_entry(
                connection,
                project_id=project_id,
                key="relationship_candidate:protected:queued",
                definition=_definition("queued_id", "queued"),
                source="user",
                evidence=[
                    {"kind": "matching_column_names"},
                    {"kind": "relationship_validation_requested"},
                ],
                actor_source="user",
            ),
            "ignored": _insert_entry(
                connection,
                project_id=project_id,
                key="relationship_candidate:protected:ignored",
                definition=_definition("ignored_id", "ignored"),
                is_active=False,
                validity="stale",
                evidence=[
                    {"kind": "matching_column_names"},
                    {"kind": "semantic_candidate_ignored"},
                ],
                actor_source="user",
            ),
            "user_edited": _insert_entry(
                connection,
                project_id=project_id,
                key="relationship_candidate:protected:user-edited",
                definition=_definition("edited_id", "edited"),
                actor_source="user",
            ),
            "api_created": _insert_entry(
                connection,
                project_id=project_id,
                key="relationship_candidate:protected:api-created",
                definition=_definition("api_created_id", "api_created"),
                mutation_kind="created",
            ),
        }

        monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
        migration.upgrade()

        active_eligible = list(
            connection.execute(
                sa.select(SemanticEntry).where(
                    SemanticEntry.project_id == project_id,
                    SemanticEntry.state == "candidate",
                    SemanticEntry.source == "inferred",
                    SemanticEntry.is_active.is_(True),
                )
            ).mappings()
        )
        protected_active_ids = {
            str(protected["user_edited"]),
            str(protected["api_created"]),
        }
        bounded_active = [
            row for row in active_eligible if str(row["id"]) not in protected_active_ids
        ]
        assert len(bounded_active) == migration._PER_PROJECT_CAP
        assert all(float(row["confidence"]) > 0.55 for row in bounded_active)

        same_group_rows = list(
            connection.execute(
                sa.select(SemanticEntry).where(SemanticEntry.id.in_(same_group_ids))
            ).mappings()
        )
        assert sum(bool(row["is_active"]) for row in same_group_rows) <= migration._PER_COLUMN_CAP
        assert any(not row["is_active"] and row["validity"] == "stale" for row in same_group_rows)

        for entry_id in protected.values():
            row = (
                connection.execute(sa.select(SemanticEntry).where(SemanticEntry.id == entry_id))
                .mappings()
                .one()
            )
            assert row["revision_number"] == 1
        assert (
            connection.execute(
                sa.select(SemanticEntry.is_active).where(SemanticEntry.id == protected["ignored"])
            ).scalar_one()
            is False
        )

        revisions_after_first = connection.execute(
            sa.select(sa.func.count()).select_from(SemanticEntryRevision)
        ).scalar_one()
        heads_after_first = dict(
            connection.execute(sa.select(SemanticEntry.id, SemanticEntry.active_revision_id)).all()
        )
        migration.upgrade()
        assert (
            connection.execute(
                sa.select(sa.func.count()).select_from(SemanticEntryRevision)
            ).scalar_one()
            == revisions_after_first
        )
        assert (
            dict(
                connection.execute(
                    sa.select(SemanticEntry.id, SemanticEntry.active_revision_id)
                ).all()
            )
            == heads_after_first
        )

    engine.dispose()
