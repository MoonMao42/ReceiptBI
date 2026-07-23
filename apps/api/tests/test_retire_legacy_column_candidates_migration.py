from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from uuid import UUID, uuid4

import sqlalchemy as sa

from app.db.tables import Base, Project, SemanticEntry, SemanticEntryRevision


def _migration_module() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0019_retire_legacy_column_candidates.py"
    )
    spec = importlib.util.spec_from_file_location("retire_legacy_column_candidates", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _snapshot(values: dict) -> dict:
    fields = (
        "scope_id",
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
    return {field: values.get(field) for field in fields}


def _insert_entry(
    connection: sa.Connection,
    *,
    project_id: UUID,
    key: str,
    definition: dict | None,
    state: str = "candidate",
    source: str = "inferred",
    actor_source: str = "inferred",
    mutation_kind: str = "candidate_created",
    execution_state: str = "definition_only",
    entry_type: str | None = None,
    evidence: list[dict] | None = None,
) -> UUID:
    entry_id = uuid4()
    revision_id = uuid4()
    now = datetime.now(UTC)
    values = {
        "id": entry_id,
        "project_id": project_id,
        "scope_id": None,
        "key": key,
        "value": "旧版字段名候选",
        "entry_type": entry_type
        or ("metric" if key.startswith("metric_candidate:") else "dimension"),
        "state": state,
        "confidence": 0.65,
        "definition": definition,
        "validity": "active",
        "execution_state": execution_state,
        "execution_details": {"version": 1, "status": execution_state},
        "evidence": evidence or [{"kind": "preflight"}],
        "source": source,
        "is_active": True,
        "revision_number": 1,
        "active_revision_id": revision_id,
        "recommendation_batch_id": None,
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


def test_migration_retires_only_untouched_raw_candidates_and_is_repeat_safe(
    monkeypatch,
) -> None:
    migration = _migration_module()
    engine = sa.create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with engine.begin() as connection:
        project_id = uuid4()
        connection.execute(
            Project.__table__.insert().values(
                id=project_id,
                name="历史字段候选",
                status="active",
                extra_data={},
            )
        )
        retired = {
            _insert_entry(
                connection,
                project_id=project_id,
                key="metric_candidate:source:account_rep_name",
                definition=None,
            ),
            _insert_entry(
                connection,
                project_id=project_id,
                key="metric_candidate:source:account_rep_code",
                definition={"version": 1, "kind": "column_metric", "column": "account_rep_code"},
                execution_state="verified",
            ),
            _insert_entry(
                connection,
                project_id=project_id,
                key="grain:source",
                definition={"version": 1, "kind": "grain_key", "column": "order_id"},
            ),
        }
        retired_relationships = {
            _insert_entry(
                connection,
                project_id=project_id,
                key="relationship_candidate:legacy:untouched",
                definition={"version": 1, "kind": "relationship"},
                entry_type="relationship",
                evidence=[
                    {"kind": "matching_column_names"},
                    {"kind": "semantic_scope_reconciled"},
                ],
            ),
            _insert_entry(
                connection,
                project_id=project_id,
                key="relationship_candidate:legacy:queued",
                definition={"version": 1, "kind": "relationship"},
                source="user",
                actor_source="user",
                mutation_kind="validation_queued",
                execution_state="needs_validation",
                entry_type="relationship",
                evidence=[
                    {"kind": "matching_column_names"},
                    {"kind": "relationship_validation_requested"},
                ],
            ),
        }
        protected = {
            _insert_entry(
                connection,
                project_id=project_id,
                key="metric_candidate:source:user-edited",
                definition=None,
                actor_source="user",
            ),
            _insert_entry(
                connection,
                project_id=project_id,
                key="metric_candidate:source:api-created",
                definition=None,
                mutation_kind="created",
            ),
            _insert_entry(
                connection,
                project_id=project_id,
                key="metric_candidate:source:confirmed",
                definition=None,
                state="confirmed",
                source="user",
            ),
            _insert_entry(
                connection,
                project_id=project_id,
                key="metric_candidate:source:typed",
                definition={
                    "version": 1,
                    "kind": "aggregate_metric",
                    "operation": "sum",
                },
            ),
            _insert_entry(
                connection,
                project_id=project_id,
                key="relationship_candidate:legacy:user-edited",
                definition={"version": 1, "kind": "relationship"},
                source="user",
                actor_source="user",
                mutation_kind="user_updated",
                execution_state="needs_validation",
                entry_type="relationship",
                evidence=[{"kind": "matching_column_names"}],
            ),
            _insert_entry(
                connection,
                project_id=project_id,
                key="relationship_candidate:legacy:verified",
                definition={"version": 1, "kind": "relationship"},
                execution_state="verified",
                entry_type="relationship",
                evidence=[{"kind": "matching_column_names"}],
            ),
        }

        monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
        migration.upgrade()

        for entry_id in retired:
            row = (
                connection.execute(sa.select(SemanticEntry).where(SemanticEntry.id == entry_id))
                .mappings()
                .one()
            )
            assert row["is_active"] is False
            assert row["validity"] == "stale"
            assert row["execution_state"] == "blocked"
            assert row["revision_number"] == 2
            revision = (
                connection.execute(
                    sa.select(SemanticEntryRevision).where(
                        SemanticEntryRevision.id == row["active_revision_id"]
                    )
                )
                .mappings()
                .one()
            )
            assert revision["mutation_kind"] == "legacy_candidate_retired"

        for entry_id in retired_relationships:
            row = (
                connection.execute(sa.select(SemanticEntry).where(SemanticEntry.id == entry_id))
                .mappings()
                .one()
            )
            assert row["is_active"] is False
            assert row["validity"] == "stale"
            assert row["execution_state"] == "blocked"
            assert row["revision_number"] == 2
            revision = (
                connection.execute(
                    sa.select(SemanticEntryRevision).where(
                        SemanticEntryRevision.id == row["active_revision_id"]
                    )
                )
                .mappings()
                .one()
            )
            assert revision["mutation_kind"] == "legacy_relationship_retired"

        for entry_id in protected:
            row = (
                connection.execute(sa.select(SemanticEntry).where(SemanticEntry.id == entry_id))
                .mappings()
                .one()
            )
            assert row["is_active"] is True
            assert row["revision_number"] == 1

        revisions_after_first = connection.scalar(
            sa.select(sa.func.count()).select_from(SemanticEntryRevision)
        )
        migration.upgrade()
        assert (
            connection.scalar(sa.select(sa.func.count()).select_from(SemanticEntryRevision))
            == revisions_after_first
        )

    engine.dispose()
