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
        / "0020_retire_stale_semantic_recommendations.py"
    )
    spec = importlib.util.spec_from_file_location(
        "retire_stale_semantic_recommendations", path
    )
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


def _insert_recommendation(
    connection: sa.Connection,
    *,
    project_id: UUID,
    suffix: str,
    evidence: list[dict] | None = None,
    state: str = "candidate",
    source: str = "inferred",
    execution_state: str = "needs_validation",
    actor_source: str = "inferred",
    mutation_kind: str = "recommendation_created",
) -> UUID:
    entry_id = uuid4()
    revision_id = uuid4()
    now = datetime.now(UTC)
    values = {
        "id": entry_id,
        "project_id": project_id,
        "scope_id": None,
        "key": f"semantic_recommendation:dimension:{suffix}",
        "value": "旧建议",
        "entry_type": "dimension",
        "state": state,
        "confidence": 0.6,
        "definition": {
            "version": 1,
            "kind": "dimension",
            "business_name": "listing time",
        },
        "validity": "unverified",
        "execution_state": execution_state,
        "execution_details": {"version": 1, "status": execution_state},
        "evidence": evidence
        or [
            {"kind": "profile_dimension_role", "generated_by": "deterministic_profile"},
            {"kind": "semantic_recommendation_batch", "generated_by": "preflight"},
        ],
        "source": source,
        "is_active": True,
        "revision_number": 1,
        "active_revision_id": revision_id,
        "recommendation_batch_id": uuid4(),
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
            reason="历史建议",
            source_correction_id=None,
            snapshot=_snapshot(values),
            created_at=now,
        )
    )
    return entry_id


def test_migration_retires_only_untouched_pre_localization_recommendations(
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
                name="语义治理迁移",
                status="active",
                extra_data={},
            )
        )
        retired_id = _insert_recommendation(
            connection,
            project_id=project_id,
            suffix="untouched",
        )
        protected_ids = {
            _insert_recommendation(
                connection,
                project_id=project_id,
                suffix="ai-localized",
                evidence=[
                    {"kind": "semantic_recommendation_batch", "generated_by": "preflight"},
                    {"kind": "model_presentation_enhancement"},
                ],
            ),
            _insert_recommendation(
                connection,
                project_id=project_id,
                suffix="user-reviewed",
                actor_source="user",
                mutation_kind="human_attested",
            ),
            _insert_recommendation(
                connection,
                project_id=project_id,
                suffix="verified",
                execution_state="verified",
            ),
            _insert_recommendation(
                connection,
                project_id=project_id,
                suffix="confirmed",
                state="confirmed",
                source="user",
            ),
        }

        monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
        migration.upgrade()

        retired = connection.execute(
            sa.select(SemanticEntry).where(SemanticEntry.id == retired_id)
        ).mappings().one()
        assert retired["is_active"] is False
        assert retired["validity"] == "stale"
        assert retired["execution_state"] == "blocked"
        assert retired["revision_number"] == 2
        revision = connection.execute(
            sa.select(SemanticEntryRevision).where(
                SemanticEntryRevision.id == retired["active_revision_id"]
            )
        ).mappings().one()
        assert revision["mutation_kind"] == "stale_recommendation_retired"
        assert revision["parent_revision_id"] is not None

        for entry_id in protected_ids:
            protected = connection.execute(
                sa.select(SemanticEntry).where(SemanticEntry.id == entry_id)
            ).mappings().one()
            assert protected["is_active"] is True
            assert protected["revision_number"] == 1

        revision_count = connection.scalar(
            sa.select(sa.func.count()).select_from(SemanticEntryRevision)
        )
        migration.upgrade()
        assert connection.scalar(
            sa.select(sa.func.count()).select_from(SemanticEntryRevision)
        ) == revision_count

    engine.dispose()
