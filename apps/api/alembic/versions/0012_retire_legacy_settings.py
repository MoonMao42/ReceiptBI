"""retire legacy prompt, schema, semantic, and demo state

Revision ID: 0012_retire_legacy_settings
Revises: 0011_correction_target_ref
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0012_retire_legacy_settings"
down_revision: str | None = "0011_correction_target_ref"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> sa.types.TypeEngine:
    return postgresql.UUID(as_uuid=True)


connections = sa.table(
    "connections",
    sa.column("id", _uuid()),
    sa.column("name", sa.String()),
    sa.column("driver", sa.String()),
    sa.column("database_name", sa.String()),
)
app_settings = sa.table(
    "app_settings",
    sa.column("default_connection_id", _uuid()),
)
conversations = sa.table(
    "conversations",
    sa.column("id", _uuid()),
    sa.column("connection_id", _uuid()),
    sa.column("extra_data", sa.JSON()),
)
messages = sa.table(
    "messages",
    sa.column("id", _uuid()),
    sa.column("extra_data", sa.JSON()),
)
projects = sa.table(
    "projects",
    sa.column("id", _uuid()),
    sa.column("name", sa.String()),
    sa.column("description", sa.Text()),
    sa.column("status", sa.String()),
    sa.column("extra_data", sa.JSON()),
)
project_data_sources = sa.table(
    "project_data_sources",
    sa.column("id", _uuid()),
    sa.column("project_id", _uuid()),
    sa.column("connection_id", _uuid()),
    sa.column("kind", sa.String()),
    sa.column("name", sa.String()),
    sa.column("format", sa.String()),
    sa.column("source_uri", sa.Text()),
    sa.column("working_uri", sa.Text()),
    sa.column("status", sa.String()),
    sa.column("profile_data", sa.JSON()),
)
preflight_reports = sa.table(
    "preflight_reports",
    sa.column("id", _uuid()),
    sa.column("project_id", _uuid()),
    sa.column("data_source_id", _uuid()),
    sa.column("source_snapshot", sa.JSON()),
)
sanitation_recipes = sa.table(
    "sanitation_recipes",
    sa.column("id", _uuid()),
    sa.column("project_id", _uuid()),
    sa.column("data_source_id", _uuid()),
)
sanitation_recipe_revisions = sa.table(
    "sanitation_recipe_revisions",
    sa.column("id", _uuid()),
    sa.column("recipe_id", _uuid()),
    sa.column("revision_number", sa.Integer()),
)
analysis_corrections = sa.table(
    "analysis_corrections",
    sa.column("project_id", _uuid()),
)
artifacts = sa.table(
    "artifacts",
    sa.column("project_id", _uuid()),
)
analysis_runs = sa.table(
    "analysis_runs",
    sa.column("project_id", _uuid()),
)
semantic_entries = sa.table(
    "semantic_entries",
    sa.column("id", _uuid()),
    sa.column("project_id", _uuid()),
    sa.column("key", sa.String()),
    sa.column("value", sa.Text()),
    sa.column("entry_type", sa.String()),
    sa.column("state", sa.String()),
    sa.column("confidence", sa.Float()),
    sa.column("definition", sa.JSON()),
    sa.column("validity", sa.String()),
    sa.column("execution_state", sa.String()),
    sa.column("execution_details", sa.JSON()),
    sa.column("evidence", sa.JSON()),
    sa.column("source", sa.String()),
    sa.column("is_active", sa.Boolean()),
    sa.column("revision_number", sa.Integer()),
    sa.column("active_revision_id", _uuid()),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("updated_at", sa.DateTime(timezone=True)),
)
semantic_entry_revisions = sa.table(
    "semantic_entry_revisions",
    sa.column("id", _uuid()),
    sa.column("project_id", _uuid()),
    sa.column("semantic_entry_id", _uuid()),
    sa.column("revision_number", sa.Integer()),
    sa.column("parent_revision_id", _uuid()),
    sa.column("restored_from_revision_id", _uuid()),
    sa.column("mutation_kind", sa.String()),
    sa.column("actor_source", sa.String()),
    sa.column("reason", sa.Text()),
    sa.column("source_correction_id", sa.String()),
    sa.column("snapshot", sa.JSON()),
    sa.column("created_at", sa.DateTime(timezone=True)),
)
semantic_terms = sa.table(
    "semantic_terms",
    sa.column("id", _uuid()),
    sa.column("connection_id", _uuid()),
    sa.column("term", sa.String()),
    sa.column("expression", sa.Text()),
    sa.column("term_type", sa.String()),
    sa.column("description", sa.Text()),
    sa.column("examples", sa.JSON()),
    sa.column("is_active", sa.Boolean()),
    sa.column("created_at", sa.DateTime(timezone=True)),
)
table_relationships = sa.table(
    "table_relationships",
    sa.column("id", _uuid()),
    sa.column("connection_id", _uuid()),
    sa.column("source_table", sa.String()),
    sa.column("source_column", sa.String()),
    sa.column("target_table", sa.String()),
    sa.column("target_column", sa.String()),
    sa.column("relationship_type", sa.String()),
    sa.column("join_type", sa.String()),
    sa.column("description", sa.Text()),
    sa.column("is_active", sa.Boolean()),
    sa.column("created_at", sa.DateTime(timezone=True)),
)
prompts = sa.table(
    "prompts",
    sa.column("id", _uuid()),
    sa.column("name", sa.String()),
    sa.column("content", sa.Text()),
    sa.column("description", sa.Text()),
    sa.column("version", sa.Integer()),
    sa.column("is_active", sa.Boolean()),
    sa.column("is_default", sa.Boolean()),
    sa.column("parent_id", _uuid()),
    sa.column("created_at", sa.DateTime(timezone=True)),
)


def _id(value: object) -> str:
    return str(value)


def _is_demo_database_path(value: object) -> bool:
    raw = str(value or "").strip()
    if raw == "__DEMO_DB_PATH__":
        return True
    return raw.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1].casefold() == "demo.db"


def _demo_connection_ids(bind: sa.Connection) -> set[str]:
    rows = bind.execute(
        sa.select(
            connections.c.id,
            connections.c.name,
            connections.c.driver,
            connections.c.database_name,
        ).where(connections.c.name == "Sample Database")
    ).mappings()
    return {
        _id(row["id"])
        for row in rows
        if str(row["driver"] or "").casefold() == "sqlite"
        and _is_demo_database_path(row["database_name"])
    }


def _is_system_demo_project(row: Mapping[str, Any]) -> bool:
    extra_data = row.get("extra_data")
    if not isinstance(extra_data, dict):
        return False
    if any(
        extra_data.get(key) is True
        for key in (
            "is_demo",
            "demo_project",
            "system_demo",
            "system_sample",
            "sample_project",
        )
    ):
        return True
    origin = str(
        extra_data.get("origin")
        or extra_data.get("source")
        or extra_data.get("project_kind")
        or ""
    ).casefold()
    owner = str(extra_data.get("created_by") or extra_data.get("owner") or "").casefold()
    return origin in {"demo", "sample", "system_demo", "sample_database"} and (
        owner == "system" or extra_data.get("system_owned") is True
    )


def _delete_system_demo_project(bind: sa.Connection, project_id: object) -> None:
    bind.execute(analysis_corrections.delete().where(analysis_corrections.c.project_id == project_id))
    bind.execute(artifacts.delete().where(artifacts.c.project_id == project_id))
    bind.execute(analysis_runs.delete().where(analysis_runs.c.project_id == project_id))
    entry_ids = list(
        bind.execute(
            sa.select(semantic_entries.c.id).where(semantic_entries.c.project_id == project_id)
        ).scalars()
    )
    for entry_id in entry_ids:
        _delete_semantic_entry_history(bind, entry_id)

    recipe_ids = list(
        bind.execute(
            sa.select(sanitation_recipes.c.id).where(
                sanitation_recipes.c.project_id == project_id
            )
        ).scalars()
    )
    for recipe_id in recipe_ids:
        _delete_recipe_history(bind, recipe_id)
    bind.execute(sanitation_recipes.delete().where(sanitation_recipes.c.project_id == project_id))
    bind.execute(preflight_reports.delete().where(preflight_reports.c.project_id == project_id))
    bind.execute(
        project_data_sources.delete().where(project_data_sources.c.project_id == project_id)
    )
    bind.execute(projects.delete().where(projects.c.id == project_id))


def _normalized_uuid_text(value: object) -> str:
    return str(value or "").strip().replace("-", "").casefold()


def _evidence_references_demo(value: Any, demo_source_ids: set[str]) -> bool:
    if isinstance(value, str):
        normalized_name = value.strip().casefold()
        if normalized_name == "sample database" or normalized_name.startswith(
            "sample database."
        ):
            return True
        normalized = _normalized_uuid_text(value)
        return bool(normalized) and normalized in demo_source_ids
    if isinstance(value, dict):
        return any(_evidence_references_demo(item, demo_source_ids) for item in value.values())
    if isinstance(value, list):
        return any(_evidence_references_demo(item, demo_source_ids) for item in value)
    return False


def _delete_semantic_entry_history(bind: sa.Connection, entry_id: object) -> None:
    revision_ids = list(
        bind.execute(
            sa.select(semantic_entry_revisions.c.id)
            .where(semantic_entry_revisions.c.semantic_entry_id == entry_id)
            .order_by(semantic_entry_revisions.c.revision_number.desc())
        ).scalars()
    )
    for revision_id in revision_ids:
        bind.execute(
            semantic_entry_revisions.delete().where(
                semantic_entry_revisions.c.id == revision_id
            )
        )
    bind.execute(semantic_entries.delete().where(semantic_entries.c.id == entry_id))


def _delete_recipe_history(bind: sa.Connection, recipe_id: object) -> None:
    revision_ids = list(
        bind.execute(
            sa.select(sanitation_recipe_revisions.c.id)
            .where(sanitation_recipe_revisions.c.recipe_id == recipe_id)
            .order_by(sanitation_recipe_revisions.c.revision_number.desc())
        ).scalars()
    )
    for revision_id in revision_ids:
        bind.execute(
            sanitation_recipe_revisions.delete().where(
                sanitation_recipe_revisions.c.id == revision_id
            )
        )


def _retire_demo_semantic_entries(
    bind: sa.Connection,
    demo_source_ids: Sequence[object],
) -> None:
    normalized_source_ids = {_normalized_uuid_text(value) for value in demo_source_ids}
    if not normalized_source_ids:
        return
    rows = list(bind.execute(sa.select(semantic_entries)).mappings())
    for row in rows:
        evidence = list(row["evidence"] or [])
        if not _evidence_references_demo(evidence, normalized_source_ids):
            continue
        protected = row["state"] in {"confirmed", "locked"} or row["source"] == "user"
        if not protected and (
            row["state"] == "candidate" or row["source"] in {"inferred", "verified_analysis"}
        ):
            _delete_semantic_entry_history(bind, row["id"])
            continue
        if not protected:
            continue

        migration_evidence = {
            "kind": "demo_source_retired",
            "reason": "自动注入的 Sample Database 已退役；该定义需重新绑定真实数据源后验证",
            "demo_source_ids": sorted(_id(value) for value in demo_source_ids),
        }
        updated_evidence = [*evidence, migration_evidence]
        execution_details = dict(row["execution_details"] or {})
        execution_details["blocked_reason"] = "demo_source_retired"
        revision_id = uuid4()
        revision_number = int(row["revision_number"] or 0) + 1
        snapshot = {
            "key": row["key"],
            "value": row["value"],
            "entry_type": row["entry_type"],
            "state": row["state"],
            "confidence": row["confidence"],
            "definition": row["definition"],
            "validity": "stale",
            "execution_state": "blocked",
            "execution_details": execution_details,
            "evidence": updated_evidence,
            "source": row["source"],
            "is_active": row["is_active"] is not False,
        }
        bind.execute(
            semantic_entry_revisions.insert().values(
                id=revision_id,
                project_id=row["project_id"],
                semantic_entry_id=row["id"],
                revision_number=revision_number,
                parent_revision_id=row["active_revision_id"],
                restored_from_revision_id=None,
                mutation_kind="demo_source_retired",
                actor_source="system",
                reason="Sample Database 退役，旧定义等待重新绑定真实数据源",
                source_correction_id=None,
                snapshot=snapshot,
                created_at=datetime.now(UTC),
            )
        )
        bind.execute(
            semantic_entries.update()
            .where(semantic_entries.c.id == row["id"])
            .values(
                validity="stale",
                execution_state="blocked",
                execution_details=execution_details,
                evidence=updated_evidence,
                revision_number=revision_number,
                active_revision_id=revision_id,
                updated_at=datetime.now(UTC),
            )
        )


def _remove_demo_state(bind: sa.Connection, demo_ids: set[str]) -> None:
    if not demo_ids:
        return
    all_demo_ids = [
        row_id
        for row_id in bind.execute(sa.select(connections.c.id)).scalars()
        if _id(row_id) in demo_ids
    ]
    if not all_demo_ids:
        return

    demo_sources = list(
        bind.execute(
            sa.select(
                project_data_sources.c.id,
                project_data_sources.c.project_id,
            ).where(project_data_sources.c.connection_id.in_(all_demo_ids))
        ).mappings()
    )
    demo_source_ids = [row["id"] for row in demo_sources]
    affected_project_ids = {row["project_id"] for row in demo_sources}

    if demo_source_ids:
        _retire_demo_semantic_entries(bind, demo_source_ids)
        bind.execute(
            preflight_reports.delete().where(
                preflight_reports.c.data_source_id.in_(demo_source_ids)
            )
        )
        demo_recipe_ids = list(
            bind.execute(
                sa.select(sanitation_recipes.c.id).where(
                    sanitation_recipes.c.data_source_id.in_(demo_source_ids)
                )
            ).scalars()
        )
        for recipe_id in demo_recipe_ids:
            _delete_recipe_history(bind, recipe_id)
        bind.execute(
            sanitation_recipes.delete().where(
                sanitation_recipes.c.data_source_id.in_(demo_source_ids)
            )
        )
        bind.execute(
            project_data_sources.delete().where(project_data_sources.c.id.in_(demo_source_ids))
        )

    for project_id in affected_project_ids:
        has_other_sources = bind.execute(
            sa.select(project_data_sources.c.id)
            .where(project_data_sources.c.project_id == project_id)
            .limit(1)
        ).first()
        if has_other_sources:
            continue
        project_row = bind.execute(
            sa.select(
                projects.c.id,
                projects.c.name,
                projects.c.description,
                projects.c.extra_data,
            ).where(projects.c.id == project_id)
        ).mappings().first()
        if project_row is not None and _is_system_demo_project(project_row):
            _delete_system_demo_project(bind, project_id)

    bind.execute(
        app_settings.update()
        .where(app_settings.c.default_connection_id.in_(all_demo_ids))
        .values(default_connection_id=None)
    )
    bind.execute(
        conversations.update()
        .where(conversations.c.connection_id.in_(all_demo_ids))
        .values(connection_id=None)
    )
    bind.execute(connections.delete().where(connections.c.id.in_(all_demo_ids)))


def _without_available_lenses(value: Any) -> tuple[Any, bool]:
    if isinstance(value, dict):
        changed = "available_lenses" in value
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if key == "available_lenses":
                continue
            cleaned_item, item_changed = _without_available_lenses(item)
            cleaned[key] = cleaned_item
            changed = changed or item_changed
        return cleaned, changed
    if isinstance(value, list):
        changed = False
        cleaned_items: list[Any] = []
        for item in value:
            cleaned_item, item_changed = _without_available_lenses(item)
            cleaned_items.append(cleaned_item)
            changed = changed or item_changed
        return cleaned_items, changed
    return value, False


_OLD_DESKTOP_PATH = "/.querygpt-desktop/"
_NEW_DESKTOP_PATH = "/.receiptbi-desktop/"


def _replace_desktop_path(value: Any) -> tuple[Any, bool]:
    if isinstance(value, str):
        replaced = value.replace(_OLD_DESKTOP_PATH, _NEW_DESKTOP_PATH)
        return replaced, replaced != value
    if isinstance(value, dict):
        changed = False
        replaced_dict: dict[str, Any] = {}
        for key, item in value.items():
            replaced_item, item_changed = _replace_desktop_path(item)
            replaced_dict[key] = replaced_item
            changed = changed or item_changed
        return replaced_dict, changed
    if isinstance(value, list):
        changed = False
        replaced_items: list[Any] = []
        for item in value:
            replaced_item, item_changed = _replace_desktop_path(item)
            replaced_items.append(replaced_item)
            changed = changed or item_changed
        return replaced_items, changed
    return value, False


def _migrate_desktop_paths(bind: sa.Connection) -> None:
    for table in (conversations, messages):
        for row in bind.execute(sa.select(table.c.id, table.c.extra_data)).mappings():
            replaced, changed = _replace_desktop_path(row["extra_data"])
            if changed:
                bind.execute(
                    table.update().where(table.c.id == row["id"]).values(extra_data=replaced)
                )
    for row in bind.execute(
        sa.select(
            project_data_sources.c.id,
            project_data_sources.c.source_uri,
            project_data_sources.c.working_uri,
        )
    ).mappings():
        values: dict[str, Any] = {}
        for field in ("source_uri", "working_uri"):
            value = row[field]
            if isinstance(value, str) and _OLD_DESKTOP_PATH in value:
                values[field] = value.replace(_OLD_DESKTOP_PATH, _NEW_DESKTOP_PATH)
        if values:
            bind.execute(
                project_data_sources.update()
                .where(project_data_sources.c.id == row["id"])
                .values(**values)
            )


def _clean_persisted_lenses(bind: sa.Connection) -> None:
    for row in bind.execute(
        sa.select(project_data_sources.c.id, project_data_sources.c.profile_data)
    ).mappings():
        cleaned, changed = _without_available_lenses(row["profile_data"])
        if changed:
            bind.execute(
                project_data_sources.update()
                .where(project_data_sources.c.id == row["id"])
                .values(profile_data=cleaned)
            )
    for row in bind.execute(
        sa.select(preflight_reports.c.id, preflight_reports.c.source_snapshot)
    ).mappings():
        cleaned, changed = _without_available_lenses(row["source_snapshot"])
        if changed:
            bind.execute(
                preflight_reports.update()
                .where(preflight_reports.c.id == row["id"])
                .values(source_snapshot=cleaned)
            )


def _create_migrated_workspace(
    bind: sa.Connection,
    *,
    connection: Mapping[str, Any] | None,
) -> object:
    project_id = uuid4()
    context = (
        {
            "legacy_connection_id": _id(connection["id"]),
            "legacy_connection_name": str(connection["name"] or ""),
        }
        if connection is not None
        else {"legacy_scope": "global"}
    )
    bind.execute(
        projects.insert().values(
            id=project_id,
            name="Migrated workspace",
            description="旧版设置的隔离归档；请核对后再确认或锁定其中的业务定义。",
            status="active",
            extra_data={"legacy_settings_migration": context},
        )
    )
    if connection is not None:
        bind.execute(
            project_data_sources.insert().values(
                id=uuid4(),
                project_id=project_id,
                connection_id=connection["id"],
                kind="connection",
                name=str(connection["name"] or "Imported connection")[:255],
                format=str(connection["driver"] or "")[:30] or None,
                status="attached",
                profile_data={
                    "legacy_settings_migration": True,
                    "logical_name": str(connection["name"] or "Imported connection")[:255],
                    "is_current": True,
                },
            )
        )
    return project_id


def _insert_entry_with_revision(
    bind: sa.Connection,
    *,
    project_id: object,
    key: str,
    value: str,
    entry_type: str,
    validity: str,
    execution_state: str,
    evidence: list[dict[str, Any]],
    is_active: bool,
    created_at: datetime | None,
) -> None:
    entry_id = uuid4()
    revision_id = uuid4()
    timestamp = created_at or datetime.now(UTC)
    snapshot = {
        "key": key,
        "value": value,
        "entry_type": entry_type,
        "state": "candidate",
        "confidence": 0.5,
        "definition": None,
        "validity": validity,
        "execution_state": execution_state,
        "execution_details": {},
        "evidence": evidence,
        "source": "imported",
        "is_active": is_active,
    }
    bind.execute(
        semantic_entries.insert().values(
            id=entry_id,
            project_id=project_id,
            **snapshot,
            revision_number=1,
            active_revision_id=revision_id,
            created_at=timestamp,
            updated_at=timestamp,
        )
    )
    bind.execute(
        semantic_entry_revisions.insert().values(
            id=revision_id,
            project_id=project_id,
            semantic_entry_id=entry_id,
            revision_number=1,
            parent_revision_id=None,
            restored_from_revision_id=None,
            mutation_kind="legacy_settings_import",
            actor_source="imported",
            reason="从退役的旧版设置迁入项目语义层",
            source_correction_id=None,
            snapshot=snapshot,
            created_at=timestamp,
        )
    )


def _migrate_legacy_knowledge(bind: sa.Connection, demo_ids: set[str]) -> None:
    connection_rows = {
        _id(row["id"]): row
        for row in bind.execute(
            sa.select(
                connections.c.id,
                connections.c.name,
                connections.c.driver,
                connections.c.database_name,
            )
        ).mappings()
    }
    project_ids_by_connection: dict[str, list[object]] = {}
    for row in bind.execute(
        sa.select(
            project_data_sources.c.connection_id,
            project_data_sources.c.project_id,
        ).where(project_data_sources.c.connection_id.is_not(None))
    ).mappings():
        project_ids_by_connection.setdefault(_id(row["connection_id"]), []).append(
            row["project_id"]
        )

    fallback_by_connection: dict[str, object] = {}
    global_workspace_id: object | None = None
    existing_keys = {
        (_id(row["project_id"]), str(row["key"]))
        for row in bind.execute(
            sa.select(semantic_entries.c.project_id, semantic_entries.c.key)
        ).mappings()
    }

    def projects_for(connection_id: object | None) -> list[object]:
        nonlocal global_workspace_id
        if connection_id is None:
            if global_workspace_id is None:
                global_workspace_id = _create_migrated_workspace(bind, connection=None)
            return [global_workspace_id]
        normalized = _id(connection_id)
        attached = list(dict.fromkeys(project_ids_by_connection.get(normalized, [])))
        if attached:
            return attached
        connection = connection_rows.get(normalized)
        if connection is None:
            if global_workspace_id is None:
                global_workspace_id = _create_migrated_workspace(bind, connection=None)
            return [global_workspace_id]
        if normalized not in fallback_by_connection:
            fallback_by_connection[normalized] = _create_migrated_workspace(
                bind,
                connection=connection,
            )
        return [fallback_by_connection[normalized]]

    for row in bind.execute(sa.select(semantic_terms)).mappings():
        connection_id = row["connection_id"]
        if connection_id is not None and _id(connection_id) in demo_ids:
            continue
        legacy_id = _id(row["id"])
        key = f"legacy_term:{legacy_id}"
        legacy_active = row["is_active"] is not False
        term_type = str(row["term_type"] or "").casefold()
        entry_type = term_type if term_type in {"metric", "dimension"} else "business_rule"
        evidence = [
            {
                "kind": "legacy_settings_import",
                "legacy_table": "semantic_terms",
                "legacy_id": legacy_id,
                "legacy_connection_id": _id(connection_id) if connection_id else None,
                "term": str(row["term"] or ""),
                "expression": str(row["expression"] or ""),
                "term_type": str(row["term_type"] or ""),
                "description": row["description"],
                "examples": row["examples"] or [],
                "legacy_is_active": legacy_active,
            }
        ]
        value = f"{str(row['term'] or '').strip()}: {str(row['expression'] or '').strip()}"
        for project_id in projects_for(connection_id):
            pair = (_id(project_id), key)
            if pair in existing_keys:
                continue
            _insert_entry_with_revision(
                bind,
                project_id=project_id,
                key=key,
                value=value,
                entry_type=entry_type,
                validity="active" if legacy_active else "stale",
                execution_state="definition_only" if legacy_active else "blocked",
                evidence=evidence,
                is_active=legacy_active,
                created_at=row["created_at"],
            )
            existing_keys.add(pair)

    for row in bind.execute(sa.select(table_relationships)).mappings():
        connection_id = row["connection_id"]
        if connection_id is not None and _id(connection_id) in demo_ids:
            continue
        legacy_id = _id(row["id"])
        key = f"legacy_relationship:{legacy_id}"
        legacy_active = row["is_active"] is not False
        evidence = [
            {
                "kind": "legacy_settings_import",
                "legacy_table": "table_relationships",
                "legacy_id": legacy_id,
                "legacy_connection_id": _id(connection_id) if connection_id else None,
                "source_table": str(row["source_table"] or ""),
                "source_column": str(row["source_column"] or ""),
                "target_table": str(row["target_table"] or ""),
                "target_column": str(row["target_column"] or ""),
                "relationship_type": str(row["relationship_type"] or ""),
                "join_type": str(row["join_type"] or ""),
                "description": row["description"],
                "legacy_is_active": legacy_active,
            }
        ]
        value = (
            f"{row['source_table']}.{row['source_column']} "
            f"{row['join_type'] or 'LEFT'} JOIN "
            f"{row['target_table']}.{row['target_column']} "
            f"({row['relationship_type'] or '1:N'})"
        )
        for project_id in projects_for(connection_id):
            pair = (_id(project_id), key)
            if pair in existing_keys:
                continue
            _insert_entry_with_revision(
                bind,
                project_id=project_id,
                key=key,
                value=value,
                entry_type="relationship",
                validity="unverified" if legacy_active else "stale",
                execution_state="definition_only" if legacy_active else "blocked",
                evidence=evidence,
                is_active=legacy_active,
                created_at=row["created_at"],
            )
            existing_keys.add(pair)

    prompt_rows = list(bind.execute(sa.select(prompts)).mappings())
    if prompt_rows:
        prompt_project_id = projects_for(None)[0]
        for row in prompt_rows:
            legacy_id = _id(row["id"])
            key = f"legacy_prompt:{legacy_id}"
            pair = (_id(prompt_project_id), key)
            if pair in existing_keys:
                continue
            evidence = [
                {
                    "kind": "legacy_settings_import",
                    "legacy_table": "prompts",
                    "legacy_id": legacy_id,
                    "name": str(row["name"] or ""),
                    "description": row["description"],
                    "version": int(row["version"] or 1),
                    "legacy_is_active": row["is_active"] is not False,
                    "legacy_is_default": row["is_default"] is True,
                    "legacy_parent_id": _id(row["parent_id"]) if row["parent_id"] else None,
                    "archived_only": True,
                }
            ]
            _insert_entry_with_revision(
                bind,
                project_id=prompt_project_id,
                key=key,
                value=str(row["content"] or ""),
                entry_type="business_rule",
                validity="stale",
                execution_state="blocked",
                evidence=evidence,
                is_active=False,
                created_at=row["created_at"],
            )
            existing_keys.add(pair)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    demo_ids = _demo_connection_ids(bind)
    _remove_demo_state(bind, demo_ids)
    _migrate_desktop_paths(bind)
    _clean_persisted_lenses(bind)
    _migrate_legacy_knowledge(bind, demo_ids)

    for table_name in ("prompts", "table_relationships", "semantic_terms"):
        if table_name in table_names:
            op.drop_table(table_name)

    if "app_settings" in table_names:
        app_settings_columns = {column["name"] for column in inspector.get_columns("app_settings")}
        if "demo_initialized" in app_settings_columns:
            with op.batch_alter_table("app_settings") as batch_op:
                batch_op.drop_column("demo_initialized")


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    app_settings_columns = {column["name"] for column in inspector.get_columns("app_settings")}
    if "demo_initialized" not in app_settings_columns:
        op.add_column(
            "app_settings",
            sa.Column(
                "demo_initialized",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )

    op.create_table(
        "semantic_terms",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("connection_id", _uuid(), nullable=True),
        sa.Column("term", sa.String(100), nullable=False),
        sa.Column("expression", sa.Text(), nullable=False),
        sa.Column("term_type", sa.String(20), nullable=False, server_default="metric"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("examples", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["connection_id"], ["connections.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_semantic_terms_term", "semantic_terms", ["term"])
    op.create_table(
        "table_relationships",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("connection_id", _uuid(), nullable=False),
        sa.Column("source_table", sa.String(100), nullable=False),
        sa.Column("source_column", sa.String(100), nullable=False),
        sa.Column("target_table", sa.String(100), nullable=False),
        sa.Column("target_column", sa.String(100), nullable=False),
        sa.Column("relationship_type", sa.String(10), nullable=False, server_default="1:N"),
        sa.Column("join_type", sa.String(20), nullable=False, server_default="LEFT"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["connection_id"], ["connections.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "prompts",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("parent_id", _uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["parent_id"], ["prompts.id"], ondelete="SET NULL"),
    )
