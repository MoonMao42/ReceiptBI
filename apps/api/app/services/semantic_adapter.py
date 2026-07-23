"""Replaceable adapter around the embedded Wren Core semantic engine."""

from __future__ import annotations

import base64
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from app.services.project_context import ProjectRuntimeContext

_SEMANTIC_INSTRUCTION_CHAR_BUDGET = 12_000
_SEMANTIC_MODEL_HINT_CHAR_BUDGET = 2_600
_SEMANTIC_RELATIONSHIP_HINT_CHAR_BUDGET = 6_200
_SEMANTIC_COLUMN_MAPPING_HINT_CHAR_BUDGET = 2_400


def _instruction_query_terms(query: str | None) -> tuple[str, ...]:
    if not query or not query.strip():
        return ()
    normalized = unicodedata.normalize("NFKC", query).casefold()[:512]
    terms: set[str] = set()
    for token in re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]+", normalized):
        if not token:
            continue
        terms.add(token)
        if re.fullmatch(r"[\u4e00-\u9fff]+", token) and len(token) > 2:
            for size in range(2, min(4, len(token)) + 1):
                terms.update(token[index : index + size] for index in range(len(token) - size + 1))
    return tuple(sorted(terms, key=lambda value: (-len(value), value))[:96])


def _instruction_relevance(value: str, query_terms: tuple[str, ...]) -> int:
    if not query_terms:
        return 0
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return sum(min(len(term), 12) for term in query_terms if term in normalized)


def _bounded_instruction_list(
    label: str,
    ranked_items: list[tuple[tuple[Any, ...], str]],
    *,
    char_budget: int,
) -> tuple[str, bool]:
    """Render complete, deterministic entries without cutting a value in half."""

    if not ranked_items:
        return "", False
    prefix = f"；{label}："
    ranked = sorted(ranked_items, key=lambda item: item[0])
    selected: list[str] = []
    for _, item in ranked:
        candidate = prefix + "、".join([*selected, item])
        if len(candidate) > char_budget:
            continue
        selected.append(item)

    omitted = len(ranked) - len(selected)
    marker = f"（其余 {omitted} 项按需解析）" if omitted else ""
    while selected and len(prefix + "、".join(selected) + marker) > char_budget:
        selected.pop()
        omitted += 1
        marker = f"（其余 {omitted} 项按需解析）"
    if not selected:
        marker = f"（{len(ranked)} 项按需解析）"
        summary = prefix + marker
        return (summary if len(summary) <= char_budget else ""), True
    return prefix + "、".join(selected) + marker, bool(omitted)


def _relationship_instruction_rank(
    project: ProjectRuntimeContext,
    *,
    backend: str,
    model_name: str,
    column: dict[str, Any],
    query_terms: tuple[str, ...],
) -> tuple[Any, ...]:
    relationship_key = str((column.get("properties") or {}).get("relationshipKey") or "")
    relationship = getattr(project, "executable_relationships", {}).get(relationship_key, {})
    searchable = " ".join(
        (
            backend,
            model_name,
            str(column["name"]),
            relationship_key,
            json.dumps(
                relationship.get("definition") or {},
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ),
        )
    )
    return (
        {"locked": 0, "confirmed": 1}.get(str(relationship.get("state") or ""), 2),
        relationship.get("execution_state") != "verified",
        -_instruction_relevance(searchable, query_terms),
        relationship_key,
        backend,
        model_name,
        str(column["name"]),
    )


def _semantic_type(raw_type: str) -> str:
    normalized = raw_type.lower()
    if any(token in normalized for token in ("int", "serial")):
        return "BIGINT"
    if any(token in normalized for token in ("float", "double", "real", "decimal", "numeric")):
        return "DOUBLE"
    if "bool" in normalized:
        return "BOOLEAN"
    if "timestamp" in normalized or "datetime" in normalized:
        return "TIMESTAMP"
    if normalized == "date" or normalized.startswith("date["):
        return "DATE"
    if "json" in normalized:
        return "JSON"
    return "VARCHAR"


def _model_name(value: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_").lower()
    return name or "dataset"


def _logical_identifier(value: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9_\u4e00-\u9fff]+", "_", value).strip("_")
    if not name:
        name = "column"
    if name[0].isdigit():
        name = f"column_{name}"
    return name


def _quoted_identifier(value: str) -> str:
    return f'"{value.replace(chr(34), chr(34) * 2)}"'


def _unique_name(candidate: str, used: set[str]) -> str:
    if candidate not in used:
        return candidate
    counter = 2
    while f"{candidate}_{counter}" in used:
        counter += 1
    return f"{candidate}_{counter}"


def _column_payloads(
    columns: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    payloads: list[dict[str, Any]] = []
    logical_names: dict[str, str] = {}
    used_names: set[str] = set()
    for column in columns:
        physical_name = str(column.get("name") or "column")
        logical_name = _unique_name(_logical_identifier(physical_name), used_names)
        used_names.add(logical_name)
        logical_names[physical_name] = logical_name
        properties = {"description": str(column.get("description") or "")}
        payload: dict[str, Any] = {
            "name": logical_name,
            "type": _semantic_type(str(column.get("type") or column.get("dtype") or "varchar")),
            "properties": properties,
        }
        if logical_name != physical_name:
            payload["expression"] = _quoted_identifier(physical_name)
            properties["physicalName"] = physical_name
        payloads.append(payload)
    return payloads, logical_names


def build_manifest(
    project: ProjectRuntimeContext,
    sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compile source profiles into an engine-ready Wren MDL manifest."""

    models: list[dict[str, Any]] = []
    used_names: set[str] = set()
    model_lookup: dict[tuple[str, str], str] = {}
    physical_columns: dict[str, list[dict[str, Any]]] = {}
    logical_columns: dict[str, dict[str, str]] = {}
    selected_sources = sources if sources is not None else project.sources
    for source in selected_sources:
        profile = source.get("profile") or {}
        source_id = str(source.get("id") or "")
        if source.get("kind") == "file":
            columns = profile.get("schema", {}).get("columns", [])
            if not columns:
                continue
            table_name = str(source.get("view_name") or source.get("name") or "dataset")
            name = _unique_name(_model_name(table_name), used_names)
            used_names.add(name)
            model_lookup[(source_id, table_name)] = name
            physical_columns[name] = list(columns)
            column_payloads, logical_column_names = _column_payloads(list(columns))
            logical_columns[name] = logical_column_names
            models.append(
                {
                    "name": name,
                    "tableReference": {"table": table_name},
                    "columns": column_payloads,
                    "properties": {"description": profile.get("summary") or source.get("name")},
                }
            )
            continue

        for table in profile.get("tables", []):
            raw_name = str(table.get("name") or "table")
            preferred_name = _model_name(raw_name)
            if preferred_name in used_names:
                preferred_name = _model_name(f"{source.get('name')}_{raw_name}")
            name = _unique_name(preferred_name, used_names)
            used_names.add(name)
            model_lookup[(source_id, raw_name)] = name
            columns = list(table.get("columns", []))
            physical_columns[name] = columns
            column_payloads, logical_column_names = _column_payloads(columns)
            logical_columns[name] = logical_column_names
            models.append(
                {
                    "name": name,
                    "tableReference": {"table": raw_name},
                    "columns": column_payloads,
                    "properties": {"description": f"来自 {source.get('name')}"},
                }
            )

    model_payloads = {str(model["name"]): model for model in models}
    relationships: list[dict[str, Any]] = []
    used_relationship_names: set[str] = set()
    for relationship in project.executable_relationships.values():
        definition = relationship.get("definition") or {}
        resolved = relationship.get("resolved_sources") or {}
        left_source_id = str((resolved.get("left") or {}).get("source_id") or "")
        right_source_id = str((resolved.get("right") or {}).get("source_id") or "")
        cardinality = str(definition.get("cardinality") or "")
        if (
            relationship.get("validity") != "active"
            or definition.get("normalization") != "exact"
            or cardinality not in {"one_to_one", "one_to_many", "many_to_one", "many_to_many"}
        ):
            continue
        left = definition["left"]
        right = definition["right"]
        left_model = model_lookup.get((left_source_id, str(left["table_or_view"])))
        right_model = model_lookup.get((right_source_id, str(right["table_or_view"])))
        if left_model is None or right_model is None or cardinality == "many_to_many":
            continue

        if cardinality == "one_to_many":
            source_model, source_physical_column = right_model, str(right["column"])
            target_model, target_physical_column = left_model, str(left["column"])
        else:
            source_model, source_physical_column = left_model, str(left["column"])
            target_model, target_physical_column = right_model, str(right["column"])
        source_column = logical_columns[source_model].get(source_physical_column)
        target_column = logical_columns[target_model].get(target_physical_column)
        if source_column is None or target_column is None:
            continue

        source_payload = model_payloads[source_model]
        source_column_names = {str(column["name"]) for column in source_payload["columns"]}
        # wren-core 0.7 resolves a relationship path by the target model name.
        # If a physical field already occupies that name, fail closed and keep
        # the relationship in ReceiptBI's typed join runtime instead.
        if target_model in source_column_names:
            continue

        relationship_name = _unique_name(
            _model_name(str(relationship.get("key") or "relationship")),
            used_relationship_names,
        )
        used_relationship_names.add(relationship_name)
        relationships.append(
            {
                "name": relationship_name,
                "models": [source_model, target_model],
                "joinType": "many_to_one" if cardinality == "one_to_many" else cardinality,
                "condition": (
                    f"{_quoted_identifier(source_model)}.{_quoted_identifier(source_column)} = "
                    f"{_quoted_identifier(target_model)}.{_quoted_identifier(target_column)}"
                ),
            }
        )
        source_payload["columns"].append(
            {
                "name": target_model,
                "type": target_model,
                "relationship": relationship_name,
                "properties": {
                    "description": f"ReceiptBI 已确认关系 {relationship.get('key')}",
                    "relationshipKey": str(relationship.get("key") or ""),
                },
            }
        )
        source_column_names.add(target_model)
        for target in physical_columns[target_model]:
            target_physical_name = str(target.get("name") or "column")
            target_name = logical_columns[target_model][target_physical_name]
            base_name = _logical_identifier(f"{target_model}_{target_name}")
            derived_name = _unique_name(base_name, source_column_names)
            source_column_names.add(derived_name)
            source_payload["columns"].append(
                {
                    "name": derived_name,
                    "type": _semantic_type(
                        str(target.get("type") or target.get("dtype") or "varchar")
                    ),
                    "isCalculated": True,
                    "expression": (
                        f"{_quoted_identifier(target_model)}.{_quoted_identifier(target_name)}"
                    ),
                    "properties": {
                        "description": (
                            f"通过已确认关系 {relationship.get('key')} 取得 "
                            f"{target_model}.{target_name}"
                        ),
                        "relationshipKey": str(relationship.get("key") or ""),
                        "sourceColumn": target_physical_name,
                    },
                }
            )

    return {
        "catalog": "receiptbi",
        "schema": "project",
        "models": models,
        "relationships": relationships,
        "views": [],
    }


class SemanticEngineAdapter:
    """Plan modeled SQL with Wren Core while keeping its product layer replaceable."""

    def __init__(self, project: ProjectRuntimeContext):
        self.project = project
        self.project_dir: Path = project.project_dir
        self._sessions: dict[str, Any] = {}
        self._manifests: dict[str, dict[str, Any]] = {}
        self.diagnostics: list[dict[str, str]] = []
        self.compiled_backends: list[str] = []
        self.compiled_relationship_keys: list[str] = []
        self.internal_relationship_keys: list[str] = sorted(project.executable_relationships)
        self.status = "internal"
        backend_sources: dict[str, list[dict[str, Any]]] = {}
        file_sources = [source for source in project.sources if source.get("kind") == "file"]
        if file_sources:
            backend_sources["files"] = file_sources
        for source in project.sources:
            if source.get("kind") == "connection":
                backend_sources[str(source.get("id") or source.get("name") or "database")] = [
                    source
                ]
        backend_manifests = {
            backend: manifest
            for backend, sources in backend_sources.items()
            if (manifest := build_manifest(project, sources))["models"]
        }
        if not backend_manifests:
            return
        try:
            from wren_core import SessionContext, to_manifest
        except ImportError as exc:
            self.diagnostics.append(
                {"backend": "all", "kind": "wren_unavailable", "detail": str(exc)}
            )
            return

        target_dir = self.project_dir / "target" / "mdl"
        for backend, manifest in backend_manifests.items():
            try:
                payload = json.dumps(manifest, ensure_ascii=False, separators=(",", ":"))
                encoded = base64.b64encode(payload.encode("utf-8")).decode("ascii")
                to_manifest(encoded)
                self._sessions[backend] = SessionContext(encoded)
                self._manifests[backend] = manifest
                target_dir.mkdir(parents=True, exist_ok=True)
                (target_dir / f"{_model_name(backend)}.json").write_text(
                    json.dumps(manifest, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                self.diagnostics.append(
                    {
                        "backend": backend,
                        "kind": "manifest_compile_failed",
                        "detail": str(exc),
                    }
                )

        self.compiled_backends = sorted(self._sessions)
        compiled_relationship_keys = {
            str((column.get("properties") or {}).get("relationshipKey"))
            for manifest in self._manifests.values()
            for model in manifest["models"]
            for column in model["columns"]
            if column.get("relationship")
            and (column.get("properties") or {}).get("relationshipKey")
        }
        self.compiled_relationship_keys = sorted(compiled_relationship_keys)
        self.internal_relationship_keys = sorted(
            set(project.executable_relationships) - compiled_relationship_keys
        )
        self.diagnostics.extend(
            {
                "backend": "internal",
                "kind": "relationship_internal",
                "detail": key,
            }
            for key in self.internal_relationship_keys
        )
        if not self._sessions:
            return
        self.status = (
            "wren-core" if len(self._sessions) == len(backend_manifests) else "wren-core-partial"
        )
        primary_backend = "files" if "files" in self._manifests else self.compiled_backends[0]
        manifest_path = self.project_dir / "target" / "mdl.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(self._manifests[primary_backend], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def transform_sql(self, sql: str, source_id: str | None = None) -> str:
        backend = source_id
        if backend is None:
            if "files" in self._sessions:
                backend = "files"
            elif len(self._sessions) == 1:
                backend = next(iter(self._sessions))
        session = self._sessions.get(str(backend)) if backend is not None else None
        if session is None:
            return sql
        return str(session.transform_sql(sql))

    def validate_sql(self, sql: str, source_id: str | None = None) -> None:
        """Prevent a confirmed Wren relationship from being bypassed by a manual JOIN."""

        backend = source_id
        if backend is None:
            if "files" in self._manifests:
                backend = "files"
            elif len(self._manifests) == 1:
                backend = next(iter(self._manifests))
        manifest = self._manifests.get(str(backend)) if backend is not None else None
        if manifest is None or not re.search(r"\bjoin\b", sql, re.I):
            return
        for relationship in manifest["relationships"]:
            if all(
                re.search(rf'(?<![\w])"?{re.escape(model)}"?(?![\w])', sql, re.I)
                for model in relationship["models"]
            ):
                relationship_key = next(
                    (
                        (column.get("properties") or {}).get("relationshipKey")
                        for model in manifest["models"]
                        for column in model["columns"]
                        if column.get("relationship") == relationship["name"]
                    ),
                    None,
                )
                derived_fields = [
                    f"{model['name']}.{column['name']}"
                    for model in manifest["models"]
                    for column in model["columns"]
                    if (column.get("properties") or {}).get("relationshipKey") == relationship_key
                    and column.get("isCalculated")
                ]
                raise ValueError(
                    "该关联已有确认关系，不能手写 JOIN 条件；请改用语义关系字段："
                    + "、".join(derived_fields[:12])
                )

    def instructions(self, query: str | None = None) -> str:
        if not self._sessions:
            return ""
        query_terms = _instruction_query_terms(query)
        relationship_models = {
            (backend, str(model["name"]))
            for backend, manifest in self._manifests.items()
            for model in manifest["models"]
            for column in model["columns"]
            if column.get("isCalculated")
            and (column.get("properties") or {}).get("relationshipKey")
        }
        models = [
            (
                (
                    -_instruction_relevance(f"{backend} {model['name']}", query_terms),
                    (backend, str(model["name"])) not in relationship_models,
                    str(backend),
                    str(model["name"]),
                ),
                f"{backend}: {model['name']}",
            )
            for backend, manifest in self._manifests.items()
            for model in manifest["models"]
        ]
        relationship_fields = [
            (
                _relationship_instruction_rank(
                    self.project,
                    backend=str(backend),
                    model_name=str(model["name"]),
                    column=column,
                    query_terms=query_terms,
                ),
                f"{backend}: {model['name']}.{column['name']}",
            )
            for backend, manifest in self._manifests.items()
            for model in manifest["models"]
            for column in model["columns"]
            if column.get("isCalculated")
            and (column.get("properties") or {}).get("relationshipKey")
        ]
        relationship_hint, relationship_truncated = _bounded_instruction_list(
            "同后端已确认关系必须使用这些派生字段",
            relationship_fields,
            char_budget=_SEMANTIC_RELATIONSHIP_HINT_CHAR_BUDGET,
        )
        column_mappings = [
            (
                (
                    -_instruction_relevance(
                        " ".join(
                            (
                                str(backend),
                                str(model["name"]),
                                str(column["name"]),
                                str((column.get("properties") or {}).get("physicalName") or ""),
                            )
                        ),
                        query_terms,
                    ),
                    str(backend),
                    str(model["name"]),
                    str(column["name"]),
                    str((column.get("properties") or {}).get("physicalName") or ""),
                ),
                (
                    f"{backend}: {model['name']}.{column['name']} 对应物理字段 "
                    f"{(column.get('properties') or {}).get('physicalName')}"
                ),
            )
            for backend, manifest in self._manifests.items()
            for model in manifest["models"]
            for column in model["columns"]
            if (column.get("properties") or {}).get("physicalName")
        ]
        mapping_hint, mapping_truncated = _bounded_instruction_list(
            "含特殊字符的字段使用这些逻辑名称",
            column_mappings,
            char_budget=_SEMANTIC_COLUMN_MAPPING_HINT_CHAR_BUDGET,
        )
        model_hint, model_truncated = _bounded_instruction_list(
            "可用业务模型",
            models,
            char_budget=_SEMANTIC_MODEL_HINT_CHAR_BUDGET,
        )
        selection_hint = ""
        if relationship_truncated or mapping_truncated or model_truncated:
            selection_hint = (
                "；以上清单已按验证状态和当前问题筛选"
                if query_terms
                else "；以上清单已按验证状态和容量预算筛选"
            )
        result = (
            "结构语义按每个物理数据后端分别由 Wren Core 校验；跨后端只能使用 ReceiptBI "
            "已验证的关系工具"
            + model_hint
            + relationship_hint
            + mapping_hint
            + selection_hint
            + "。"
        )
        if len(result) > _SEMANTIC_INSTRUCTION_CHAR_BUDGET:
            raise RuntimeError("semantic adapter instruction budget exceeded")
        return result
