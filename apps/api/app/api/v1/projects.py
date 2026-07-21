"""Project, data readiness and learned business knowledge APIs."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import shutil
import zipfile
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, TypeAdapter, ValidationError
from pydantic_ai import Agent
from sqlalchemy import case, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import encryptor
from app.core.config import settings
from app.db import get_db
from app.db.tables import (
    AnalysisCorrection,
    AnalysisRun,
    ArtifactRecord,
    Connection,
    PreflightReportRecord,
    Project,
    ProjectDataSource,
    SanitationRecipeRecord,
    SanitationRecipeRevisionRecord,
    SemanticEntry,
    SemanticEntryRevision,
)
from app.models import (
    AnalysisCorrectionCreate,
    AnalysisCorrectionDeleteResponse,
    AnalysisCorrectionResponse,
    AnalysisCorrectionTargetResponse,
    AnalysisPlaybookCapture,
    AnalysisPlaybookDeleteResponse,
    AnalysisPlaybookResponse,
    AnalysisPlaybookSourceRole,
    AnalysisPlaybookStep,
    AnalysisPlaybookValidationSummary,
    AnalysisRunCreate,
    AnalysisRunResponse,
    APIResponse,
    ArtifactResponse,
    ConnectionSourceCreate,
    DataSourceResponse,
    PreflightReportResponse,
    ProjectBundle,
    ProjectBundleSanitationHistory,
    ProjectCreate,
    ProjectDependencyInstall,
    ProjectResponse,
    SanitationRecipeResponse,
    SanitationRecipeRevisionResponse,
    SanitationRecipeRevisionRestoreRequest,
    SanitationTemplateBindRequest,
    SanitationTemplateBindResponse,
    SanitationTemplatePreviewRequest,
    SanitationTemplatePreviewResponse,
    SanitationTemplateShape,
    SanitationTemplateSummaryResponse,
    SemanticEntryCreate,
    SemanticEntryResponse,
    SemanticEntryRestoreRequest,
    SemanticEntryRevisionResponse,
    SemanticEntryUpdate,
    StandingAnalysisResponse,
    SuggestedQuestion,
    SuggestedQuestionsRequest,
    SuggestedQuestionsResponse,
    TrustedProjectReferenceCapture,
    TrustedProjectReferenceResponse,
    TrustedProjectReferenceSourceRole,
    TrustedProjectReferenceValidationEvidence,
)
from app.models.workspace import (
    AnalysisCorrectionTargetOptionResponse,
    AnalysisPlaybookStructuredQueryPlan,
    MetricColumnCorrectionSelection,
    ProjectUpdate,
    SemanticEntryBatchRequest,
    SemanticEntryBatchResponse,
    SemanticEntryPageResponse,
    SemanticEntrySummaryResponse,
    SemanticSourceRef,
    SourceCleaningApplyRequest,
    SourceCleaningApplyResponse,
    SourceCleaningPreviewRequest,
    SourceCleaningPreviewResponse,
    validate_semantic_definition_compatibility,
)
from app.services.analysis_checkpoint import stable_payload_hash
from app.services.analyst_runtime import build_pydantic_model
from app.services.app_settings import get_or_create_app_settings, settings_to_dict
from app.services.business_decision_slots import canonicalize_decision_key
from app.services.correction_targets import (
    discover_metric_column_correction_options,
    discover_report_correction_targets,
    resolve_metric_column_correction_option,
    resolve_report_correction_target,
)
from app.services.data_preflight import (
    SUPPORTED_FILE_FORMATS,
    compare_working_copies,
    fingerprint_file,
    run_preflight,
)
from app.services.database import create_database_manager
from app.services.database_value_preflight import run_database_value_preflight
from app.services.dependency_manager import ProjectDependencyManager
from app.services.execution_context import ExecutionContextResolver
from app.services.golden_regression import normalize_query_key
from app.services.project_context import (
    _canonical_column,
    _view_name,
    load_project_context,
    resolve_confirmed_ambiguity,
)
from app.services.sanitation_contract import (
    SANITATION_PROVENANCE_OPERATIONS,
    SanitationContractError,
    canonicalize_sanitation_operations,
    canonicalize_visual_sanitation_operations,
)
from app.services.sanitation_revisions import (
    SanitationRevisionConflictError,
    SanitationRevisionIntegrityError,
    append_sanitation_revision,
    ensure_sanitation_revision_head,
    restore_sanitation_revision,
    sanitation_fingerprint_contract,
    sanitation_revision_or_none,
)
from app.services.semantic_learning import compile_report_correction
from app.services.semantic_revisions import (
    SemanticRevisionConflictError,
    append_semantic_revision,
    deactivate_semantic_entry,
    reset_semantic_execution_proof,
    restore_semantic_revision,
    semantic_entry_snapshot,
    semantic_revision_or_none,
)
from app.services.semantic_source_scope import (
    SemanticSourceCatalog,
    SemanticSourceResolution,
    SemanticSourceScopeFilter,
    resolution_matches_scope,
    resolve_semantic_source_scope,
)
from app.services.standing_workspace import (
    StandingWorkspaceCorruptError,
    StandingWorkspaceError,
    load_standing_analyses,
    save_standing_analyses,
    standing_analysis_id,
    validate_playbook_run_freshness,
)

router = APIRouter(prefix="/projects", tags=["projects"])
logger = logging.getLogger(__name__)

_MAX_ACTIVE_TRUSTED_REFERENCES = 20
_MAX_STORED_TRUSTED_REFERENCES = 100
_MAX_RELATIONSHIP_ENDPOINTS_PER_COLUMN = 24
_MAX_INFERRED_RELATIONSHIPS_PER_COLUMN = 6
_MAX_INFERRED_RELATIONSHIPS_PER_PROJECT = 80
_TRUSTED_EVIDENCE_KINDS = {
    "validation",
    "relationship_validation",
    "relationship_application",
    "golden_regression_validation",
}
_TRUSTED_PROFILE_FIELDS = {
    "materialized_rows",
    "columns",
    "null_counts",
    "duplicate_rows",
    "keys",
    "numeric",
    "truncated",
    "left_key",
    "right_key",
    "left_non_null",
    "right_non_null",
    "left_match_rate",
    "right_match_rate",
    "cardinality",
    "expansion_ratio",
    "normalization",
}

_EXCEL_SHEET_SELECTION_KEY = "excel_sheet_selection"


class _SuggestedQuestionSet(BaseModel):
    items: list[SuggestedQuestion] = Field(..., min_length=3, max_length=3)


def excel_sheet_selection_key(source_id: UUID) -> str:
    """Scope a workbook decision to the source whose working copy it changes."""

    return f"{_EXCEL_SHEET_SELECTION_KEY}:{source_id}"


def parse_excel_sheet_selection_key(key: str) -> UUID | None:
    prefix = f"{_EXCEL_SHEET_SELECTION_KEY}:"
    if not key.startswith(prefix):
        return None
    try:
        return UUID(key.removeprefix(prefix))
    except ValueError:
        return None


def _scope_preflight_ambiguities(
    ambiguities: list[dict[str, Any]],
    source_id: UUID,
) -> None:
    scoped_key = excel_sheet_selection_key(source_id)
    for ambiguity in ambiguities:
        if str(ambiguity.get("key") or "") == _EXCEL_SHEET_SELECTION_KEY:
            ambiguity["key"] = scoped_key


async def _project_or_404(db: AsyncSession, project_id: UUID) -> Project:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
    return project


async def _locked_project_or_404(db: AsyncSession, project_id: UUID) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id).with_for_update())
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
    return project


async def _source_or_404(db: AsyncSession, project_id: UUID, source_id: UUID) -> ProjectDataSource:
    result = await db.execute(
        select(ProjectDataSource).where(
            ProjectDataSource.id == source_id,
            ProjectDataSource.project_id == project_id,
        )
    )
    source = result.scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据源不存在")
    return source


def _safe_filename(filename: str | None) -> str:
    raw = Path(filename or "data.csv").name
    safe = re.sub(r"[^\w.\-\u4e00-\u9fff]", "-", raw, flags=re.UNICODE)
    return safe[:180] or "data.csv"


def _source_series_key(filename: str) -> str:
    """Collapse common period/version tokens while preserving the business source name."""

    stem = Path(filename).stem.casefold()
    stem = re.sub(r"(?:19|20)\d{2}[-_. ]?(?:0?[1-9]|1[0-2])", " ", stem)
    stem = re.sub(r"(?:19|20)\d{2}", " ", stem)
    stem = re.sub(r"(?:0?[1-9]|1[0-2])\s*月", " ", stem)
    stem = re.sub(
        r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
        r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|"
        r"dec(?:ember)?|q[1-4])\b",
        " ",
        stem,
    )
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", stem)


def _profile_columns(profile: dict[str, Any]) -> set[str]:
    return {
        re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]", "", str(column.get("name", "")).lower())
        for column in profile.get("schema", {}).get("columns", [])
        if column.get("name")
    }


def _canonical_dtype(value: Any) -> str:
    dtype = str(value or "unknown").casefold()
    if "bool" in dtype:
        return "boolean"
    if any(marker in dtype for marker in ("int", "float", "decimal", "numeric", "double")):
        return "number"
    if any(marker in dtype for marker in ("datetime", "timestamp", "date", "time")):
        return "datetime"
    if dtype == "str" or any(
        marker in dtype for marker in ("object", "string", "varchar", "char", "text")
    ):
        return "text"
    return dtype


def _profile_column_contract(profile: dict[str, Any]) -> dict[str, dict[str, str]]:
    contract: dict[str, dict[str, str]] = {}
    for column in profile.get("schema", {}).get("columns", []):
        name = str(column.get("name") or "").strip()
        key = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]", "", name.casefold())
        if not key:
            continue
        raw_dtype = str(column.get("dtype") or column.get("type") or "unknown")
        contract[key] = {
            "name": name,
            "dtype": raw_dtype,
            "category": _canonical_dtype(raw_dtype),
        }
    return contract


def _schema_drift_details(
    previous_profile: dict[str, Any],
    new_schema: dict[str, Any],
) -> tuple[set[str], set[str], list[dict[str, str]], float]:
    previous = _profile_column_contract(previous_profile)
    current = _profile_column_contract({"schema": new_schema})
    previous_keys = set(previous)
    current_keys = set(current)
    union = previous_keys | current_keys
    overlap_ratio = len(previous_keys & current_keys) / len(union) if union else 1.0
    added = {current[key]["name"] for key in current_keys - previous_keys}
    removed = {previous[key]["name"] for key in previous_keys - current_keys}
    type_changes = [
        {
            "column": current[key]["name"],
            "previous_type": previous[key]["dtype"],
            "current_type": current[key]["dtype"],
            "previous_category": previous[key]["category"],
            "current_category": current[key]["category"],
        }
        for key in sorted(previous_keys & current_keys)
        if previous[key]["category"] != current[key]["category"]
    ]
    return added, removed, type_changes, round(overlap_ratio, 6)


def _record_schema_drift(
    result: Any,
    *,
    matched_by: str | None,
    overlap_ratio: float,
    added_columns: set[str],
    removed_columns: set[str],
    type_changes: list[dict[str, str]],
) -> bool:
    """Attach one honest schema-drift decision without approving it implicitly."""

    if not (added_columns or removed_columns or type_changes):
        return False
    detail_parts: list[str] = []
    if added_columns:
        detail_parts.append(f"新增字段：{'、'.join(sorted(added_columns))}")
    if removed_columns:
        detail_parts.append(f"缺少字段：{'、'.join(sorted(removed_columns))}")
    if type_changes:
        detail_parts.append(
            "类型变化："
            + "、".join(
                f"{item['column']} ({item['previous_type']} → {item['current_type']})"
                for item in type_changes
            )
        )
    requires_confirmation = bool(removed_columns or type_changes)
    result.issues = [item for item in result.issues if item.get("code") != "schema_drift"]
    result.issues.append(
        {
            "code": "schema_drift",
            "title": "沿用上期整理方法时发现结构变化",
            "detail": "；".join(detail_parts),
            "severity": "warning",
            "automatic": False,
            "count": len(added_columns) + len(removed_columns) + len(type_changes),
        }
    )
    result.source_snapshot["schema_drift"] = {
        "matched_by": matched_by,
        "overlap_ratio": overlap_ratio,
        "added_columns": sorted(added_columns),
        "removed_columns": sorted(removed_columns),
        "type_changes": type_changes,
        "requires_confirmation": requires_confirmation,
    }
    if requires_confirmation:
        result.status = "needs_confirmation"
        if "结构变化需要确认" not in result.summary:
            result.summary += "，结构变化需要确认"
    elif "并提示了结构变化" not in result.summary:
        result.summary += "，并提示了结构变化"
    return requires_confirmation


def _profile_column_details(profile: dict[str, Any]) -> list[dict[str, Any]]:
    details = list(profile.get("schema", {}).get("columns", []))
    for table in profile.get("tables", []):
        for column in table.get("columns", []):
            details.append({**column, "table": table.get("name")})
    return details


def _profile_schema_signature(profile: dict[str, Any], table: str | None = None) -> str:
    columns = [
        {
            "name": str(column.get("name") or ""),
            "type": str(column.get("type") or column.get("dtype") or "unknown"),
        }
        for column in _profile_column_details(profile)
        if table is None or str(column.get("table") or "") == table
    ]
    payload = json.dumps(
        sorted(columns, key=lambda item: (item["name"], item["type"])),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sanitation_contracts(result: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """Persist bounded, inspectable proof of what one cleaning revision consumed."""

    snapshot = result.source_snapshot or {}
    reader = snapshot.get("reader") or {}
    input_contract = {
        "version": 1,
        "fingerprint": result.input_fingerprint,
        "rows": snapshot.get("original_rows"),
        "columns": snapshot.get("original_columns"),
        "selected_sheet": reader.get("selected_sheet"),
        "header_row": reader.get("header_row"),
    }
    output_contract = {
        "version": 1,
        "fingerprint": result.output_fingerprint,
        "rows": snapshot.get("ready_rows"),
        "columns": snapshot.get("ready_columns"),
        "schema_signature": _profile_schema_signature({"schema": result.inferred_schema}),
    }
    return input_contract, output_contract


async def _record_sanitation_result(
    db: AsyncSession,
    recipe: SanitationRecipeRecord,
    result: Any,
    *,
    operations: list[dict[str, Any]],
    state: str,
    actor_source: str,
    reason: str,
) -> SanitationRecipeRevisionRecord:
    """Create or advance one recipe head without rewriting its prior revisions."""

    canonical_operations = canonicalize_sanitation_operations(operations)
    input_contract, output_contract = _sanitation_contracts(result)
    recipe_status = "needs_attention" if state == "candidate" else "applied"

    if recipe.active_revision_id is None:
        recipe.status = recipe_status
        recipe.operations = canonical_operations
        recipe.input_fingerprint = result.input_fingerprint
        recipe.output_fingerprint = result.output_fingerprint
        revision = await ensure_sanitation_revision_head(db, recipe)
        await _invalidate_visual_cleaning_metadata(db, recipe)
        return revision

    active = await ensure_sanitation_revision_head(db, recipe)
    if (
        active.state == state
        and active.operations == canonical_operations
        and active.input_contract == input_contract
        and active.output_contract == output_contract
    ):
        recipe.status = recipe_status
        return active

    revision = await append_sanitation_revision(
        db,
        recipe,
        expected_active_revision_id=active.id,
        state=state,
        operations=canonical_operations,
        input_contract=input_contract,
        output_contract=output_contract,
        actor_source=actor_source,
        reason=reason,
    )
    recipe.status = recipe_status
    await _invalidate_visual_cleaning_metadata(db, recipe)
    return revision


def _stored_recipe_templates(project: Project) -> list[ProjectBundleSanitationHistory]:
    """Load imported methods as immutable templates, failing closed on corruption."""

    raw_histories = list((project.extra_data or {}).get("recipe_template_histories") or [])
    if not raw_histories:
        return []
    try:
        bundle = ProjectBundle(
            version=3,
            project=ProjectCreate(name="导入的整理方法"),
            sanitation_histories=raw_histories,
        )
        for history in bundle.sanitation_histories:
            history.head.operations = canonicalize_sanitation_operations(
                history.head.operations
            )
            for revision in history.revisions:
                revision.operations = canonicalize_sanitation_operations(
                    revision.operations
                )
        return bundle.sanitation_histories
    except (ValidationError, SanitationContractError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="导入的整理方法记录不完整，暂时不能使用",
        ) from exc


def _stored_recipe_template_bindings(project: Project) -> list[dict[str, str]]:
    bindings = list((project.extra_data or {}).get("recipe_template_bindings") or [])
    for item in bindings:
        if not isinstance(item, dict):
            raise HTTPException(status_code=409, detail="整理方法的绑定记录已损坏")
        try:
            for key in (
                "template_recipe_id",
                "template_revision_id",
                "source_id",
                "recipe_id",
                "bound_revision_id",
            ):
                UUID(str(item[key]))
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=409, detail="整理方法的绑定记录已损坏") from exc
    return bindings


def _recipe_template_or_404(
    project: Project,
    template_id: UUID,
) -> ProjectBundleSanitationHistory:
    history = next(
        (
            item
            for item in _stored_recipe_templates(project)
            if item.recipe_id == template_id
        ),
        None,
    )
    if history is None:
        raise HTTPException(status_code=404, detail="导入的整理方法不存在")
    return history


async def _single_recipe_for_source(
    db: AsyncSession,
    *,
    project_id: UUID,
    source_id: UUID,
) -> SanitationRecipeRecord | None:
    result = await db.execute(
        select(SanitationRecipeRecord)
        .where(
            SanitationRecipeRecord.project_id == project_id,
            SanitationRecipeRecord.data_source_id == source_id,
        )
        .order_by(SanitationRecipeRecord.created_at.desc())
    )
    recipes = list(result.scalars())
    if len(recipes) > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="这份数据存在多套当前整理方法，请先处理版本记录",
        )
    return recipes[0] if recipes else None


def _template_already_bound(project: Project, template_id: UUID, source_id: UUID) -> bool:
    return any(
        item.get("template_recipe_id") == str(template_id)
        and item.get("source_id") == str(source_id)
        for item in _stored_recipe_template_bindings(project)
    )


def _template_replay_drift(result: Any) -> list[dict[str, Any]]:
    replay = (result.source_snapshot or {}).get("recipe_replay") or {}
    drift = replay.get("drift") or []
    return list(drift) if isinstance(drift, list) else []


def _sanitation_operations_hash(operations: list[dict[str, Any]]) -> str:
    payload = json.dumps(
        canonicalize_sanitation_operations(operations),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _working_copy_proof(source: ProjectDataSource) -> tuple[Path | None, str | None]:
    if not source.working_uri:
        return None, None
    working_path = Path(source.working_uri)
    if not working_path.is_file():
        raise HTTPException(status_code=409, detail="当前分析副本不可用，请先重新整理数据")
    return working_path, fingerprint_file(working_path)


def _clear_visual_cleaning_metadata(source: ProjectDataSource) -> None:
    profile = dict(source.profile_data or {})
    if "visual_cleaning" in profile:
        profile.pop("visual_cleaning", None)
        source.profile_data = profile


async def _invalidate_visual_cleaning_metadata(
    db: AsyncSession,
    recipe: SanitationRecipeRecord,
) -> None:
    source = await db.get(ProjectDataSource, recipe.data_source_id)
    if source is not None:
        _clear_visual_cleaning_metadata(source)


def _stored_visual_cleaning_operations(
    source: ProjectDataSource,
    active_revision_id: UUID | None,
) -> list[dict[str, Any]] | None:
    visual_cleaning = (source.profile_data or {}).get("visual_cleaning")
    if not isinstance(visual_cleaning, dict) or "operations" not in visual_cleaning:
        # Old sources did not record which head operations came from the manual editor.
        # Preserve their recipe conservatively instead of guessing what may be removed.
        return None
    if (
        active_revision_id is None
        or str(visual_cleaning.get("active_revision_id") or "") != str(active_revision_id)
    ):
        # Manual steps are removable only while the exact revision they created
        # remains active. Another head must never inherit stale editor ownership.
        return None
    try:
        return canonicalize_visual_sanitation_operations(visual_cleaning.get("operations"))
    except SanitationContractError as exc:
        raise HTTPException(status_code=409, detail="已保存的可视化整理设置无法安全读取") from exc


async def _active_cleaning_recipe_snapshot(
    db: AsyncSession,
    *,
    project_id: UUID,
    source_id: UUID,
) -> tuple[
    SanitationRecipeRecord | None,
    SanitationRecipeRevisionRecord | None,
    list[dict[str, Any]],
]:
    """Read one current recipe head without creating or repairing any records."""

    recipe = await _single_recipe_for_source(
        db,
        project_id=project_id,
        source_id=source_id,
    )
    if recipe is None:
        return None, None, []
    if recipe.active_revision_id is None:
        raise HTTPException(status_code=409, detail="当前整理方法的版本记录不完整")
    revision = await sanitation_revision_or_none(
        db,
        recipe_id=recipe.id,
        revision_id=recipe.active_revision_id,
    )
    if revision is None:
        raise HTTPException(status_code=409, detail="当前整理方法的版本记录不完整")
    try:
        revision_operations = canonicalize_sanitation_operations(revision.operations)
        recipe_operations = canonicalize_sanitation_operations(recipe.operations)
    except SanitationContractError as exc:
        raise HTTPException(status_code=409, detail="当前整理方法无法安全读取") from exc
    if recipe_operations != revision_operations:
        raise HTTPException(status_code=409, detail="当前整理方法与版本记录不一致")
    return recipe, revision, revision_operations


def _visual_operation_key(operation: dict[str, Any]) -> tuple[str, str]:
    operation_name = str(operation.get("operation") or "")
    column = str(operation.get("column") or "")
    return operation_name, column


def _merge_visual_cleaning_operations(
    active_operations: list[dict[str, Any]],
    selected_operations: list[dict[str, Any]],
    previous_manual_operations: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    selected = canonicalize_visual_sanitation_operations(selected_operations)
    if not selected and not previous_manual_operations:
        raise SanitationContractError("当前没有可移除的手动整理操作")
    selected_keys = {_visual_operation_key(operation) for operation in selected}
    previous_manual_keys = {
        _visual_operation_key(operation) for operation in (previous_manual_operations or [])
    }
    retained = [
        operation
        for operation in canonicalize_sanitation_operations(active_operations)
        if _visual_operation_key(operation) not in selected_keys
        and _visual_operation_key(operation) not in previous_manual_keys
    ]
    return canonicalize_sanitation_operations([*retained, *selected])


def _materialized_cleaning_operations(
    active_operations: list[dict[str, Any]],
    result_operations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    provenance = [
        operation
        for operation in canonicalize_sanitation_operations(active_operations)
        if operation.get("operation") in SANITATION_PROVENANCE_OPERATIONS
    ]
    return canonicalize_sanitation_operations([*provenance, *result_operations])


def _visual_cleaning_proof_hash(
    selected_operations: list[dict[str, Any]],
    materialized_operations: list[dict[str, Any]],
) -> str:
    payload = json.dumps(
        {
            "version": 1,
            "selected_operations": canonicalize_visual_sanitation_operations(
                selected_operations
            ),
            "materialized_operations": canonicalize_sanitation_operations(
                materialized_operations
            ),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _cleaning_attempt_dir(
    project_id: UUID,
    source_id: UUID,
    *,
    purpose: Literal["previews", "attempts"],
) -> Path:
    return (
        settings.WORKSPACE_ROOT
        / str(project_id)
        / "sources"
        / str(source_id)
        / "working"
        / purpose
        / str(uuid4())
    )


def _enforce_visual_cleaning_source_limits(source_path: Path) -> None:
    try:
        source_size = source_path.stat().st_size
    except OSError as exc:
        raise HTTPException(status_code=409, detail="这份文件当前不可用，请重新添加后再试") from exc
    if source_size > settings.VISUAL_CLEANING_MAX_SOURCE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="这份文件太大，暂时不能直接整理。请先拆分文件后再试。",
        )
    if source_path.suffix.casefold() != ".xlsx":
        return
    try:
        with zipfile.ZipFile(source_path) as workbook:
            expanded_size = 0
            for item in workbook.infolist():
                if item.is_dir():
                    continue
                expanded_size += item.file_size
                if expanded_size > settings.VISUAL_CLEANING_MAX_XLSX_EXPANDED_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=(
                            "这份 Excel 展开后过大，暂时不能直接整理。"
                            "请先拆分工作表或文件后再试。"
                        ),
                    )
    except zipfile.BadZipFile:
        # The ordinary preflight reader will return the existing business-facing
        # invalid-file response. This guard is concerned only with bounded size.
        return


async def _run_preflight_in_thread(
    source_path: Path,
    output_dir: Path,
    *,
    recipe_operations: list[dict[str, Any]] | None = None,
) -> Any:
    """Keep blocking parsing off-loop and finish the worker before caller cleanup.

    Python cannot stop a running worker thread. If the request is cancelled, wait
    for that worker to finish before propagating cancellation so endpoint ``finally``
    blocks cannot delete an attempt directory while it is still being written.
    """

    worker = asyncio.create_task(
        asyncio.to_thread(
            run_preflight,
            source_path,
            output_dir,
            recipe_operations=recipe_operations,
        )
    )
    cancellation_requested = False
    while not worker.done():
        try:
            await asyncio.shield(worker)
        except asyncio.CancelledError:
            cancellation_requested = True
        except Exception:
            break
    if cancellation_requested:
        try:
            worker.result()
        except BaseException:
            pass
        raise asyncio.CancelledError
    return worker.result()


def _template_preview_payload(
    *,
    history: ProjectBundleSanitationHistory,
    source: ProjectDataSource,
    result: Any,
    current_recipe_active_revision_id: UUID | None,
    current_working_fingerprint: str | None,
) -> SanitationTemplatePreviewResponse:
    snapshot = result.source_snapshot or {}
    replay_drift = _template_replay_drift(result)
    return SanitationTemplatePreviewResponse(
        template_id=history.recipe_id,
        template_name=history.head.name,
        template_active_revision_id=history.head.active_revision_id,
        template_operations_hash=_sanitation_operations_hash(history.head.operations),
        source_id=source.id,
        source_fingerprint=result.input_fingerprint,
        preview_output_fingerprint=result.output_fingerprint,
        current_working_fingerprint=current_working_fingerprint,
        current_recipe_active_revision_id=current_recipe_active_revision_id,
        before=SanitationTemplateShape(
            rows=int(snapshot.get("original_rows") or 0),
            columns=int(snapshot.get("original_columns") or 0),
        ),
        after=SanitationTemplateShape(
            rows=int(snapshot.get("ready_rows") or 0),
            columns=int(snapshot.get("ready_columns") or 0),
        ),
        summary=(
            "这套方法与当前数据不完全匹配，暂时不会应用。"
            if replay_drift
            else "已完成试运行；确认后才会替换当前分析副本。"
        ),
        issues=result.issues,
        can_apply=not replay_drift,
    )


def _stored_analysis_playbooks(project: Project) -> list[AnalysisPlaybookResponse]:
    try:
        return [
            AnalysisPlaybookResponse.model_validate(item)
            for item in (project.extra_data or {}).get("analysis_playbooks") or []
        ]
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="项目中的可复用分析记录已损坏",
        ) from exc


def _analysis_playbook_id(query: str) -> str:
    query_key = normalize_query_key(query) or query.strip().casefold()
    return f"pb_{hashlib.sha256(query_key.encode('utf-8')).hexdigest()[:20]}"


def _stored_trusted_references(project: Project) -> list[TrustedProjectReferenceResponse]:
    try:
        return [
            TrustedProjectReferenceResponse.model_validate(item)
            for item in (project.extra_data or {}).get("trusted_references") or []
        ]
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="项目中的可信依据记录已损坏",
        ) from exc


def _trusted_reference_id(run_id: UUID) -> str:
    return f"ref_{hashlib.sha256(str(run_id).encode('utf-8')).hexdigest()[:20]}"


def _trusted_report_snapshot(report: dict[str, Any]) -> dict[str, Any]:
    metrics: list[dict[str, Any]] = []
    for item in report.get("metrics") or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        value = str(item.get("value") or "").strip()
        if not label or not value:
            continue
        context = str(item.get("context") or "").strip() or None
        metrics.append(
            {
                "label": label[:160],
                "value": value[:1000],
                "context": context[:1000] if context else None,
                "historical": True,
            }
        )
    conclusions = [
        str(item).strip()[:2000] for item in report.get("findings") or [] if str(item).strip()
    ][:100]
    return {
        "summary": str(report.get("summary") or "").strip()[:5000],
        "metrics": metrics[:100],
        "conclusions": conclusions,
        "historical": True,
    }


def _trusted_validation_evidence(
    tool_history: list[dict[str, Any]],
) -> list[TrustedProjectReferenceValidationEvidence]:
    evidence: list[TrustedProjectReferenceValidationEvidence] = []
    for item in tool_history:
        kind = str(item.get("kind") or "")
        if kind not in _TRUSTED_EVIDENCE_KINDS:
            continue
        raw_profile = item.get("profile") if isinstance(item.get("profile"), dict) else {}
        profile = {
            key: value for key, value in raw_profile.items() if key in _TRUSTED_PROFILE_FIELDS
        }
        evidence.append(
            TrustedProjectReferenceValidationEvidence(
                kind=kind,
                purpose=(str(item.get("purpose") or "").strip()[:1000] or None),
                result_name=(str(item.get("result_name") or "").strip()[:255] or None),
                status=(str(item.get("status") or "").strip()[:40] or None),
                relationship_key=(str(item.get("relationship_key") or "").strip()[:160] or None),
                contract_id=(str(item.get("contract_id") or "").strip()[:160] or None),
                profile=json.loads(json.dumps(profile, default=str, ensure_ascii=False)),
            )
        )
    return evidence[-20:]


def _save_trusted_references(
    project: Project,
    references: list[TrustedProjectReferenceResponse],
) -> None:
    project.extra_data = {
        **(project.extra_data or {}),
        "trusted_references": [item.model_dump(mode="json") for item in references],
    }


def _final_validation(
    tool_history: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    validations = [
        (index, item)
        for index, item in enumerate(tool_history)
        if item.get("kind") == "validation" and isinstance(item.get("profile"), dict)
    ]
    if not validations:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="只能保存已校验最终结果的分析",
        )
    validation_index, validation = validations[-1]
    data_steps = [
        (index, item)
        for index, item in enumerate(tool_history)
        if item.get("kind")
        in {
            "structured_query",
            "sql",
            "file_sql",
            "join",
            "aggregate",
            "business_rule_application",
        }
        and item.get("result_name")
    ]
    if not data_steps:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="这次分析没有可复用的数据调查步骤",
        )
    final_data_index, final_data_step = data_steps[-1]
    if validation_index < final_data_index or str(validation.get("result_name") or "") != str(
        final_data_step.get("result_name") or ""
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="最终业务结果尚未通过校验，不能保存为可复用分析",
        )
    if bool((validation.get("profile") or {}).get("truncated")):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="最终业务结果被截断，不能保存为可复用分析",
        )
    for item in tool_history[validation_index + 1 :]:
        if item.get("kind") != "python":
            continue
        is_validated_chart = bool(
            item.get("generated")
            and item.get("chart_type")
            and str(item.get("result_name") or "") == str(validation.get("result_name") or "")
        )
        if not is_validated_chart:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="最终校验后又执行了未类型化分析，不能保存为可复用分析",
            )
    return validation, final_data_step


def _source_logical_name(source: dict[str, Any]) -> str:
    return str(
        (source.get("profile") or {}).get("logical_name")
        or source.get("name")
        or source.get("view_name")
        or ""
    )


def _step_source_logical_roles(
    item: dict[str, Any],
    sources: list[dict[str, Any]],
) -> list[str]:
    source_refs = [ref for ref in item.get("source_refs") or [] if isinstance(ref, dict)]
    referenced_ids = {
        str(value)
        for value in [item.get("source_id"), *[ref.get("source_id") for ref in source_refs]]
        if value
    }
    referenced_names = {
        str(ref.get("source_logical_name") or "")
        for ref in source_refs
        if ref.get("source_logical_name")
    }
    sql = str(item.get("sql") or item.get("compiled_sql") or "").casefold()
    matched: list[str] = []
    for source in sources:
        source_id = str(source.get("id") or "")
        logical_name = _source_logical_name(source)
        query_name = str(source.get("view_name") or "")
        if (
            source_id in referenced_ids
            or logical_name in referenced_names
            or (query_name and query_name.casefold() in sql)
        ) and logical_name not in matched:
            matched.append(logical_name)
    if not matched and len(sources) == 1:
        logical_name = _source_logical_name(sources[0])
        if logical_name:
            matched.append(logical_name)
    return sorted(matched)


def _playbook_canonical_type(raw_type: str) -> str:
    canonical = _canonical_dtype(raw_type)
    return canonical if canonical in {"boolean", "number", "datetime", "text"} else "unknown"


def _source_structure(
    source: dict[str, Any],
) -> tuple[list[str], list[dict[str, str | None]]]:
    profile = source.get("profile") or {}
    tables = [
        str(table.get("name") or "") for table in profile.get("tables") or [] if table.get("name")
    ][:100]
    columns: list[dict[str, str | None]] = []
    for column in (profile.get("schema") or {}).get("columns") or []:
        name = str(column.get("name") or "")
        if not name:
            continue
        raw_type = str(column.get("type") or column.get("dtype") or "unknown")
        columns.append(
            {
                "table": None,
                "name": name,
                "data_type": raw_type,
                "canonical_type": _playbook_canonical_type(raw_type),
            }
        )
    for table in profile.get("tables") or []:
        table_name = str(table.get("name") or "")
        for column in table.get("columns") or []:
            name = str(column.get("name") or "")
            if not table_name or not name:
                continue
            raw_type = str(column.get("type") or column.get("dtype") or "unknown")
            columns.append(
                {
                    "table": table_name,
                    "name": name,
                    "data_type": raw_type,
                    "canonical_type": _playbook_canonical_type(raw_type),
                }
            )
    unique_columns = {
        (str(item.get("table") or ""), str(item.get("name") or "")): item for item in columns
    }
    return sorted(tables), sorted(
        unique_columns.values(),
        key=lambda item: (str(item.get("table") or ""), str(item.get("name") or "")),
    )[:500]


def _playbook_source_roles(
    sources: list[dict[str, Any]],
    tool_history: list[dict[str, Any]],
    validation: dict[str, Any],
) -> list[AnalysisPlaybookSourceRole]:
    referenced_names: set[str] = set()
    for step in tool_history:
        if step.get("kind") in {"structured_query", "sql", "file_sql"}:
            referenced_names.update(_step_source_logical_roles(step, sources))
    validation_refs = (validation.get("profile") or {}).get("source_refs") or []
    referenced_names.update(_step_source_logical_roles({"source_refs": validation_refs}, sources))

    roles: list[AnalysisPlaybookSourceRole] = []
    for source in sources:
        if source.get("kind") not in {"file", "connection"}:
            continue
        logical_name = _source_logical_name(source)
        if logical_name not in referenced_names:
            continue
        tables, columns = _source_structure(source)
        roles.append(
            AnalysisPlaybookSourceRole(
                logical_name=logical_name[:255],
                source_kind=source["kind"],
                tables=tables,
                columns=columns,
                schema_signature=_profile_schema_signature(source.get("profile") or {}),
            )
        )
    return sorted(roles, key=lambda item: (item.logical_name, item.source_kind))


def _typed_structured_query_plan(
    item: dict[str, Any],
) -> AnalysisPlaybookStructuredQueryPlan | None:
    """Copy only portable declarative intent from a runtime query receipt."""

    raw_plan = item.get("query_plan")
    if not isinstance(raw_plan, dict):
        return None
    try:
        return AnalysisPlaybookStructuredQueryPlan.model_validate(
            {
                "table": raw_plan.get("table") or raw_plan.get("table_or_view"),
                "dimensions": raw_plan.get("dimensions") or [],
                "metrics": raw_plan.get("metrics") or [],
                "filters": raw_plan.get("filters") or [],
                "sort": raw_plan.get("sort") or [],
                "limit": raw_plan.get("limit", 1000),
            }
        )
    except ValidationError:
        return None


def _business_playbook_steps(
    tool_history: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    source_roles: list[AnalysisPlaybookSourceRole],
    relationships: dict[str, dict[str, Any]],
) -> tuple[list[AnalysisPlaybookStep], dict[str, str]]:
    adapter = TypeAdapter(AnalysisPlaybookStep)
    steps: list[AnalysisPlaybookStep] = []
    result_aliases: dict[str, str] = {}
    validation_profiles = {
        str(item.get("result_name") or ""): item.get("profile") or {}
        for item in tool_history
        if item.get("kind") == "validation" and item.get("result_name")
    }

    def output_alias(item: dict[str, Any]) -> str:
        actual = str(item.get("result_name") or "").strip()
        if not actual:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="调查步骤缺少输出绑定，不能保存为可复用分析",
            )
        if actual not in result_aliases:
            result_aliases[actual] = f"result_{len(result_aliases) + 1}"
        return result_aliases[actual]

    def input_alias(item: dict[str, Any], key: str) -> str:
        actual = str(item.get(key) or "").strip()
        if not actual or actual not in result_aliases:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"调查步骤缺少已生成的 {key} 绑定，不能保存为可复用分析",
            )
        return result_aliases[actual]

    def append_step(payload: dict[str, Any]) -> None:
        payload = {"order": len(steps) + 1, **payload}
        try:
            steps.append(adapter.validate_python(payload))
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="调查步骤缺少严格的类型化绑定，不能保存为可复用分析",
            ) from exc

    for item in tool_history:
        kind = str(item.get("kind") or "")
        if kind in {"structured_query", "sql", "file_sql"}:
            logical_roles = _step_source_logical_roles(item, sources)
            if not logical_roles:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="读取步骤无法绑定项目中的逻辑数据角色",
                )
            structured_plan = (
                _typed_structured_query_plan(item) if kind == "structured_query" else None
            )
            if structured_plan is not None and len(logical_roles) == 1:
                append_step(
                    {
                        "kind": "structured_query",
                        "summary": f"按类型化计划查询逻辑数据角色：{logical_roles[0]}",
                        "input_results": [],
                        "output_result": output_alias(item),
                        "source_role": logical_roles[0],
                        "plan": structured_plan.model_dump(mode="json"),
                    }
                )
                continue
            append_step(
                {
                    "kind": "read_data",
                    "summary": f"读取逻辑数据角色：{'、'.join(logical_roles)}",
                    "input_results": [],
                    "output_result": output_alias(item),
                    "source_roles": logical_roles,
                    "required_columns": [],
                }
            )
            continue
        if kind == "business_rule_application":
            rule_key = str(item.get("rule_key") or item.get("knowledge_key") or "")
            action_kind = str(item.get("action_kind") or "")
            raw_values = [str(value) for value in item.get("values") or []]
            if not action_kind and item.get("operator") and raw_values:
                action_kind = "value_filter"
            action_labels = {
                "value_filter": "重新应用已确认筛选口径",
                "identity": "重新确认业务身份口径",
                "metric_column": "重新绑定已确认指标列",
                "metric_formula": "重新计算已确认指标口径",
            }
            append_step(
                {
                    "kind": "apply_rule",
                    "summary": f"{action_labels.get(action_kind, '重新应用已确认口径')} {rule_key}",
                    "input_results": [input_alias(item, "source_result")],
                    "output_result": output_alias(item),
                    "rule_key": rule_key,
                    "action_kind": action_kind,
                    "column": str(item.get("column") or ""),
                    "operator": item.get("operator") if action_kind == "value_filter" else None,
                    "values": raw_values if action_kind == "value_filter" else None,
                    "definition_hash": item.get("definition_hash"),
                }
            )
            continue
        if kind in {"relationship_validation", "relationship_application"}:
            profile = item.get("profile") or {}
            relationship_key = str(item.get("relationship_key") or "") or None
            relationship = relationships.get(relationship_key or "") or {}
            definition = relationship.get("definition") or {}
            normalization = str(
                profile.get("normalization")
                or item.get("normalization")
                or definition.get("normalization")
                or "exact"
            )
            if normalization == "auto":
                normalization = "exact"
            append_step(
                {
                    "kind": "validate_relationship",
                    "summary": "在当前数据上重新验证关联可靠性",
                    "input_results": [
                        input_alias(item, "left_result"),
                        input_alias(item, "right_result"),
                    ],
                    "output_result": None,
                    "relationship_key": relationship_key,
                    "definition_hash": item.get("definition_hash"),
                    "left_key": item.get("left_key") or profile.get("left_key"),
                    "right_key": item.get("right_key") or profile.get("right_key"),
                    "normalization": normalization,
                }
            )
            continue
        if kind == "join":
            profile = item.get("profile") or {}
            relationship_key = str(item.get("relationship_key") or "") or None
            relationship = relationships.get(relationship_key or "") or {}
            definition = relationship.get("definition") or {}
            normalization = str(
                profile.get("normalization")
                or item.get("normalization")
                or definition.get("normalization")
                or "exact"
            )
            if normalization == "auto":
                normalization = "exact"
            append_step(
                {
                    "kind": "join",
                    "summary": "按已验证关系重新关联当前数据",
                    "input_results": [
                        input_alias(item, "left_result"),
                        input_alias(item, "right_result"),
                    ],
                    "output_result": output_alias(item),
                    "relationship_key": relationship_key,
                    "definition_hash": item.get("definition_hash"),
                    "left_key": item.get("left_key") or profile.get("left_key"),
                    "right_key": item.get("right_key") or profile.get("right_key"),
                    "join_mode": item.get("how") or definition.get("default_join"),
                    "normalization": normalization,
                }
            )
            continue
        if kind == "aggregate":
            operation = str(item.get("operation") or "")
            group_by = [str(value) for value in item.get("group_by") or []]
            append_step(
                {
                    "kind": "aggregate",
                    "summary": f"按 {('、'.join(group_by) or '整体')} 执行 {operation} 汇总",
                    "input_results": [input_alias(item, "source_result")],
                    "output_result": output_alias(item),
                    "group_by": group_by,
                    "operation": operation,
                    "value_column": item.get("value_column"),
                    "output_column": str(item.get("output_column") or ""),
                }
            )
            continue
        if kind == "validation":
            profile = item.get("profile") or {}
            append_step(
                {
                    "kind": "validate_result",
                    "summary": "在当前数据上重新校验最终结果",
                    "input_results": [input_alias(item, "result_name")],
                    "output_result": None,
                    "key_columns": [str(value) for value in (profile.get("keys") or {})],
                    "numeric_columns": [str(value) for value in (profile.get("numeric") or {})],
                    "must_not_be_truncated": True,
                }
            )
            continue
        if kind != "python":
            continue
        if not item.get("chart_type"):
            if not result_aliases:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="补充分析没有可重新绑定的输入结果",
                )
            append_step(
                {
                    "kind": "analyze",
                    "summary": "基于当前结果重新规划补充分析",
                    "input_results": list(dict.fromkeys(result_aliases.values()))[:20],
                    "output_result": None,
                    "analysis_kind": "custom",
                    "requires_replanning": True,
                }
            )
            continue
        actual_result = str(item.get("result_name") or "")
        profile = validation_profiles.get(actual_result) or {}
        keys = [str(value) for value in (profile.get("keys") or {})]
        numeric = [str(value) for value in (profile.get("numeric") or {})]
        columns = [str(value) for value in profile.get("columns") or []]
        chart_type = str(item.get("chart_type") or "")
        x = str(item.get("x") or "")
        y = str(item.get("y") or "") or None
        value = str(item.get("value") or "") or None
        if not x:
            x = next(iter(keys or numeric or columns), "")
        if chart_type == "heatmap":
            y = y or (keys[1] if len(keys) > 1 else None)
            value = value or next(iter(numeric), None)
        elif chart_type in {"bar", "line", "scatter"}:
            y = y or next(iter(numeric), None)
        append_step(
            {
                "kind": "visualize",
                "summary": f"用当前结果重新生成 {chart_type} 图表",
                "input_results": [input_alias(item, "result_name")],
                "output_result": None,
                "chart_type": chart_type,
                "x": x,
                "y": y,
                "value": value,
                "color": str(item.get("color") or "") or None,
            }
        )

    contract_columns: set[str] = set()
    for step in steps:
        for key in ("column", "left_key", "right_key", "value_column", "output_column"):
            value = getattr(step, key, None)
            if value:
                contract_columns.add(str(value))
        for key in ("group_by", "key_columns", "numeric_columns"):
            contract_columns.update(str(value) for value in getattr(step, key, []) or [])
        for key in ("x", "y", "value", "color"):
            value = getattr(step, key, None)
            if value:
                contract_columns.add(str(value))
    role_contracts = {role.logical_name: role for role in source_roles}
    for step in steps:
        if step.kind != "read_data":
            continue
        required: list[str] = []
        for logical_name in step.source_roles:
            role = role_contracts.get(logical_name)
            if role is None:
                continue
            for column in role.columns:
                qualified = f"{column.table}.{column.name}" if column.table else column.name
                if column.name in contract_columns or qualified in contract_columns:
                    required.append(qualified)
        if not required:
            for logical_name in step.source_roles:
                role = role_contracts.get(logical_name)
                if role is None:
                    continue
                required.extend(
                    f"{column.table}.{column.name}" if column.table else column.name
                    for column in role.columns
                )
        step.required_columns = list(dict.fromkeys(required))[:200]
    return steps, result_aliases


def _validation_summary(
    validation: dict[str, Any],
    result_aliases: dict[str, str],
) -> AnalysisPlaybookValidationSummary:
    profile = validation.get("profile") or {}
    actual_result = str(validation.get("result_name") or "")
    input_result = result_aliases.get(actual_result)
    if input_result is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="最终校验无法绑定类型化结果",
        )
    return AnalysisPlaybookValidationSummary(
        input_result=input_result,
        columns=[str(item) for item in profile.get("columns") or []][:500],
        key_columns=[str(item) for item in (profile.get("keys") or {})][:100],
        numeric_columns=[str(item) for item in (profile.get("numeric") or {})][:100],
        must_not_be_truncated=True,
    )


def _playbook_shape_hash(
    source_roles: list[AnalysisPlaybookSourceRole],
    steps: list[AnalysisPlaybookStep],
    validation: AnalysisPlaybookValidationSummary,
    *,
    schema_version: Literal[2, 3],
    execution_mode: Literal["system_structured_query", "agent_replan_required"],
) -> str:
    payload = {
        "schema_version": schema_version,
        "execution_mode": execution_mode,
        "binding_policy": "logical_role_then_schema",
        "requires_revalidation": True,
        "source_roles": [item.model_dump(mode="json") for item in source_roles],
        "steps": [item.model_dump(mode="json") for item in steps],
        "validation": validation.model_dump(mode="json"),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def _playbook_execution_mode(
    *,
    tool_history: list[dict[str, Any]],
    source_roles: list[AnalysisPlaybookSourceRole],
    steps: list[AnalysisPlaybookStep],
    validation: dict[str, Any],
    final_data_step: dict[str, Any],
    playbook_id: str,
) -> Literal["system_structured_query", "agent_replan_required"]:
    """Classify only the small slice the application can replay without model judgment."""

    allowed_kinds = {
        "structured_query",
        "validation",
        "golden_regression_validation",
        "analysis_playbook_execution",
    }
    final_result_name = str(validation.get("result_name") or "")
    for item in tool_history:
        kind = str(item.get("kind") or "")
        if kind in allowed_kinds:
            continue
        presentation_only = bool(
            kind == "python"
            and item.get("generated") is True
            and item.get("chart_type")
            and int(item.get("images") or 0) > 0
            and str(item.get("result_name") or "") == final_result_name
        )
        if not presentation_only:
            return "agent_replan_required"
    structured_receipts = [
        item for item in tool_history if item.get("kind") == "structured_query"
    ]
    structured_steps = [step for step in steps if step.kind == "structured_query"]
    validation_steps = [step for step in steps if step.kind == "validate_result"]
    execution_receipts = [
        item for item in tool_history if item.get("kind") == "analysis_playbook_execution"
    ]
    if (
        len(source_roles) != 1
        or len(structured_receipts) != 1
        or len(structured_steps) != 1
        or len(validation_steps) != 1
        or len(execution_receipts) > 1
        or len(steps) != 2
    ):
        return "agent_replan_required"
    receipt = structured_receipts[0]
    source_ids = {
        str(value)
        for value in [
            receipt.get("source_id"),
            *[
                ref.get("source_id")
                for ref in receipt.get("source_refs") or []
                if isinstance(ref, dict)
            ],
        ]
        if value
    }
    if len(source_ids) != 1:
        return "agent_replan_required"
    if final_data_step is not receipt:
        return "agent_replan_required"
    if str(validation.get("result_name") or "") != str(receipt.get("result_name") or ""):
        return "agent_replan_required"
    if bool(receipt.get("truncated")) or str(receipt.get("result_completeness") or "") not in {
        "",
        "complete",
    }:
        return "agent_replan_required"
    if execution_receipts:
        execution_receipt = execution_receipts[0]
        role = source_roles[0]
        step = structured_steps[0]
        profile = dict(validation.get("profile") or {})
        expected_shape_hash = _playbook_shape_hash(
            source_roles,
            steps,
            _validation_summary(validation, {str(validation.get("result_name")): step.output_result}),
            schema_version=3,
            execution_mode="system_structured_query",
        )
        if not (
            execution_receipt.get("status") == "validated"
            and execution_receipt.get("truncated") is False
            and execution_receipt.get("playbook_id") == playbook_id
            and execution_receipt.get("playbook_shape_hash") == expected_shape_hash
            and execution_receipt.get("source_role") == role.logical_name
            and execution_receipt.get("source_kind") == role.source_kind
            and execution_receipt.get("source_schema_signature") == role.schema_signature
            and str(execution_receipt.get("source_id") or "") in source_ids
            and execution_receipt.get("result_name") == validation.get("result_name")
            and execution_receipt.get("result_hash") == validation.get("result_hash")
            and execution_receipt.get("plan_hash")
            == stable_payload_hash(step.plan.model_dump(mode="json"))
            and execution_receipt.get("profile_hash") == stable_payload_hash(profile)
            and execution_receipt.get("validation_hash") == stable_payload_hash(validation)
            and execution_receipt.get("row_count") == profile.get("materialized_rows")
            and execution_receipt.get("execution_backend") == profile.get("execution_backend")
        ):
            return "agent_replan_required"
    return "system_structured_query"


async def _upsert_candidate_knowledge(
    db: AsyncSession,
    *,
    project_id: UUID,
    key: str,
    value: str,
    entry_type: str,
    confidence: float,
    evidence: list[dict[str, Any]],
    definition: dict[str, Any] | None = None,
    validity: str = "active",
) -> None:
    result = await db.execute(
        select(SemanticEntry).where(
            SemanticEntry.project_id == project_id,
            SemanticEntry.key == key[:160],
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        if existing.state in {"confirmed", "locked"}:
            return
        user_governed = any(
            isinstance(item, dict)
            and item.get("kind")
            in {"semantic_candidate_ignored", "relationship_validation_requested"}
            for item in (existing.evidence or [])
        )
        if existing.state == "candidate" and user_governed:
            # A fresh preflight must not move the revision selected or dismissed
            # by the user while that governance decision is still current.
            return
        if (
            existing.state == "candidate"
            and existing.validity == "stale"
            and existing.source == "user"
        ):
            return
        reactivate_pruned_name_match = (
            existing.state == "candidate"
            and existing.source == "inferred"
            and existing.is_active is False
            and _is_pure_inferred_name_match_evidence(existing.evidence)
            and entry_type == "relationship"
            and _is_pure_inferred_name_match_evidence(evidence)
        )
        next_confidence = max(float(existing.confidence or 0), confidence)
        if (
            existing.value == value
            and existing.confidence == next_confidence
            and existing.evidence == evidence
            and existing.definition == definition
            and existing.validity == validity
            and not reactivate_pruned_name_match
        ):
            return
        existing.value = value
        existing.confidence = next_confidence
        existing.evidence = evidence
        existing.definition = definition
        existing.validity = validity
        if reactivate_pruned_name_match:
            existing.is_active = True
            reset_semantic_execution_proof(existing)
        await append_semantic_revision(
            db,
            existing,
            mutation_kind="candidate_refreshed",
            actor_source="inferred",
            reason="根据当前数据更新候选理解",
            expected_active_revision_id=existing.active_revision_id,
        )
        return
    entry = SemanticEntry(
        project_id=project_id,
        key=key[:160],
        value=value,
        entry_type=entry_type,
        state="candidate",
        confidence=confidence,
        definition=definition,
        validity=validity,
        evidence=evidence,
        source="inferred",
    )
    db.add(entry)
    await db.flush()
    await append_semantic_revision(
        db,
        entry,
        mutation_kind="candidate_created",
        actor_source="inferred",
        reason="根据数据预检生成候选理解",
    )


def _relationship_pair_identity(
    left_endpoint: dict[str, Any],
    right_endpoint: dict[str, Any],
    *,
    left_source_id: UUID | str | None = None,
    right_source_id: UUID | str | None = None,
) -> str:
    scoped = [
        {
            "source_id": str(source_id or ""),
            **{
                key: endpoint[key]
                for key in (
                    "source_logical_name",
                    "source_kind",
                    "table_or_view",
                    "column",
                )
            },
        }
        for endpoint, source_id in (
            (left_endpoint, left_source_id),
            (right_endpoint, right_source_id),
        )
    ]
    scoped.sort(
        key=lambda item: json.dumps(
            item,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return json.dumps(
        scoped,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _relationship_definition_pair_identity(
    definition: dict[str, Any] | None,
) -> str | None:
    if not isinstance(definition, dict):
        return None
    left = definition.get("left")
    right = definition.get("right")
    required = {"source_logical_name", "source_kind", "table_or_view", "column"}
    if (
        not isinstance(left, dict)
        or not isinstance(right, dict)
        or not required.issubset(left)
        or not required.issubset(right)
    ):
        return None
    return _relationship_pair_identity(left, right)


def _relationship_candidate_score(
    left_endpoint: dict[str, Any],
    right_endpoint: dict[str, Any],
) -> float:
    """Rank bounded name matches without treating them as validated joins."""

    score = 0.55
    left_column = str(left_endpoint.get("column") or "")
    right_column = str(right_endpoint.get("column") or "")
    if left_column.casefold() == right_column.casefold():
        score += 0.08
    if left_column.casefold().endswith("id") and right_column.casefold().endswith("id"):
        score += 0.04
    left_type = str(left_endpoint.get("data_type") or "unknown").casefold()
    right_type = str(right_endpoint.get("data_type") or "unknown").casefold()
    if left_type == right_type and left_type not in {"", "unknown"}:
        score += 0.04
    if left_endpoint.get("table_or_view") != right_endpoint.get("table_or_view"):
        score += 0.02
    if left_endpoint.get("source_logical_name") != right_endpoint.get(
        "source_logical_name"
    ):
        score += 0.02
    return round(min(score, 0.75), 6)


def _is_pure_inferred_name_match_evidence(evidence: object) -> bool:
    """Only untouched name-match evidence is eligible for automatic pruning."""

    return bool(evidence) and isinstance(evidence, list) and all(
        isinstance(item, dict) and item.get("kind") == "matching_column_names"
        for item in evidence
    )


async def _retire_unretained_inferred_relationship_candidates(
    db: AsyncSession,
    *,
    project_id: UUID,
    retained_keys: set[str],
) -> None:
    """Tombstone obsolete discovery-only heads without touching governed work."""

    user_revision_result = await db.execute(
        select(SemanticEntryRevision.semantic_entry_id).where(
            SemanticEntryRevision.project_id == project_id,
            or_(
                SemanticEntryRevision.actor_source == "user",
                SemanticEntryRevision.mutation_kind == "created",
            ),
        )
    )
    user_touched_ids = set(user_revision_result.scalars())
    result = await db.execute(
        select(SemanticEntry)
        .where(
            SemanticEntry.project_id == project_id,
            SemanticEntry.entry_type == "relationship",
            SemanticEntry.state == "candidate",
            SemanticEntry.source == "inferred",
            SemanticEntry.is_active.is_(True),
        )
        .with_for_update()
    )
    for entry in result.scalars():
        if (
            entry.key in retained_keys
            or entry.id in user_touched_ids
            or not _is_pure_inferred_name_match_evidence(entry.evidence)
        ):
            continue
        previous_revision_id = entry.active_revision_id
        entry.is_active = False
        entry.validity = "stale"
        reset_semantic_execution_proof(entry)
        await append_semantic_revision(
            db,
            entry,
            mutation_kind="candidate_pruned",
            actor_source="system",
            reason="当前数据预检未保留这项低证据关联候选",
            expected_active_revision_id=previous_revision_id,
        )


async def _persist_preflight_candidates(
    db: AsyncSession,
    source: ProjectDataSource,
) -> None:
    profile = source.profile_data or {}
    evidence = [{"source_id": str(source.id), "source": source.name, "kind": "preflight"}]
    grain = sorted(
        (
            profile.get("schema", {}).get("candidate_grain", [])
            or profile.get("preanalysis", {}).get("candidate_grain", [])
        ),
        key=lambda item: (
            int(item.get("evidence_priority", 9)),
            -float(item.get("uniqueness", 0)),
        ),
    )
    if grain:
        best = grain[0]
        grain_column = str(best.get("column") or "")
        grain_label = (
            f"{best.get('table')}.{grain_column}"
            if best.get("table")
            else grain_column
        )
        await _upsert_candidate_knowledge(
            db,
            project_id=source.project_id,
            key=f"grain:{source.id}",
            value=(
                f"{source.name} 每行可能由“{grain_label}”标识，"
                f"唯一率 {float(best.get('uniqueness', 0)):.1%}"
            ),
            entry_type="dimension",
            confidence=min(0.9, float(best.get("uniqueness", 0))),
            evidence=evidence,
        )
    amount_hints = ("amount", "revenue", "sales", "gmv", "金额", "收入", "销售", "实付")
    for column in _profile_column_details(profile):
        column_name = str(column.get("name") or "")
        if any(hint in column_name.lower() for hint in amount_hints):
            await _upsert_candidate_knowledge(
                db,
                project_id=source.project_id,
                key=f"metric_candidate:{source.id}:{column_name}",
                value=f"{source.name} 的“{column_name}”可能是金额指标，具体收入口径仍需业务确认",
                entry_type="metric",
                confidence=0.65,
                evidence=evidence,
            )

    governed_result = await db.execute(
        select(SemanticEntry).where(
            SemanticEntry.project_id == source.project_id,
            SemanticEntry.entry_type == "relationship",
            SemanticEntry.state.in_(("confirmed", "locked")),
            SemanticEntry.is_active.is_(True),
        )
    )
    governed_relationship_pairs = {
        pair_identity
        for item in governed_result.scalars()
        if (pair_identity := _relationship_definition_pair_identity(item.definition))
        is not None
    }
    declared_relationship_pairs: set[str] = set()
    declared_portable_pairs: set[str] = set()
    logical_name = str(profile.get("logical_name") or source.name)
    tables = [item for item in profile.get("tables") or [] if isinstance(item, dict)]
    for relationship in profile.get("preanalysis", {}).get("relationship_evidence", []):
        if (
            not isinstance(relationship, dict)
            or relationship.get("kind") != "declared_foreign_key"
            or relationship.get("catalog_verified") is not True
            or relationship.get("binding_complete") is not True
        ):
            continue
        source_binding = relationship.get("source") or {}
        target_binding = relationship.get("target") or {}
        source_columns = [str(item) for item in source_binding.get("columns") or []]
        target_columns = [str(item) for item in target_binding.get("columns") or []]
        if len(source_columns) != 1 or len(target_columns) != 1:
            # The current executable relationship contract is column-to-column.
            # Keep composite FK evidence in preanalysis, but do not pretend it can
            # already be executed as a semantic definition.
            continue

        def table_for(binding: dict[str, Any]) -> dict[str, Any] | None:
            table_name = str(binding.get("table") or "")
            schema_name = str(binding.get("schema") or "")
            exact = next(
                (
                    table
                    for table in tables
                    if str(table.get("name") or "") == table_name
                    and str(table.get("schema") or "") == schema_name
                ),
                None,
            )
            return exact or next(
                (table for table in tables if str(table.get("name") or "") == table_name),
                None,
            )

        source_table = table_for(source_binding)
        target_table = table_for(target_binding)
        if source_table is None or target_table is None:
            continue

        def endpoint(
            table: dict[str, Any],
            column_name: str,
        ) -> dict[str, Any] | None:
            column = next(
                (
                    item
                    for item in table.get("columns") or []
                    if str(item.get("name") or "") == column_name
                ),
                None,
            )
            if column is None:
                return None
            table_name = str(table.get("name") or "")
            return {
                "source_logical_name": logical_name,
                "source_kind": source.kind,
                "table_or_view": table_name,
                "column": column_name,
                "data_type": str(column.get("type") or column.get("dtype") or "unknown"),
                "schema_signature": _profile_schema_signature(profile, table_name),
            }

        left_endpoint = endpoint(source_table, source_columns[0])
        right_endpoint = endpoint(target_table, target_columns[0])
        if left_endpoint is None or right_endpoint is None:
            continue
        pair_identity = _relationship_pair_identity(
            left_endpoint,
            right_endpoint,
            left_source_id=source.id,
            right_source_id=source.id,
        )
        declared_relationship_pairs.add(pair_identity)
        portable_pair_identity = _relationship_pair_identity(left_endpoint, right_endpoint)
        declared_portable_pairs.add(portable_pair_identity)
        if portable_pair_identity in governed_relationship_pairs:
            # The governed head already represents this declared FK. Keep it
            # untouched and avoid a second candidate for the same logical pair.
            continue
        pair_hash = hashlib.sha256(pair_identity.encode("utf-8")).hexdigest()[:12]
        left_label = (
            f"{source.name}.{left_endpoint['table_or_view']}.{left_endpoint['column']}"
        )
        right_label = (
            f"{source.name}.{right_endpoint['table_or_view']}.{right_endpoint['column']}"
        )
        await _upsert_candidate_knowledge(
            db,
            project_id=source.project_id,
            key=f"relationship_candidate:fk:{pair_hash}",
            value=f"数据库声明的可能关联：{left_label} → {right_label}",
            entry_type="relationship",
            confidence=0.85,
            definition={
                "version": 1,
                "left": left_endpoint,
                "right": right_endpoint,
                "normalization": "exact",
                "cardinality": "many_to_one",
                "default_join": "left",
                "minimum_left_match_rate": 0.8,
                "maximum_expansion_ratio": 1.2,
            },
            validity="unverified",
            evidence=[
                {
                    "kind": "declared_foreign_key",
                    "source_id": str(source.id),
                    "constraint_name": relationship.get("constraint_name"),
                    "sources": [left_label, right_label],
                    "catalog_verified": True,
                    "automatic_confirmation": False,
                    "requires_value_validation": True,
                    "note": "数据库约束只作为候选证据，实际使用前仍会检查匹配率和重复扩张",
                }
            ],
        )

    source_result = await db.execute(
        select(ProjectDataSource).where(
            ProjectDataSource.project_id == source.project_id,
            ProjectDataSource.status != "superseded",
        )
    )
    column_sources: dict[str, list[dict[str, Any]]] = {}
    for item in source_result.scalars():
        if (item.profile_data or {}).get("is_current") is False:
            continue
        for column in _profile_column_details(item.profile_data or {}):
            column_name = str(column.get("name") or "")
            normalized = _canonical_column(column_name)
            if normalized:
                table = str(column.get("table") or "") or None
                profile = item.profile_data or {}
                logical_name = str(profile.get("logical_name") or item.name)
                endpoint = {
                    "source_logical_name": logical_name,
                    "source_kind": item.kind,
                    "table_or_view": table or _view_name(item),
                    "column": column_name,
                    "data_type": str(column.get("type") or column.get("dtype") or "unknown"),
                    "schema_signature": _profile_schema_signature(profile, table),
                }
                column_sources.setdefault(normalized, []).append(
                    {
                        "endpoint": endpoint,
                        "source_id": str(item.id),
                        "label": (f"{item.name}.{table + '.' if table else ''}{column_name}"),
                    }
                )
    ranked_inferred_candidates: list[dict[str, Any]] = []
    for normalized, candidates in sorted(column_sources.items()):
        unique_candidates_by_identity = {
            json.dumps(
                {
                    "endpoint": item["endpoint"],
                    "source_id": item["source_id"],
                },
                sort_keys=True,
                ensure_ascii=False,
            ): item
            for item in candidates
        }
        unique_candidates = [
            unique_candidates_by_identity[key]
            for key in sorted(unique_candidates_by_identity)
        ]
        endpoint_count = len(unique_candidates)
        considered_candidates = unique_candidates[:_MAX_RELATIONSHIP_ENDPOINTS_PER_COLUMN]
        ranked_group: list[dict[str, Any]] = []
        for left, right in combinations(considered_candidates, 2):
            left_endpoint = left["endpoint"]
            right_endpoint = right["endpoint"]
            if (
                left_endpoint["source_logical_name"]
                == right_endpoint["source_logical_name"]
                and left_endpoint["source_kind"] == right_endpoint["source_kind"]
                and left["source_id"] != right["source_id"]
            ):
                # A portable relationship cannot distinguish two active sources
                # with the same logical role. Runtime resolution also fails closed,
                # so do not create a misleading same-role name-match candidate.
                continue
            pair_identity = _relationship_pair_identity(
                left_endpoint,
                right_endpoint,
                left_source_id=left["source_id"],
                right_source_id=right["source_id"],
            )
            if pair_identity in declared_relationship_pairs:
                continue
            portable_pair_identity = _relationship_pair_identity(
                left_endpoint,
                right_endpoint,
            )
            if portable_pair_identity in (
                declared_portable_pairs | governed_relationship_pairs
            ):
                continue
            pair_hash = hashlib.sha256(pair_identity.encode("utf-8")).hexdigest()[:12]
            definition = {
                "version": 1,
                "left": left_endpoint,
                "right": right_endpoint,
                "normalization": (
                    "exact"
                    if left_endpoint["column"].casefold() == right_endpoint["column"].casefold()
                    else "auto"
                ),
                "cardinality": None,
                "default_join": "left",
                "minimum_left_match_rate": 0.8,
                "maximum_expansion_ratio": 1.2,
            }
            ranked_group.append(
                {
                    "normalized": normalized,
                    "pair_identity": pair_identity,
                    "pair_hash": pair_hash,
                    "left": left,
                    "right": right,
                    "definition": definition,
                    "score": _relationship_candidate_score(
                        left_endpoint,
                        right_endpoint,
                    ),
                    "endpoint_count": endpoint_count,
                    "considered_endpoint_count": len(considered_candidates),
                    "possible_pair_count": endpoint_count * (endpoint_count - 1) // 2,
                }
            )
        ranked_group.sort(key=lambda item: (-item["score"], item["pair_identity"]))
        retained_group = ranked_group[:_MAX_INFERRED_RELATIONSHIPS_PER_COLUMN]
        for rank, item in enumerate(retained_group, start=1):
            item["group_rank"] = rank
            item["group_retained_count"] = len(retained_group)
            ranked_inferred_candidates.append(item)

    ranked_inferred_candidates.sort(
        key=lambda item: (
            -item["score"],
            item["normalized"],
            item["pair_identity"],
        )
    )
    retained_inferred_candidates = ranked_inferred_candidates[
        :_MAX_INFERRED_RELATIONSHIPS_PER_PROJECT
    ]
    retained_inferred_keys: set[str] = set()
    for project_rank, item in enumerate(
        retained_inferred_candidates,
        start=1,
    ):
        left = item["left"]
        right = item["right"]
        candidate_key = f"relationship_candidate:{item['normalized']}:{item['pair_hash']}"
        retained_inferred_keys.add(candidate_key[:160])
        await _upsert_candidate_knowledge(
            db,
            project_id=source.project_id,
            key=candidate_key,
            value=f"可能的关联字段：{left['label']} ↔ {right['label']}",
            entry_type="relationship",
            confidence=item["score"],
            definition=item["definition"],
            validity="unverified",
            evidence=[
                {
                    "kind": "matching_column_names",
                    "source_ids": [left["source_id"], right["source_id"]],
                    "sources": [left["label"], right["label"]],
                    "candidate_group": {
                        "canonical_column": item["normalized"],
                        "endpoint_count": item["endpoint_count"],
                        "considered_endpoint_count": item["considered_endpoint_count"],
                        "possible_pair_count": item["possible_pair_count"],
                        "retained_pair_count": item["group_retained_count"],
                        "pair_rank": item["group_rank"],
                        "project_rank": project_rank,
                        "per_column_cap": _MAX_INFERRED_RELATIONSHIPS_PER_COLUMN,
                        "project_cap": _MAX_INFERRED_RELATIONSHIPS_PER_PROJECT,
                    },
                    "note": "实际使用前仍需检查匹配率和唯一性",
                }
            ],
        )
    await _retire_unretained_inferred_relationship_candidates(
        db,
        project_id=source.project_id,
        retained_keys=retained_inferred_keys,
    )


def _candidate_mentions_source(entry: SemanticEntry, source: ProjectDataSource) -> bool:
    source_id = str(source.id)
    if source_id in str(entry.key or ""):
        return True
    for item in entry.evidence or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("source_id") or "") == source_id:
            return True
        if source_id in {str(value) for value in item.get("source_ids") or []}:
            return True
        labels = item.get("sources") or []
        if isinstance(labels, list) and any(
            str(label).startswith(f"{source.name}.") for label in labels
        ):
            return True
    return False


async def _clear_inferred_candidates_for_source(
    db: AsyncSession,
    source: ProjectDataSource,
) -> None:
    result = await db.execute(
        select(SemanticEntry).where(
            SemanticEntry.project_id == source.project_id,
            SemanticEntry.state == "candidate",
        )
    )
    for entry in result.scalars():
        if _candidate_mentions_source(entry, source):
            entry.is_active = False
            entry.validity = "stale"
            reset_semantic_execution_proof(entry)
            entry.evidence = [
                *list(entry.evidence or []),
                {
                    "kind": "source_removed",
                    "source_id": str(source.id),
                },
            ]
            await append_semantic_revision(
                db,
                entry,
                mutation_kind="candidate_deactivated",
                actor_source="system",
                reason="移除数据来源后停用相关候选理解",
                expected_active_revision_id=entry.active_revision_id,
            )


async def apply_excel_sheet_selection_decision(
    db: AsyncSession,
    *,
    project_id: UUID,
    source_id: UUID,
    confirmation_key: str,
    selected_sheet: str,
) -> dict[str, Any]:
    """Rebuild one source from an explicitly chosen sheet without touching its trusted copy."""

    source = await _source_or_404(db, project_id, source_id)
    expected_key = excel_sheet_selection_key(source.id)
    if confirmation_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="工作表确认已变化，请重新预检后再选择",
        )
    source_path = Path(source.source_uri or "")
    if source.kind != "file" or source_path.suffix.casefold() not in {".xls", ".xlsx"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="这项工作表确认不属于可执行的 Excel 数据源",
        )
    profile = dict(source.profile_data or {})
    ambiguity = next(
        (
            item
            for item in profile.get("ambiguities") or []
            if str(item.get("key") or "") == confirmation_key
        ),
        None,
    )
    if ambiguity is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="工作表确认已被处理或发生变化，请刷新后重试",
        )
    options = [str(option) for option in ambiguity.get("options") or []]
    if selected_sheet not in options:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="选中的工作表不属于当前可用选项",
        )

    decision_dir = (
        settings.WORKSPACE_ROOT
        / str(project_id)
        / "sources"
        / str(source.id)
        / "working"
        / "decisions"
        / str(uuid4())
    )
    try:
        result = await _run_preflight_in_thread(
            source_path,
            decision_dir,
            recipe_operations=[{"operation": "select_sheet", "sheet": selected_sheet}],
        )
        actual_sheet = str((result.source_snapshot.get("reader") or {}).get("selected_sheet") or "")
        if actual_sheet != selected_sheet or result.working_path is None:
            raise ValueError("重新整理后的工作表与用户选择不一致")

        _scope_preflight_ambiguities(result.ambiguities, source.id)
        await _reuse_confirmed_preflight_answers(db, project_id, result)

        source.working_uri = str(result.working_path.resolve())
        source.fingerprint = result.input_fingerprint
        source.status = result.status
        source.profile_data = {
            **profile,
            "summary": result.summary,
            "schema": result.inferred_schema,
            "preanalysis": result.source_snapshot.get("preanalysis", {}),
            "sample": result.source_snapshot.get("sample", []),
            "issues": result.issues,
            "ambiguities": result.ambiguities,
        }

        report_result = await db.execute(
            select(PreflightReportRecord)
            .where(PreflightReportRecord.data_source_id == source.id)
            .order_by(PreflightReportRecord.created_at.desc())
        )
        reports = list(report_result.scalars())
        report = next(
            (
                item
                for item in reports
                if any(
                    str(question.get("key") or "") == confirmation_key
                    for question in item.ambiguities or []
                )
            ),
            reports[0] if reports else None,
        )
        if report is None:
            report = PreflightReportRecord(project_id=project_id, data_source_id=source.id)
            db.add(report)
        report.status = result.status
        report.summary = result.summary
        report.issues = result.issues
        report.ambiguities = result.ambiguities
        report.inferred_schema = result.inferred_schema
        report.source_snapshot = result.source_snapshot
        report.fingerprint = result.input_fingerprint

        recipe_result = await db.execute(
            select(SanitationRecipeRecord)
            .where(SanitationRecipeRecord.data_source_id == source.id)
            .order_by(SanitationRecipeRecord.created_at.desc())
        )
        recipe = recipe_result.scalars().first()
        if recipe is None:
            recipe = SanitationRecipeRecord(
                project_id=project_id,
                data_source_id=source.id,
                name=f"{source.name} 自动整理",
            )
            db.add(recipe)
        recipe_needs_attention = any(
            item.get("code") in {"recipe_replay_drift", "recipe_input_changed"}
            for item in result.issues
        )
        await _record_sanitation_result(
            db,
            recipe,
            result,
            operations=result.operations,
            state="candidate" if recipe_needs_attention else "confirmed",
            actor_source="user",
            reason=f"确认使用工作表“{selected_sheet}”并重新整理",
        )

        await _clear_inferred_candidates_for_source(db, source)
        if (source.profile_data or {}).get("is_current") is not False:
            await _persist_preflight_candidates(db, source)
        await db.flush()
        return {
            "cleanup_dir": str(decision_dir),
            "source_id": str(source.id),
            "selected_sheet": selected_sheet,
            "working_uri": source.working_uri,
            "recipe_id": str(recipe.id),
        }
    except HTTPException:
        shutil.rmtree(decision_dir, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(decision_dir, ignore_errors=True)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="无法安全应用所选工作表，原分析副本保持不变",
        ) from exc


async def _reuse_confirmed_preflight_answers(
    db: AsyncSession,
    project_id: UUID,
    preflight: Any,
) -> None:
    knowledge_result = await db.execute(
        select(SemanticEntry).where(
            SemanticEntry.project_id == project_id,
            SemanticEntry.state.in_(["confirmed", "locked"]),
            SemanticEntry.is_active.is_(True),
            SemanticEntry.validity == "active",
        )
    )
    confirmed_by_slot: dict[str, set[str]] = {}
    for item in knowledge_result.scalars():
        slot = canonicalize_decision_key(str(item.key))
        meaning = json.dumps(
            {"value": item.value, "definition": item.definition},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        confirmed_by_slot.setdefault(slot, set()).add(meaning)
    confirmed_keys = {
        slot for slot, meanings in confirmed_by_slot.items() if len(meanings) == 1
    }
    if not confirmed_keys:
        return
    original = list(preflight.ambiguities)
    preflight.ambiguities = [
        item
        for item in original
        if canonicalize_decision_key(
            str(item.get("key") or ""),
            question=str(item.get("question") or ""),
            reason=str(item.get("reason") or ""),
            options=[str(option) for option in item.get("options") or []],
        )
        not in confirmed_keys
    ]
    reused = len(original) - len(preflight.ambiguities)
    if reused:
        has_blocking_issue = any(
            item.get("code") in {"recipe_replay_drift", "recipe_input_changed"}
            for item in preflight.issues
        )
        preflight.status = (
            "needs_confirmation" if preflight.ambiguities or has_blocking_issue else "ready"
        )
        if not preflight.ambiguities:
            preflight.summary = re.sub(r"，有 \d+ 个业务口径需要确认", "", preflight.summary)
        preflight.issues.append(
            {
                "code": "confirmed_knowledge_reused",
                "title": f"已复用 {reused} 项确认过的业务口径",
                "detail": "这些口径来自当前项目，不会影响其他项目。",
                "severity": "info",
                "automatic": True,
                "count": reused,
            }
        )
        preflight.summary += "，已复用确认过的业务口径"


async def _matching_prior_source(
    db: AsyncSession,
    source: ProjectDataSource,
    new_schema: dict[str, Any],
) -> tuple[
    ProjectDataSource | None,
    set[str],
    set[str],
    list[dict[str, str]],
    str | None,
    float,
]:
    new_columns = _profile_columns({"schema": new_schema})
    result = await db.execute(
        select(ProjectDataSource)
        .where(
            ProjectDataSource.project_id == source.project_id,
            ProjectDataSource.kind == "file",
            ProjectDataSource.id != source.id,
            ProjectDataSource.status != "superseded",
        )
        .order_by(ProjectDataSource.updated_at.desc())
    )
    series_key = _source_series_key(source.name)
    same_series_match: ProjectDataSource | None = None
    schema_match: ProjectDataSource | None = None
    schema_match_score = 0.0
    for candidate in result.scalars():
        if (candidate.profile_data or {}).get("is_current") is False:
            continue
        candidate_columns = _profile_columns(candidate.profile_data or {})
        if not candidate_columns or not new_columns:
            continue
        score = len(candidate_columns & new_columns) / len(candidate_columns | new_columns)
        same_series = bool(series_key and _source_series_key(candidate.name) == series_key)
        if same_series and same_series_match is None:
            same_series_match = candidate
            continue
        if score < 0.85:
            continue
        if score > schema_match_score:
            schema_match, schema_match_score = candidate, score

    matched = same_series_match or schema_match
    if matched is None:
        return None, set(), set(), [], None, 0.0
    added, removed, type_changes, overlap_ratio = _schema_drift_details(
        matched.profile_data or {},
        new_schema,
    )
    return (
        matched,
        added,
        removed,
        type_changes,
        "source_series" if same_series_match is not None else "schema_overlap",
        overlap_ratio,
    )


def _suggestion_context(sources: list[ProjectDataSource]) -> dict[str, Any]:
    compact_sources: list[dict[str, Any]] = []
    for source in sources[:12]:
        profile = source.profile_data or {}
        preanalysis = profile.get("preanalysis") or {}
        roles = list(preanalysis.get("candidate_roles") or [])[:60]
        compact_sources.append(
            {
                "name": source.name,
                "kind": source.kind,
                "summary": profile.get("summary"),
                "shape": preanalysis.get("shape") or {},
                "candidate_roles": [
                    {
                        "column": role.get("column"),
                        "role": role.get("role"),
                        "missing": role.get("missing"),
                        "unique": role.get("unique"),
                        "range": role.get("range"),
                        "top_values": list(role.get("top_values") or [])[:5],
                    }
                    for role in roles
                ],
            }
        )
    return {"sources": compact_sources}


def _fallback_suggestions(context: dict[str, Any]) -> list[SuggestedQuestion]:
    sources = list(context.get("sources") or [])
    if not sources:
        return []
    source_names = "、".join(str(item.get("name") or "当前数据") for item in sources[:2])
    roles = [role for source in sources for role in list(source.get("candidate_roles") or [])]
    has_time = any(item.get("role") == "time" for item in roles)
    has_measure = any(item.get("role") == "measure" for item in roles)
    has_dimension = any(item.get("role") in {"dimension", "identifier"} for item in roles)
    items = [
        SuggestedQuestion(
            label="先找出最值得关注的问题",
            prompt=f"请自主分析 {source_names}，找出最值得我关注的异常、变化和可能原因。",
            reason="从当前数据整体开始，不预设固定图表或结论",
        )
    ]
    if has_time and has_measure:
        items.append(
            SuggestedQuestion(
                label="看看变化从哪里开始",
                prompt=f"分析 {source_names} 随时间发生的主要变化，指出转折点并调查可能原因。",
                reason="当前数据包含时间和数值信息",
            )
        )
    elif has_measure:
        items.append(
            SuggestedQuestion(
                label="核对异常值和业务影响",
                prompt=f"检查 {source_names} 中数值异常最明显的地方，说明它们是否会影响业务结论。",
                reason="当前数据包含可比较的数值信息",
            )
        )
    if has_dimension and has_measure:
        items.append(
            SuggestedQuestion(
                label="比较不同业务分组",
                prompt=f"比较 {source_names} 中不同业务分组的表现，找出差异最大和最值得跟进的部分。",
                reason="当前数据可以按业务维度比较",
            )
        )
    generic_fallbacks = [
        SuggestedQuestion(
            label="检查数据能回答什么",
            prompt=f"先检查 {source_names} 的数据质量和口径，再告诉我目前可以可靠回答哪些经营问题。",
            reason="先确认数据边界，避免把样例当成结论",
        ),
        SuggestedQuestion(
            label="找出可能影响判断的数据问题",
            prompt=f"检查 {source_names} 中会明显影响业务判断的缺失、重复或异常记录，并说明应该怎样处理。",
            reason="先排除会改变结论的数据风险",
        ),
        SuggestedQuestion(
            label="建议下一步调查方向",
            prompt=f"根据 {source_names} 当前能支持的分析范围，提出最值得优先调查的三个业务方向并说明理由。",
            reason="从真实数据范围决定下一步，不预设业务故事",
        ),
    ]
    for fallback in generic_fallbacks:
        if len(items) >= 3:
            break
        items.append(fallback)
    return items[:3]


def _merge_suggestions(
    generated: list[SuggestedQuestion] | None,
    fallback: list[SuggestedQuestion],
) -> list[SuggestedQuestion]:
    """Keep AI variety without allowing duplicate controls in the workbench."""

    merged: list[SuggestedQuestion] = []
    seen: set[str] = set()
    for suggestion in [*(generated or []), *fallback]:
        marker = re.sub(r"\s+", "", suggestion.prompt).casefold()
        if not marker or marker in seen:
            continue
        seen.add(marker)
        merged.append(suggestion)
        if len(merged) == 3:
            break
    return merged


async def _ai_suggestions(
    db: AsyncSession,
    payload: SuggestedQuestionsRequest,
    context: dict[str, Any],
) -> list[SuggestedQuestion] | None:
    settings_record = await get_or_create_app_settings(db)
    resolver = ExecutionContextResolver(
        db,
        model_name=str(payload.model_id) if payload.model_id else None,
        settings_data=settings_to_dict(settings_record),
    )
    model_config = await resolver.get_model_config()
    if model_config.get("api_key_required") and not model_config.get("api_key"):
        return None
    agent = Agent(
        build_pydantic_model(model_config),
        output_type=_SuggestedQuestionSet,
        instructions=(
            "你为普通运营、财务或销售人员生成三个可直接开始的数据调查问题。"
            "问题必须只基于给定的数据轮廓，不得假设不存在的业务。"
            "如果给出了已确认业务口径，建议必须遵守这些口径。"
            "使用业务语言，不暴露字段名、SQL、Python、schema 或语义层。"
            "三个方向要明显不同：整体诊断、变化或异常、分组或关系。"
            "不要强制指定热力图等图表，是否可视化交给后续分析决定。"
            "label 是简短入口，prompt 是可直接执行的完整任务，reason 说明为何适合当前数据。"
        ),
        retries={"output": 2},
    )
    try:
        result = await asyncio.wait_for(
            agent.run(json.dumps(context, ensure_ascii=False, default=str)),
            timeout=15,
        )
    except Exception as exc:
        logger.info("AI suggestions unavailable, using preflight fallback: %s", exc)
        return None
    return result.output.items


@router.get("", response_model=APIResponse[list[ProjectResponse]])
async def list_projects(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).order_by(Project.updated_at.desc()))
    return APIResponse.ok(data=[ProjectResponse.model_validate(item) for item in result.scalars()])


@router.post("", response_model=APIResponse[ProjectResponse])
async def create_project(payload: ProjectCreate, db: AsyncSession = Depends(get_db)):
    project = Project(name=payload.name, description=payload.description, status="active")
    db.add(project)
    await db.commit()
    await db.refresh(project)
    (settings.WORKSPACE_ROOT / str(project.id) / "sources").mkdir(parents=True, exist_ok=True)
    return APIResponse.ok(data=ProjectResponse.model_validate(project), message="项目已创建")


@router.get("/{project_id}", response_model=APIResponse[ProjectResponse])
async def get_project(project_id: UUID, db: AsyncSession = Depends(get_db)):
    return APIResponse.ok(
        data=ProjectResponse.model_validate(await _project_or_404(db, project_id))
    )


@router.patch("/{project_id}", response_model=APIResponse[ProjectResponse])
async def update_project(
    project_id: UUID,
    payload: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
):
    project = await _project_or_404(db, project_id)
    project.name = payload.name
    await db.commit()
    await db.refresh(project)
    return APIResponse.ok(
        data=ProjectResponse.model_validate(project),
        message="项目名称已更新",
    )


@router.post(
    "/{project_id}/suggested-questions",
    response_model=APIResponse[SuggestedQuestionsResponse],
)
async def suggested_questions(
    project_id: UUID,
    payload: SuggestedQuestionsRequest,
    db: AsyncSession = Depends(get_db),
):
    await _project_or_404(db, project_id)
    result = await db.execute(
        select(ProjectDataSource)
        .where(
            ProjectDataSource.project_id == project_id,
            ProjectDataSource.status.in_(["ready", "needs_confirmation"]),
        )
        .order_by(ProjectDataSource.updated_at.desc())
    )
    sources = [
        source
        for source in result.scalars()
        if (source.profile_data or {}).get("is_current", True) is not False
    ]
    context = _suggestion_context(sources)
    knowledge_result = await db.execute(
        select(SemanticEntry)
        .where(
            SemanticEntry.project_id == project_id,
            SemanticEntry.state.in_(["confirmed", "locked"]),
            SemanticEntry.validity != "stale",
            SemanticEntry.entry_type != "verified_query",
        )
        .order_by(SemanticEntry.updated_at.desc())
        .limit(20)
    )
    context["confirmed_business_context"] = [
        {"type": entry.entry_type, "value": entry.value} for entry in knowledge_result.scalars()
    ]
    signature = hashlib.sha256(
        json.dumps(context, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    fallback = _fallback_suggestions(context)
    if not fallback:
        return APIResponse.ok(
            data=SuggestedQuestionsResponse(
                items=[],
                generated_by="preflight",
                context_signature=signature,
            )
        )
    generated = await _ai_suggestions(db, payload, context)
    suggestions = _merge_suggestions(generated, fallback)
    return APIResponse.ok(
        data=SuggestedQuestionsResponse(
            items=suggestions,
            generated_by="ai" if generated else "preflight",
            context_signature=signature,
        )
    )


@router.get("/{project_id}/sources", response_model=APIResponse[list[DataSourceResponse]])
async def list_sources(project_id: UUID, db: AsyncSession = Depends(get_db)):
    await _project_or_404(db, project_id)
    result = await db.execute(
        select(ProjectDataSource)
        .where(
            ProjectDataSource.project_id == project_id,
            ProjectDataSource.status != "superseded",
        )
        .order_by(ProjectDataSource.created_at)
    )
    return APIResponse.ok(
        data=[DataSourceResponse.model_validate(item) for item in result.scalars()]
    )


@router.delete("/{project_id}/sources/{source_id}", response_model=APIResponse[dict[str, Any]])
async def remove_project_source(
    project_id: UUID,
    source_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Remove ReceiptBI's source copy/association without mutating external data."""

    source = await _source_or_404(db, project_id, source_id)
    profile = dict(source.profile_data or {})
    restored_source_id: UUID | None = None
    if profile.get("is_current") is not False:
        previous_id = profile.get("recipe_replayed_from")
        try:
            previous_source = (
                await db.get(ProjectDataSource, UUID(str(previous_id))) if previous_id else None
            )
        except ValueError:
            previous_source = None
        if (
            previous_source is not None
            and previous_source.project_id == project_id
            and previous_source.status == "superseded"
        ):
            previous_profile = dict(previous_source.profile_data or {})
            previous_profile["is_current"] = True
            previous_profile.pop("superseded_by", None)
            previous_source.profile_data = previous_profile
            previous_source.status = "ready" if previous_source.working_uri else "attached"
            restored_source_id = previous_source.id

    await _clear_inferred_candidates_for_source(db, source)
    await db.execute(
        delete(PreflightReportRecord).where(PreflightReportRecord.data_source_id == source.id)
    )
    await db.execute(
        delete(SanitationRecipeRecord).where(SanitationRecipeRecord.data_source_id == source.id)
    )
    await db.delete(source)
    await db.commit()

    source_dir = settings.WORKSPACE_ROOT / str(project_id) / "sources" / str(source_id)
    try:
        shutil.rmtree(source_dir, ignore_errors=False)
    except FileNotFoundError:
        pass
    except OSError as exc:
        logger.warning(
            "Source record removed but workspace cleanup failed for %s: %s", source_id, exc
        )

    return APIResponse.ok(
        data={
            "source_id": str(source_id),
            "removed": True,
            "restored_source_id": str(restored_source_id) if restored_source_id else None,
            "external_data_untouched": True,
        },
        message="来源已从项目移除；原始文件和数据库没有被修改",
    )


@router.post("/{project_id}/sources/files", response_model=APIResponse[DataSourceResponse])
async def upload_file_source(
    project_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    await _project_or_404(db, project_id)
    filename = _safe_filename(file.filename)
    suffix = Path(filename).suffix.lower().lstrip(".")
    if suffix not in SUPPORTED_FILE_FORMATS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"当前支持 CSV、Excel、Parquet 和 JSON，不支持 .{suffix or '未知'}",
        )

    source = ProjectDataSource(
        project_id=project_id,
        kind="file",
        name=filename,
        format=suffix,
        status="attached",
    )
    db.add(source)
    await db.flush()
    source_dir = settings.WORKSPACE_ROOT / str(project_id) / "sources" / str(source.id)
    source_dir.mkdir(parents=True, exist_ok=True)
    original_path = source_dir / filename
    with original_path.open("wb") as destination:
        shutil.copyfileobj(file.file, destination)
    source.source_uri = str(original_path.resolve())
    source.fingerprint = fingerprint_file(original_path)
    await db.commit()
    await db.refresh(source)
    return APIResponse.ok(data=DataSourceResponse.model_validate(source), message="文件已加入项目")


@router.post("/{project_id}/sources/connections", response_model=APIResponse[DataSourceResponse])
async def attach_connection_source(
    project_id: UUID,
    payload: ConnectionSourceCreate,
    db: AsyncSession = Depends(get_db),
):
    await _project_or_404(db, project_id)
    connection = await db.get(Connection, payload.connection_id)
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据库连接不存在")
    existing = await db.execute(
        select(ProjectDataSource).where(
            ProjectDataSource.project_id == project_id,
            ProjectDataSource.connection_id == connection.id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该数据库已加入项目")
    source_name = str(payload.name or connection.name).strip()
    if not source_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="数据源名称不能为空",
        )
    active_sources_result = await db.execute(
        select(ProjectDataSource).where(
            ProjectDataSource.project_id == project_id,
            ProjectDataSource.status != "superseded",
        )
    )
    requested_logical_name = source_name.casefold()
    for active_source in active_sources_result.scalars():
        active_names = {
            str(active_source.name).strip().casefold(),
            str((active_source.profile_data or {}).get("logical_name") or "")
            .strip()
            .casefold(),
        }
        active_names.discard("")
        if requested_logical_name in active_names:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="当前项目已有同名数据源，请换一个能区分它们的名称",
            )
    source = ProjectDataSource(
        project_id=project_id,
        connection_id=connection.id,
        kind="connection",
        name=source_name,
        format=connection.driver,
        status="attached",
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return APIResponse.ok(
        data=DataSourceResponse.model_validate(source), message="数据库已加入项目"
    )


async def _record_preflight_failure(
    db: AsyncSession,
    *,
    project_id: UUID,
    source_id: UUID,
) -> str:
    source = await _source_or_404(db, project_id, source_id)
    profile = dict(source.profile_data or {})
    trusted_copy_preserved = bool(
        source.working_uri
        and Path(source.working_uri).is_file()
        and profile.get("is_current") is not False
        and source.status in {"ready", "needs_confirmation"}
    )
    summary = (
        "本次重新整理没有成功，当前分析仍使用上一次成功副本"
        if trusted_copy_preserved
        else "这份数据暂时没有整理成功，可以重新整理或移除来源"
    )
    issue = {
        "code": "preflight_failed",
        "title": "本次重新整理没有成功",
        "detail": (
            "上一次成功副本保持不变，可以稍后重试。"
            if trusted_copy_preserved
            else "可以重新整理；原始文件和数据库没有被修改。"
        ),
        "severity": "critical",
        "automatic": False,
    }
    if trusted_copy_preserved:
        source.profile_data = {
            **profile,
            "last_preflight_failure": {
                "at": datetime.now(UTC).isoformat(),
                "summary": summary,
            },
        }
    else:
        existing_issues = [
            item
            for item in profile.get("issues") or []
            if item.get("code") != "preflight_failed"
        ]
        source.status = "error"
        source.profile_data = {
            **profile,
            "summary": summary,
            "issues": [*existing_issues, issue],
            "is_current": False,
            "activation_state": "failed",
        }
    db.add(
        PreflightReportRecord(
            project_id=project_id,
            data_source_id=source_id,
            status="error",
            summary=summary,
            issues=[issue],
            ambiguities=[],
            inferred_schema={},
            source_snapshot={
                "read_only": source.kind == "connection",
                "retryable": True,
                "trusted_copy_preserved": trusted_copy_preserved,
                "active_source_id": str(source.id) if trusted_copy_preserved else None,
            },
            fingerprint=source.fingerprint,
        )
    )
    await db.commit()
    return summary


@router.post(
    "/{project_id}/sources/{source_id}/preflight",
    response_model=APIResponse[PreflightReportResponse],
)
async def preflight_source(
    project_id: UUID,
    source_id: UUID,
    replay_recipe_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await _preflight_source_impl(
            project_id,
            source_id,
            replay_recipe_id=replay_recipe_id,
            db=db,
        )
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        failure_detail = await _record_preflight_failure(
            db,
            project_id=project_id,
            source_id=source_id,
        )
        logger.exception("Preflight failed for project %s source %s", project_id, source_id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=failure_detail,
        ) from exc


async def _preflight_source_impl(
    project_id: UUID,
    source_id: UUID,
    replay_recipe_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    source = await _source_or_404(db, project_id, source_id)
    if source.kind == "file":
        if not source.source_uri:
            raise HTTPException(status_code=400, detail="文件路径不可用")
        replay_recipe: SanitationRecipeRecord | None = None
        replay_revision: SanitationRecipeRevisionRecord | None = None
        if replay_recipe_id is not None:
            replay_recipe = await db.get(SanitationRecipeRecord, replay_recipe_id)
            if (
                replay_recipe is None
                or replay_recipe.project_id != project_id
                or replay_recipe.data_source_id != source.id
            ):
                raise HTTPException(status_code=404, detail="整理记录不存在")
            if source.status == "superseded":
                raise HTTPException(
                    status_code=409,
                    detail="历史版本不能直接重新整理，请在当前版本上继续",
                )
            replay_revision = await ensure_sanitation_revision_head(db, replay_recipe)
        # Never let an in-progress attempt overwrite the last trusted working copy.
        # The source pointer is switched only after the complete attempt is persisted.
        output_dir = (
            settings.WORKSPACE_ROOT
            / str(project_id)
            / "sources"
            / str(source.id)
            / "working"
            / "attempts"
            / str(uuid4())
        )
        result = await _run_preflight_in_thread(
            Path(source.source_uri),
            output_dir,
            recipe_operations=replay_revision.operations if replay_revision else None,
        )
        recipe_operations = list(result.operations)
        prior_source: ProjectDataSource | None = None
        prior_recipe: SanitationRecipeRecord | None = None
        added_columns: set[str] = set()
        removed_columns: set[str] = set()
        type_changes: list[dict[str, str]] = []
        prior_match_basis: str | None = None
        schema_overlap_ratio = 0.0

        if replay_recipe is not None:
            recipe_operations.insert(
                0,
                {
                    "operation": "reapply_recipe",
                    "recipe_id": str(replay_recipe.id),
                },
            )
            if (
                replay_recipe.input_fingerprint
                and replay_recipe.input_fingerprint != result.input_fingerprint
            ):
                result.issues.append(
                    {
                        "code": "recipe_input_changed",
                        "title": "原文件内容已发生变化",
                        "detail": "整理方法已经重新执行，但需要确认变化是否符合预期。",
                        "severity": "warning",
                        "automatic": False,
                    }
                )
                result.status = "needs_confirmation"
                result.summary += "，原文件变化需要确认"
        else:
            (
                prior_source,
                added_columns,
                removed_columns,
                type_changes,
                prior_match_basis,
                schema_overlap_ratio,
            ) = await _matching_prior_source(db, source, result.inferred_schema)

        if prior_source is not None:
            prior_recipe_result = await db.execute(
                select(SanitationRecipeRecord)
                .where(SanitationRecipeRecord.data_source_id == prior_source.id)
                .order_by(SanitationRecipeRecord.created_at.desc())
            )
            prior_recipe = prior_recipe_result.scalars().first()
            if prior_recipe is not None:
                prior_revision = await ensure_sanitation_revision_head(db, prior_recipe)
                result = await _run_preflight_in_thread(
                    Path(source.source_uri),
                    output_dir,
                    recipe_operations=prior_revision.operations,
                )
                (
                    added_columns,
                    removed_columns,
                    type_changes,
                    schema_overlap_ratio,
                ) = _schema_drift_details(
                    prior_source.profile_data or {},
                    result.inferred_schema,
                )
                recipe_operations = [
                    {
                        "operation": "replay_prior_recipe",
                        "source_id": str(prior_source.id),
                        "recipe_id": str(prior_recipe.id),
                    },
                    *result.operations,
                ]
            _record_schema_drift(
                result,
                matched_by=prior_match_basis,
                overlap_ratio=schema_overlap_ratio,
                added_columns=added_columns,
                removed_columns=removed_columns,
                type_changes=type_changes,
            )
        elif replay_recipe is None:
            project = await db.get(Project, project_id)
            imported_templates = _stored_recipe_templates(project) if project else []
            compatible_template = next(
                (
                    history
                    for history in imported_templates
                    if history.head.operations
                    and all(
                        not operation.get("column")
                        or operation.get("column")
                        in {
                            column.get("name")
                            for column in result.inferred_schema.get("columns", [])
                        }
                        for operation in history.head.operations
                    )
                ),
                None,
            )
            if compatible_template is not None:
                result.issues.append(
                    {
                        "code": "imported_recipe_candidate",
                        "title": "发现一套可参考的历史整理方法",
                        "detail": "它来自项目备份，尚未绑定到这份数据，因此不会自动执行。",
                        "severity": "info",
                        "automatic": False,
                    }
                )
                result.source_snapshot["recipe_template_candidate"] = {
                    "id": str(compatible_template.recipe_id),
                    "name": compatible_template.head.name,
                    "requires_explicit_binding": True,
                }

        _scope_preflight_ambiguities(result.ambiguities, source.id)
        await _reuse_confirmed_preflight_answers(db, project_id, result)
        existing_profile = dict(source.profile_data or {})
        pending_prior_source: ProjectDataSource | None = None
        replacement_of = existing_profile.get("replacement_of")
        if replacement_of:
            try:
                candidate = await db.get(ProjectDataSource, UUID(str(replacement_of)))
            except ValueError:
                candidate = None
            if (
                candidate is not None
                and candidate.project_id == project_id
                and candidate.id != source.id
            ):
                pending_prior_source = candidate

        if pending_prior_source is not None and replay_recipe is not None:
            (
                added_columns,
                removed_columns,
                type_changes,
                schema_overlap_ratio,
            ) = _schema_drift_details(
                pending_prior_source.profile_data or {},
                result.inferred_schema,
            )
            _record_schema_drift(
                result,
                matched_by="pending_replacement",
                overlap_ratio=schema_overlap_ratio,
                added_columns=added_columns,
                removed_columns=removed_columns,
                type_changes=type_changes,
            )

        blocking_recipe_drift = any(
            item.get("code") in {"recipe_replay_drift", "recipe_input_changed"}
            for item in result.issues
        )
        schema_requires_confirmation = bool(
            (result.source_snapshot.get("schema_drift") or {}).get("requires_confirmation")
        )
        replacement_requires_confirmation = prior_source is not None and (
            blocking_recipe_drift or schema_requires_confirmation
        )
        # Re-running a recipe is a deterministic retry, not user approval of a
        # previously blocked replacement. Only the explicit accept action may switch it.
        pending_replay_still_blocked = pending_prior_source is not None
        if pending_replay_still_blocked:
            result.status = "needs_confirmation"

        if replay_recipe is not None:
            logical_name = str(existing_profile.get("logical_name") or _view_name(source))
            version = int(existing_profile.get("version") or 1)
        else:
            logical_name = (
                str(
                    (prior_source.profile_data or {}).get("logical_name")
                    or _view_name(prior_source)
                )
                if prior_source is not None
                else _view_name(source)
            )
            version = (
                int((prior_source.profile_data or {}).get("version") or 1) + 1
                if prior_source is not None
                else 1
            )

        source_to_supersede: ProjectDataSource | None = None
        if prior_source is not None and not replacement_requires_confirmation:
            source_to_supersede = prior_source
        elif pending_prior_source is not None and not pending_replay_still_blocked:
            source_to_supersede = pending_prior_source
        if source_to_supersede is not None:
            prior_profile = dict(source_to_supersede.profile_data or {})
            prior_profile.update(
                {
                    "logical_name": logical_name,
                    "is_current": False,
                    "superseded_by": str(source.id),
                }
            )
            source_to_supersede.profile_data = prior_profile
            source_to_supersede.status = "superseded"

        if replacement_requires_confirmation or pending_replay_still_blocked:
            active_source = prior_source or pending_prior_source
            result.issues.append(
                {
                    "code": "replacement_pending",
                    "title": "新一期数据暂未替换当前版本",
                    "detail": "当前分析继续使用上一个已核对版本；重新整理确认无误后再切换。",
                    "severity": "warning",
                    "automatic": True,
                }
            )
            result.source_snapshot["replacement"] = {
                "status": "pending_confirmation",
                "replaces_source_id": str(active_source.id) if active_source else None,
                "active_source_id": str(active_source.id) if active_source else None,
            }
            result.summary += "，当前分析继续使用上一个已核对版本"
        elif pending_prior_source is not None:
            result.source_snapshot["replacement"] = {
                "status": "activated",
                "replaced_source_id": str(pending_prior_source.id),
                "active_source_id": str(source.id),
            }

        source.working_uri = str(result.working_path.resolve()) if result.working_path else None
        source.fingerprint = result.input_fingerprint
        source.status = result.status
        source_profile = {
            "summary": result.summary,
            "schema": result.inferred_schema,
            "preanalysis": result.source_snapshot.get("preanalysis", {}),
            "sample": result.source_snapshot.get("sample", []),
            "issues": result.issues,
            "ambiguities": result.ambiguities,
            "recipe_replayed_from": (
                str(prior_source.id)
                if prior_recipe
                else existing_profile.get("recipe_replayed_from")
            ),
            "logical_name": logical_name,
            "version": version,
            "is_current": not (replacement_requires_confirmation or pending_replay_still_blocked),
        }
        if replacement_requires_confirmation or pending_replay_still_blocked:
            active_source = prior_source or pending_prior_source
            source_profile.update(
                {
                    "replacement_of": str(active_source.id) if active_source else replacement_of,
                    "activation_state": "pending_confirmation",
                }
            )
        source.profile_data = source_profile
        if source_profile["is_current"]:
            await _persist_preflight_candidates(db, source)
        report = PreflightReportRecord(
            project_id=project_id,
            data_source_id=source.id,
            status=result.status,
            summary=result.summary,
            issues=result.issues,
            ambiguities=result.ambiguities,
            inferred_schema=result.inferred_schema,
            source_snapshot=result.source_snapshot,
            fingerprint=result.input_fingerprint,
        )
        if replay_recipe is not None:
            recipe_needs_attention = (
                blocking_recipe_drift
                or schema_requires_confirmation
                or pending_replay_still_blocked
            )
            await _record_sanitation_result(
                db,
                replay_recipe,
                result,
                operations=recipe_operations,
                state="candidate" if recipe_needs_attention else "confirmed",
                actor_source="system",
                reason=(
                    "重新执行整理方法，变化等待用户确认"
                    if recipe_needs_attention
                    else "重新执行并核对整理方法"
                ),
            )
            db.add(report)
        else:
            recipe_needs_attention = any(
                item.get("code") == "recipe_replay_drift" for item in result.issues
            ) or bool(
                (result.source_snapshot.get("schema_drift") or {}).get("requires_confirmation")
            )
            recipe = SanitationRecipeRecord(
                project_id=project_id,
                data_source_id=source.id,
                name=f"{source.name} 自动整理",
            )
            db.add_all([report, recipe])
            await _record_sanitation_result(
                db,
                recipe,
                result,
                operations=recipe_operations,
                state="candidate" if recipe_needs_attention else "confirmed",
                actor_source="system",
                reason=(
                    "首次整理完成，变化等待用户确认"
                    if recipe_needs_attention
                    else "首次自动整理并核对完成"
                ),
            )
    else:
        connection = await db.get(Connection, source.connection_id)
        if connection is None:
            raise HTTPException(status_code=404, detail="数据库连接已失效")
        password = (
            encryptor.decrypt(connection.password_encrypted)
            if connection.password_encrypted
            else ""
        )
        manager = create_database_manager(
            {
                "driver": connection.driver,
                "host": connection.host,
                "port": connection.port,
                "user": connection.username,
                "password": password,
                "database": connection.database_name,
                "extra_options": connection.extra_options or {},
            }
        )
        try:
            value_profile = await asyncio.to_thread(
                run_database_value_preflight,
                manager,
            )
            schema_catalog = value_profile.catalog
        except Exception:
            logger.exception(
                "Database preflight failed",
                extra={"project_id": str(project_id), "source_id": str(source.id)},
            )
            source.status = "error"
            source.profile_data = {
                "summary": "数据库暂时无法读取",
                "issues": [
                    {
                        "code": "database_preflight_failed",
                        "title": "数据库暂时无法读取",
                        "detail": "没有修改数据库；请检查连接后重试。",
                        "severity": "critical",
                        "automatic": False,
                    }
                ],
                "is_current": False,
            }
            report = PreflightReportRecord(
                project_id=project_id,
                data_source_id=source.id,
                status="error",
                summary="数据库暂时无法读取，没有修改数据库",
                issues=list(source.profile_data["issues"]),
                ambiguities=[],
                inferred_schema={},
                source_snapshot={"read_only": True, "profile_status": "error"},
            )
            db.add(report)
            await db.commit()
            await db.refresh(report)
            return APIResponse.ok(data=PreflightReportResponse.model_validate(report))
        schema_text = "\n".join(
            f"- {table['name']}: "
            + ", ".join(f"{column['name']} ({column['type']})" for column in table["columns"])
            for table in schema_catalog
        )
        source.status = "ready"
        source.profile_data = {
            "summary": value_profile.summary,
            "logical_name": str(
                (source.profile_data or {}).get("logical_name") or source.name
            ),
            "schema_text": schema_text,
            "tables": schema_catalog,
            "preanalysis": value_profile.preanalysis,
            "issues": value_profile.issues,
            "profile_status": value_profile.status,
            "is_current": True,
        }
        await _persist_preflight_candidates(db, source)
        report = PreflightReportRecord(
            project_id=project_id,
            data_source_id=source.id,
            status=("needs_confirmation" if value_profile.status == "error" else "ready"),
            summary=value_profile.summary,
            issues=value_profile.issues,
            ambiguities=[],
            inferred_schema={"text": schema_text, "tables": schema_catalog},
            source_snapshot={
                "read_only": True,
                "profile_status": value_profile.status,
                "preanalysis": value_profile.preanalysis,
            },
        )
        db.add(report)

    await db.commit()
    await db.refresh(report)
    return APIResponse.ok(data=PreflightReportResponse.model_validate(report))


@router.get("/{project_id}/preflight", response_model=APIResponse[list[PreflightReportResponse]])
async def list_preflight_reports(project_id: UUID, db: AsyncSession = Depends(get_db)):
    await _project_or_404(db, project_id)
    result = await db.execute(
        select(PreflightReportRecord)
        .where(PreflightReportRecord.project_id == project_id)
        .order_by(PreflightReportRecord.created_at.desc())
    )
    return APIResponse.ok(
        data=[PreflightReportResponse.model_validate(item) for item in result.scalars()]
    )


@router.post(
    "/{project_id}/sources/{source_id}/cleaning/preview",
    response_model=APIResponse[SourceCleaningPreviewResponse],
)
async def preview_source_cleaning(
    project_id: UUID,
    source_id: UUID,
    payload: SourceCleaningPreviewRequest,
    db: AsyncSession = Depends(get_db),
):
    await _project_or_404(db, project_id)
    source = await _source_or_404(db, project_id, source_id)
    if source.kind != "file" or not source.source_uri:
        raise HTTPException(status_code=409, detail="可视化整理目前只适用于项目文件")
    if source.status == "superseded":
        raise HTTPException(status_code=409, detail="历史数据版本不能直接修改")
    source_path = Path(source.source_uri)
    await asyncio.to_thread(_enforce_visual_cleaning_source_limits, source_path)

    try:
        _, current_revision, active_operations = await _active_cleaning_recipe_snapshot(
            db,
            project_id=project_id,
            source_id=source.id,
        )
        selected_operations = canonicalize_visual_sanitation_operations(payload.operations)
        previous_manual_operations = _stored_visual_cleaning_operations(
            source,
            current_revision.id if current_revision is not None else None,
        )
        effective_operations = _merge_visual_cleaning_operations(
            active_operations,
            selected_operations,
            previous_manual_operations,
        )
        current_working_path, current_working_fingerprint = _working_copy_proof(source)
    except SanitationContractError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    preview_dir = _cleaning_attempt_dir(
        project_id,
        source.id,
        purpose="previews",
    )
    try:
        before_result = None
        before_path = current_working_path
        if before_path is None:
            before_result = await _run_preflight_in_thread(
                source_path,
                preview_dir / "before",
                recipe_operations=active_operations,
            )
            if _template_replay_drift(before_result):
                raise HTTPException(
                    status_code=409,
                    detail="当前整理方法与文件已经不匹配，请先重新整理数据",
                )
            before_path = before_result.working_path

        result = await _run_preflight_in_thread(
            source_path,
            preview_dir / "after",
            recipe_operations=effective_operations,
        )
        if (
            before_result is not None
            and before_result.input_fingerprint != result.input_fingerprint
        ):
            raise HTTPException(status_code=409, detail="文件在预览期间发生变化，请重新预览")
        if _template_replay_drift(result):
            raise HTTPException(
                status_code=409,
                detail="所选操作与当前字段或数据格式不匹配，当前分析副本没有改变",
            )
        if (
            fingerprint_file(source_path) != result.input_fingerprint
            or _working_copy_proof(source)[1] != current_working_fingerprint
        ):
            raise HTTPException(status_code=409, detail="文件或当前分析副本发生变化，请重新预览")
        if before_path is None or result.working_path is None:
            raise HTTPException(status_code=409, detail="预览没有生成可比较的分析副本")

        comparison = compare_working_copies(before_path, result.working_path)
        materialized_operations = _materialized_cleaning_operations(
            active_operations,
            result.operations,
        )
        response = SourceCleaningPreviewResponse(
            source_id=source.id,
            operations_hash=_visual_cleaning_proof_hash(
                selected_operations,
                materialized_operations,
            ),
            source_fingerprint=result.input_fingerprint,
            preview_output_fingerprint=result.output_fingerprint,
            current_working_fingerprint=current_working_fingerprint,
            current_recipe_active_revision_id=(
                current_revision.id if current_revision is not None else None
            ),
            before=comparison["before"],
            after=comparison["after"],
            changes=comparison["changes"],
            can_apply=True,
        )
        return APIResponse.ok(data=response, message="已预览变化，当前分析数据没有改变")
    except HTTPException:
        raise
    except (SanitationContractError, ValueError) as exc:
        raise HTTPException(
            status_code=409,
            detail="所选操作无法安全预览，当前分析数据没有改变",
        ) from exc
    except Exception as exc:
        logger.exception(
            "Cleaning preview failed for project %s source %s",
            project_id,
            source.id,
        )
        raise HTTPException(
            status_code=409,
            detail="这次预览没有完成，当前分析数据没有改变",
        ) from exc
    finally:
        shutil.rmtree(preview_dir, ignore_errors=True)


@router.post(
    "/{project_id}/sources/{source_id}/cleaning/apply",
    response_model=APIResponse[SourceCleaningApplyResponse],
)
async def apply_source_cleaning(
    project_id: UUID,
    source_id: UUID,
    payload: SourceCleaningApplyRequest,
    db: AsyncSession = Depends(get_db),
):
    await _locked_project_or_404(db, project_id)
    source = await _source_or_404(db, project_id, source_id)
    if source.kind != "file" or not source.source_uri:
        raise HTTPException(status_code=409, detail="可视化整理目前只适用于项目文件")
    if source.status == "superseded":
        raise HTTPException(status_code=409, detail="历史数据版本不能直接修改")
    source_path = Path(source.source_uri)
    await asyncio.to_thread(_enforce_visual_cleaning_source_limits, source_path)

    try:
        recipe, current_revision, active_operations = await _active_cleaning_recipe_snapshot(
            db,
            project_id=project_id,
            source_id=source.id,
        )
        current_revision_id = current_revision.id if current_revision is not None else None
        if current_revision_id != payload.expected_current_recipe_active_revision_id:
            raise HTTPException(status_code=409, detail="当前整理方法已经变化，请重新预览")
        selected_operations = canonicalize_visual_sanitation_operations(payload.operations)
        previous_manual_operations = _stored_visual_cleaning_operations(
            source,
            current_revision.id if current_revision is not None else None,
        )
        effective_operations = _merge_visual_cleaning_operations(
            active_operations,
            selected_operations,
            previous_manual_operations,
        )
        _, current_working_fingerprint = _working_copy_proof(source)
        if current_working_fingerprint != payload.expected_current_working_fingerprint:
            raise HTTPException(status_code=409, detail="当前分析副本已经变化，请重新预览")
    except SanitationContractError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    attempt_dir = _cleaning_attempt_dir(
        project_id,
        source.id,
        purpose="attempts",
    )
    applied = False
    try:
        result = await _run_preflight_in_thread(
            source_path,
            attempt_dir,
            recipe_operations=effective_operations,
        )
        materialized_operations = _materialized_cleaning_operations(
            active_operations,
            result.operations,
        )
        if (
            result.input_fingerprint != payload.expected_source_fingerprint
            or result.output_fingerprint != payload.expected_preview_output_fingerprint
            or _visual_cleaning_proof_hash(
                selected_operations,
                materialized_operations,
            )
            != payload.expected_operations_hash
            or fingerprint_file(source_path) != result.input_fingerprint
            or _working_copy_proof(source)[1] != payload.expected_current_working_fingerprint
        ):
            raise HTTPException(
                status_code=409,
                detail="文件、整理方法或试运行结果已经变化，请重新预览",
            )
        if _template_replay_drift(result):
            raise HTTPException(
                status_code=409,
                detail="所选操作与当前字段或数据格式不匹配，尚未应用",
            )

        _scope_preflight_ambiguities(result.ambiguities, source.id)
        await _reuse_confirmed_preflight_answers(db, project_id, result)
        input_contract, output_contract = _sanitation_contracts(result)
        if recipe is None:
            recipe = SanitationRecipeRecord(
                project_id=project_id,
                data_source_id=source.id,
                name=f"{source.name} 整理方法",
                status="applied",
                operations=materialized_operations,
                input_fingerprint=result.input_fingerprint,
                output_fingerprint=result.output_fingerprint,
            )
            db.add(recipe)
            revision = await ensure_sanitation_revision_head(db, recipe)
            revision.state = "confirmed"
            revision.input_contract = input_contract
            revision.output_contract = output_contract
            revision.actor_source = "user"
            revision.reason = "查看变化后应用可视化整理"
        else:
            if current_revision is None:
                raise HTTPException(status_code=409, detail="当前整理方法已经变化，请重新预览")
            revision = await append_sanitation_revision(
                db,
                recipe,
                expected_active_revision_id=current_revision.id,
                state="confirmed",
                operations=materialized_operations,
                input_contract=input_contract,
                output_contract=output_contract,
                actor_source="user",
                reason="查看变化后应用可视化整理",
            )
            recipe.status = "applied"

        existing_profile = dict(source.profile_data or {})
        source.working_uri = str(result.working_path.resolve()) if result.working_path else None
        source.fingerprint = result.input_fingerprint
        source.status = result.status
        source.profile_data = {
            **existing_profile,
            "summary": result.summary,
            "schema": result.inferred_schema,
            "preanalysis": result.source_snapshot.get("preanalysis", {}),
            "sample": result.source_snapshot.get("sample", []),
            "issues": result.issues,
            "ambiguities": result.ambiguities,
            "is_current": existing_profile.get("is_current", True),
            "visual_cleaning": {
                "operations": selected_operations,
                "active_revision_id": str(revision.id),
            },
        }
        await _clear_inferred_candidates_for_source(db, source)
        if source.profile_data.get("is_current") is not False:
            await _persist_preflight_candidates(db, source)

        report = PreflightReportRecord(
            project_id=project_id,
            data_source_id=source.id,
            status=result.status,
            summary=result.summary,
            issues=result.issues,
            ambiguities=result.ambiguities,
            inferred_schema=result.inferred_schema,
            source_snapshot={
                **result.source_snapshot,
                "visual_cleaning": {
                    "operations_hash": payload.expected_operations_hash,
                    "parent_revision_id": (
                        str(current_revision.id) if current_revision is not None else None
                    ),
                },
            },
            fingerprint=result.input_fingerprint,
        )
        db.add(report)
        await db.flush()
        await db.commit()
        applied = True
        await db.refresh(recipe)
        await db.refresh(revision)
        await db.refresh(report)
        return APIResponse.ok(
            data=SourceCleaningApplyResponse(
                recipe=SanitationRecipeResponse.model_validate(recipe),
                revision=SanitationRecipeRevisionResponse.model_validate(revision),
                preflight=PreflightReportResponse.model_validate(report),
            ),
            message="整理已应用到当前分析副本，原文件没有改变",
        )
    except HTTPException:
        await db.rollback()
        raise
    except (SanitationContractError, SanitationRevisionConflictError, ValueError) as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="应用时数据或整理方法发生变化，请重新预览",
        ) from exc
    except Exception as exc:
        await db.rollback()
        logger.exception(
            "Cleaning apply failed for project %s source %s",
            project_id,
            source.id,
        )
        raise HTTPException(
            status_code=409,
            detail="这次应用没有完成，当前分析数据保持不变",
        ) from exc
    finally:
        if not applied:
            shutil.rmtree(attempt_dir, ignore_errors=True)


@router.get(
    "/{project_id}/recipe-templates",
    response_model=APIResponse[list[SanitationTemplateSummaryResponse]],
)
async def list_recipe_templates(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    project = await _project_or_404(db, project_id)
    histories = _stored_recipe_templates(project)
    if not histories:
        return APIResponse.ok(data=[])

    source_result = await db.execute(
        select(ProjectDataSource).where(
            ProjectDataSource.project_id == project_id,
            ProjectDataSource.kind == "file",
            ProjectDataSource.status != "superseded",
        )
    )
    sources = list(source_result.scalars())
    bindings = _stored_recipe_template_bindings(project)
    bound_pairs = {
        (item["template_recipe_id"], item["source_id"])
        for item in bindings
    }
    summaries = []
    for history in histories:
        compatible_source_ids = [
            source.id
            for source in sources
            if (str(history.recipe_id), str(source.id)) not in bound_pairs
        ]
        summaries.append(
            SanitationTemplateSummaryResponse(
                id=history.recipe_id,
                name=history.head.name,
                active_revision_id=history.head.active_revision_id,
                revision_count=len(history.revisions),
                compatible_source_ids=compatible_source_ids,
            )
        )
    return APIResponse.ok(data=summaries)


@router.post(
    "/{project_id}/recipe-templates/{template_id}/preview",
    response_model=APIResponse[SanitationTemplatePreviewResponse],
)
async def preview_recipe_template(
    project_id: UUID,
    template_id: UUID,
    payload: SanitationTemplatePreviewRequest,
    db: AsyncSession = Depends(get_db),
):
    project = await _project_or_404(db, project_id)
    history = _recipe_template_or_404(project, template_id)
    source = await _source_or_404(db, project_id, payload.source_id)
    if source.kind != "file" or not source.source_uri:
        raise HTTPException(status_code=409, detail="这套整理方法只能先用于项目里的文件")
    if source.status == "superseded":
        raise HTTPException(status_code=409, detail="历史数据版本不能绑定新的整理方法")
    if _template_already_bound(project, template_id, source.id):
        raise HTTPException(status_code=409, detail="这套方法已经用于这份数据")

    recipe = await _single_recipe_for_source(
        db,
        project_id=project_id,
        source_id=source.id,
    )
    current_working_fingerprint = None
    if source.working_uri and Path(source.working_uri).is_file():
        current_working_fingerprint = fingerprint_file(Path(source.working_uri))

    preview_dir = (
        settings.WORKSPACE_ROOT
        / str(project_id)
        / "sources"
        / str(source.id)
        / "working"
        / "previews"
        / str(uuid4())
    )
    try:
        result = await _run_preflight_in_thread(
            Path(source.source_uri),
            preview_dir,
            recipe_operations=history.head.operations,
        )
        _scope_preflight_ambiguities(result.ambiguities, source.id)
        await _reuse_confirmed_preflight_answers(db, project_id, result)
        response = _template_preview_payload(
            history=history,
            source=source,
            result=result,
            current_recipe_active_revision_id=(
                recipe.active_revision_id if recipe is not None else None
            ),
            current_working_fingerprint=current_working_fingerprint,
        )
        return APIResponse.ok(
            data=response,
            message="这里只是预览，当前分析数据没有改变",
        )
    except HTTPException:
        raise
    except (SanitationContractError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="这套整理方法与当前文件不兼容，当前分析数据没有改变",
        ) from exc
    except Exception as exc:
        logger.exception(
            "Template preview failed for project %s source %s template %s",
            project_id,
            source.id,
            template_id,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="试运行没有完成，当前分析数据没有改变",
        ) from exc
    finally:
        shutil.rmtree(preview_dir, ignore_errors=True)


@router.post(
    "/{project_id}/recipe-templates/{template_id}/bind",
    response_model=APIResponse[SanitationTemplateBindResponse],
)
async def bind_recipe_template(
    project_id: UUID,
    template_id: UUID,
    payload: SanitationTemplateBindRequest,
    db: AsyncSession = Depends(get_db),
):
    project = await _locked_project_or_404(db, project_id)
    history = _recipe_template_or_404(project, template_id)
    if history.head.active_revision_id != payload.expected_template_active_revision_id:
        raise HTTPException(status_code=409, detail="这套整理方法已经更新，请重新查看变化")
    if (
        _sanitation_operations_hash(history.head.operations)
        != payload.expected_template_operations_hash
    ):
        raise HTTPException(status_code=409, detail="这套整理方法已经更新，请重新查看变化")
    source = await _source_or_404(db, project_id, payload.source_id)
    if source.kind != "file" or not source.source_uri:
        raise HTTPException(status_code=409, detail="这套整理方法只能用于项目里的文件")
    if source.status == "superseded":
        raise HTTPException(status_code=409, detail="历史数据版本不能绑定新的整理方法")
    if _template_already_bound(project, template_id, source.id):
        raise HTTPException(status_code=409, detail="这套方法已经用于这份数据")

    recipe = await _single_recipe_for_source(
        db,
        project_id=project_id,
        source_id=source.id,
    )
    current_recipe_revision_id = recipe.active_revision_id if recipe is not None else None
    if current_recipe_revision_id != payload.expected_current_recipe_active_revision_id:
        raise HTTPException(status_code=409, detail="当前整理方法已经变化，请重新查看变化")

    current_working_fingerprint = None
    if source.working_uri and Path(source.working_uri).is_file():
        current_working_fingerprint = fingerprint_file(Path(source.working_uri))
    if current_working_fingerprint != payload.expected_current_working_fingerprint:
        raise HTTPException(status_code=409, detail="当前分析副本已经变化，请重新查看变化")

    attempt_dir = (
        settings.WORKSPACE_ROOT
        / str(project_id)
        / "sources"
        / str(source.id)
        / "working"
        / "attempts"
        / str(uuid4())
    )
    applied = False
    try:
        result = await _run_preflight_in_thread(
            Path(source.source_uri),
            attempt_dir,
            recipe_operations=history.head.operations,
        )
        if (
            result.input_fingerprint != payload.expected_source_fingerprint
            or result.output_fingerprint != payload.expected_preview_output_fingerprint
            or fingerprint_file(Path(source.source_uri)) != result.input_fingerprint
        ):
            raise HTTPException(
                status_code=409,
                detail="文件或试运行结果已经变化，请重新查看变化",
            )
        if _template_replay_drift(result):
            raise HTTPException(
                status_code=409,
                detail="这套整理方法与当前文件不完全匹配，尚未应用",
            )
        _scope_preflight_ambiguities(result.ambiguities, source.id)
        await _reuse_confirmed_preflight_answers(db, project_id, result)

        provenance_operations = canonicalize_sanitation_operations(
            [
                {
                    "operation": "replay_imported_recipe",
                    "template": f"{history.head.name} ({history.recipe_id})",
                },
                *result.operations,
            ]
        )
        input_contract, output_contract = _sanitation_contracts(result)
        if recipe is None:
            recipe = SanitationRecipeRecord(
                project_id=project_id,
                data_source_id=source.id,
                name=f"{source.name} 整理方法",
                status="applied",
                operations=provenance_operations,
                input_fingerprint=result.input_fingerprint,
                output_fingerprint=result.output_fingerprint,
            )
            db.add(recipe)
            revision = await ensure_sanitation_revision_head(db, recipe)
            revision.state = "confirmed"
            revision.input_contract = input_contract
            revision.output_contract = output_contract
            revision.actor_source = "imported"
            revision.reason = f"查看变化后应用“{history.head.name}”"
        else:
            active = await ensure_sanitation_revision_head(db, recipe)
            if (
                payload.expected_current_recipe_active_revision_id is not None
                and active.id != payload.expected_current_recipe_active_revision_id
            ):
                raise HTTPException(status_code=409, detail="当前整理方法已经变化，请重新查看变化")
            revision = await append_sanitation_revision(
                db,
                recipe,
                expected_active_revision_id=active.id,
                state="confirmed",
                operations=provenance_operations,
                input_contract=input_contract,
                output_contract=output_contract,
                actor_source="imported",
                reason=f"查看变化后应用“{history.head.name}”",
            )
            recipe.status = "applied"

        existing_profile = dict(source.profile_data or {})
        existing_profile.pop("visual_cleaning", None)
        source.working_uri = str(result.working_path.resolve()) if result.working_path else None
        source.fingerprint = result.input_fingerprint
        source.status = result.status
        source.profile_data = {
            **existing_profile,
            "summary": result.summary,
            "schema": result.inferred_schema,
            "preanalysis": result.source_snapshot.get("preanalysis", {}),
            "sample": result.source_snapshot.get("sample", []),
            "issues": result.issues,
            "ambiguities": result.ambiguities,
            "is_current": existing_profile.get("is_current", True),
        }
        await _clear_inferred_candidates_for_source(db, source)
        if source.profile_data.get("is_current") is not False:
            await _persist_preflight_candidates(db, source)

        report = PreflightReportRecord(
            project_id=project_id,
            data_source_id=source.id,
            status=result.status,
            summary=result.summary,
            issues=result.issues,
            ambiguities=result.ambiguities,
            inferred_schema=result.inferred_schema,
            source_snapshot={
                **result.source_snapshot,
                "imported_recipe_binding": {
                    "template_recipe_id": str(history.recipe_id),
                    "template_revision_id": str(history.head.active_revision_id),
                },
            },
            fingerprint=result.input_fingerprint,
        )
        db.add(report)
        await db.flush()

        extra_data = dict(project.extra_data or {})
        bindings = list(extra_data.get("recipe_template_bindings") or [])
        bindings.append(
            {
                "template_recipe_id": str(history.recipe_id),
                "template_revision_id": str(history.head.active_revision_id),
                "source_id": str(source.id),
                "recipe_id": str(recipe.id),
                "bound_revision_id": str(revision.id),
                "bound_at": datetime.now(UTC).isoformat(),
            }
        )
        extra_data["recipe_template_bindings"] = bindings
        project.extra_data = extra_data
        await db.commit()
        applied = True
        await db.refresh(recipe)
        await db.refresh(revision)
        await db.refresh(report)
        return APIResponse.ok(
            data=SanitationTemplateBindResponse(
                recipe=SanitationRecipeResponse.model_validate(recipe),
                revision=SanitationRecipeRevisionResponse.model_validate(revision),
                preflight=PreflightReportResponse.model_validate(report),
            ),
            message="这套整理方法已用于当前分析副本；原文件没有改变",
        )
    except HTTPException:
        await db.rollback()
        raise
    except (SanitationContractError, SanitationRevisionConflictError) as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="应用时数据或整理方法发生变化，请重新查看变化",
        ) from exc
    except Exception as exc:
        await db.rollback()
        logger.exception(
            "Template bind failed for project %s source %s template %s",
            project_id,
            source.id,
            template_id,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="这次应用没有完成，当前分析数据保持不变",
        ) from exc
    finally:
        if not applied:
            shutil.rmtree(attempt_dir, ignore_errors=True)


@router.get("/{project_id}/recipes", response_model=APIResponse[list[SanitationRecipeResponse]])
async def list_recipes(project_id: UUID, db: AsyncSession = Depends(get_db)):
    await _project_or_404(db, project_id)
    result = await db.execute(
        select(SanitationRecipeRecord)
        .where(SanitationRecipeRecord.project_id == project_id)
        .order_by(SanitationRecipeRecord.created_at.desc())
    )
    return APIResponse.ok(
        data=[SanitationRecipeResponse.model_validate(item) for item in result.scalars()]
    )


@router.get(
    "/{project_id}/recipes/{recipe_id}/revisions",
    response_model=APIResponse[list[SanitationRecipeRevisionResponse]],
)
async def list_recipe_revisions(
    project_id: UUID,
    recipe_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    recipe = await db.get(SanitationRecipeRecord, recipe_id)
    if recipe is None or recipe.project_id != project_id:
        raise HTTPException(status_code=404, detail="整理记录不存在")
    try:
        await ensure_sanitation_revision_head(db, recipe)
    except SanitationRevisionIntegrityError as exc:
        raise HTTPException(status_code=409, detail="整理方法的版本记录不完整") from exc
    await db.commit()
    revisions_result = await db.execute(
        select(SanitationRecipeRevisionRecord)
        .where(SanitationRecipeRevisionRecord.recipe_id == recipe.id)
        .order_by(SanitationRecipeRevisionRecord.revision_number.desc())
    )
    return APIResponse.ok(
        data=[
            SanitationRecipeRevisionResponse.model_validate(item)
            for item in revisions_result.scalars()
        ]
    )


@router.post(
    "/{project_id}/recipes/{recipe_id}/revisions/{revision_id}/restore",
    response_model=APIResponse[SanitationRecipeRevisionResponse],
)
async def restore_recipe_revision(
    project_id: UUID,
    recipe_id: UUID,
    revision_id: UUID,
    payload: SanitationRecipeRevisionRestoreRequest,
    db: AsyncSession = Depends(get_db),
):
    recipe = await db.get(SanitationRecipeRecord, recipe_id)
    if recipe is None or recipe.project_id != project_id:
        raise HTTPException(status_code=404, detail="整理记录不存在")
    target = await sanitation_revision_or_none(
        db,
        recipe_id=recipe.id,
        revision_id=revision_id,
    )
    if target is None:
        raise HTTPException(status_code=404, detail="整理方法的这个历史版本不存在")
    try:
        canonicalize_sanitation_operations(target.operations)
        restored = await restore_sanitation_revision(
            db,
            recipe,
            target,
            expected_active_revision_id=payload.expected_active_revision_id,
            reason=payload.reason,
            actor_source="user",
        )
    except SanitationRevisionConflictError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (SanitationRevisionIntegrityError, SanitationContractError) as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="这个整理版本无法安全恢复") from exc
    recipe.status = "reverted"
    source = await db.get(ProjectDataSource, recipe.data_source_id)
    if source is not None:
        _clear_visual_cleaning_metadata(source)
    await db.commit()
    await db.refresh(restored)
    return APIResponse.ok(
        data=SanitationRecipeRevisionResponse.model_validate(restored),
        message="已恢复旧的整理方法；重新整理后才会用于当前分析，原文件不会改变",
    )


@router.post(
    "/{project_id}/recipes/{recipe_id}/undo",
    response_model=APIResponse[SanitationRecipeResponse],
)
async def undo_recipe(
    project_id: UUID,
    recipe_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    recipe = await db.get(SanitationRecipeRecord, recipe_id)
    if recipe is None or recipe.project_id != project_id:
        raise HTTPException(status_code=404, detail="整理记录不存在")
    source = await _source_or_404(db, project_id, recipe.data_source_id)
    if source.status == "superseded":
        raise HTTPException(status_code=409, detail="历史版本不能直接撤销，请在当前版本上操作")

    profile = dict(source.profile_data or {})
    previous_id = profile.get("replacement_of") or profile.get("recipe_replayed_from")
    previous_source: ProjectDataSource | None = None
    if previous_id:
        try:
            previous_source = await db.get(ProjectDataSource, UUID(str(previous_id)))
        except ValueError:
            previous_source = None
        if (
            previous_source is None
            or previous_source.project_id != project_id
            or previous_source.id == source.id
            or not previous_source.working_uri
            or not Path(previous_source.working_uri).is_file()
        ):
            raise HTTPException(
                status_code=409,
                detail="找不到可恢复的上一成功版本，本次整理没有被撤销",
            )

        previous_profile = dict(previous_source.profile_data or {})
        previous_profile.update({"is_current": True})
        previous_profile.pop("superseded_by", None)
        previous_profile.pop("activation_state", None)
        previous_source.profile_data = previous_profile
        previous_source.status = (
            "needs_confirmation" if previous_profile.get("ambiguities") else "ready"
        )

    reverted_issue = {
        "code": "sanitation_reverted",
        "title": "已撤销本次整理",
        "detail": (
            "当前分析已恢复使用上一个成功版本。"
            if previous_source is not None
            else "当前没有可用于分析的整理副本。"
        ),
        "severity": "info",
        "automatic": False,
    }
    profile.update(
        {
            "is_current": False,
            "activation_state": "reverted",
            "summary": reverted_issue["detail"],
            "issues": [
                *[
                    item
                    for item in profile.get("issues") or []
                    if item.get("code") != "sanitation_reverted"
                ],
                reverted_issue,
            ],
        }
    )
    if previous_source is not None:
        profile["replacement_of"] = str(previous_source.id)
    profile.pop("visual_cleaning", None)
    source.profile_data = profile
    source.working_uri = None
    source.status = "attached"
    active_recipe_revision = await ensure_sanitation_revision_head(db, recipe)
    reverted_recipe_revision = await append_sanitation_revision(
        db,
        recipe,
        expected_active_revision_id=active_recipe_revision.id,
        state="reverted",
        operations=canonicalize_sanitation_operations(active_recipe_revision.operations),
        input_contract=active_recipe_revision.input_contract,
        output_contract=active_recipe_revision.output_contract,
        actor_source="user",
        reason="撤销这次整理并恢复上一个可信数据版本",
    )
    recipe.active_revision_id = reverted_recipe_revision.id
    recipe.status = "reverted"
    await db.commit()
    await db.refresh(recipe)
    return APIResponse.ok(
        data=SanitationRecipeResponse.model_validate(recipe),
        message=(
            "已撤销本次整理，当前分析已恢复上一个成功版本；原文件未受影响"
            if previous_source is not None
            else "已撤销整理，当前没有分析副本；原文件未受影响"
        ),
    )


@router.post(
    "/{project_id}/recipes/{recipe_id}/reapply",
    response_model=APIResponse[PreflightReportResponse],
)
async def reapply_recipe(
    project_id: UUID,
    recipe_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    recipe = await db.get(SanitationRecipeRecord, recipe_id)
    if recipe is None or recipe.project_id != project_id:
        raise HTTPException(status_code=404, detail="整理记录不存在")
    return await preflight_source(
        project_id,
        recipe.data_source_id,
        replay_recipe_id=recipe.id,
        db=db,
    )


@router.post(
    "/{project_id}/sources/{source_id}/accept-replacement",
    response_model=APIResponse[DataSourceResponse],
)
async def accept_source_replacement(
    project_id: UUID,
    source_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Explicitly activate one drifted replacement after the user has reviewed it."""

    source = await _source_or_404(db, project_id, source_id)
    profile = dict(source.profile_data or {})
    if profile.get("activation_state") != "pending_confirmation" or not profile.get(
        "replacement_of"
    ):
        raise HTTPException(status_code=409, detail="这份数据当前没有等待确认的版本切换")
    if not source.working_uri or not Path(source.working_uri).is_file():
        raise HTTPException(status_code=409, detail="待确认的分析副本不存在，请先重新整理")

    try:
        previous_source = await db.get(
            ProjectDataSource,
            UUID(str(profile["replacement_of"])),
        )
    except ValueError:
        previous_source = None
    if (
        previous_source is None
        or previous_source.project_id != project_id
        or previous_source.id == source.id
        or previous_source.status == "superseded"
        or (previous_source.profile_data or {}).get("is_current") is False
        or not previous_source.working_uri
        or not Path(previous_source.working_uri).is_file()
    ):
        raise HTTPException(
            status_code=409,
            detail="上一个成功版本已经变化，请重新整理后再确认",
        )

    recipe_result = await db.execute(
        select(SanitationRecipeRecord)
        .where(SanitationRecipeRecord.data_source_id == source.id)
        .order_by(SanitationRecipeRecord.created_at.desc())
    )
    recipe = recipe_result.scalars().first()
    if recipe is None:
        raise HTTPException(status_code=409, detail="没有可确认的整理记录")

    accepted_at = datetime.now(UTC).isoformat()
    accepted_changes = [
        item
        for item in profile.get("issues") or []
        if item.get("code")
        in {"schema_drift", "recipe_replay_drift", "recipe_input_changed"}
    ]
    acceptance_issue = {
        "code": "replacement_accepted",
        "title": "已确认启用这版数据",
        "detail": "结构或内容变化已由你明确确认；上一个成功版本保留为历史。",
        "severity": "info",
        "automatic": False,
    }
    runtime_issues = [
        item
        for item in profile.get("issues") or []
        if item.get("code")
        not in {
            "replacement_pending",
            "recipe_replay_drift",
            "recipe_input_changed",
            "replacement_accepted",
        }
    ]
    profile.update(
        {
            "is_current": True,
            "summary": "这版数据已由你确认启用",
            "issues": [*runtime_issues, acceptance_issue],
            "accepted_replacement": {
                "at": accepted_at,
                "previous_source_id": str(previous_source.id),
                "accepted_changes": accepted_changes,
            },
        }
    )
    profile.pop("replacement_of", None)
    profile.pop("activation_state", None)
    profile.pop("visual_cleaning", None)
    source.profile_data = profile
    source.status = "needs_confirmation" if profile.get("ambiguities") else "ready"

    previous_profile = dict(previous_source.profile_data or {})
    previous_profile.update(
        {
            "is_current": False,
            "superseded_by": str(source.id),
        }
    )
    previous_source.profile_data = previous_profile
    previous_source.status = "superseded"
    active_recipe_revision = await ensure_sanitation_revision_head(db, recipe)
    confirmed_recipe_revision = await append_sanitation_revision(
        db,
        recipe,
        expected_active_revision_id=active_recipe_revision.id,
        state="confirmed",
        operations=canonicalize_sanitation_operations(active_recipe_revision.operations),
        input_contract=active_recipe_revision.input_contract,
        output_contract=active_recipe_revision.output_contract,
        actor_source="user",
        reason="明确确认启用结构或内容已变化的数据版本",
    )
    recipe.active_revision_id = confirmed_recipe_revision.id
    recipe.status = "applied"

    report_result = await db.execute(
        select(PreflightReportRecord)
        .where(PreflightReportRecord.data_source_id == source.id)
        .order_by(PreflightReportRecord.created_at.desc())
    )
    report = report_result.scalars().first()
    if report is not None:
        report.status = source.status
        report.summary = "这版数据已由你确认启用；上一个成功版本保留为历史"
        report.issues = [
            *[item for item in report.issues or [] if item.get("code") != "replacement_accepted"],
            acceptance_issue,
        ]
        report_snapshot = dict(report.source_snapshot or {})
        report_snapshot["replacement"] = {
            "status": "accepted",
            "replaced_source_id": str(previous_source.id),
            "active_source_id": str(source.id),
            "accepted_at": accepted_at,
        }
        report.source_snapshot = report_snapshot

    await _persist_preflight_candidates(db, source)
    await db.commit()
    await db.refresh(source)
    return APIResponse.ok(
        data=DataSourceResponse.model_validate(source),
        message="已确认启用这版数据；上一个成功版本已保留为历史",
    )


def _semantic_entry_order_by() -> tuple[Any, ...]:
    return (
        case(
            (SemanticEntry.state == "candidate", 0),
            (SemanticEntry.state == "confirmed", 1),
            (SemanticEntry.state == "locked", 2),
            else_=9,
        ),
        case(
            (SemanticEntry.entry_type == "relationship", 0),
            (SemanticEntry.entry_type == "metric", 1),
            (SemanticEntry.entry_type == "dimension", 2),
            (SemanticEntry.entry_type == "business_rule", 3),
            (SemanticEntry.entry_type == "cleaning_rule", 4),
            (SemanticEntry.entry_type == "verified_query", 5),
            else_=9,
        ),
        func.lower(SemanticEntry.key),
        SemanticEntry.id,
    )


def _business_facing_semantic_entry_condition() -> Any:
    trimmed_value = func.ltrim(SemanticEntry.value, " \t\n\r\f\v")
    return (SemanticEntry.entry_type != "verified_query") & ~(
        (SemanticEntry.entry_type == "cleaning_rule")
        & or_(trimmed_value.like("{%"), trimmed_value.like("[%"))
    )


def _semantic_entry_matches_page_scope(
    entry: SemanticEntry,
    *,
    search: str | None,
    source_id: str | None,
    left_table: str | None,
    right_table: str | None,
) -> bool:
    definition = entry.definition if isinstance(entry.definition, dict) else {}
    left = definition.get("left") if isinstance(definition.get("left"), dict) else {}
    right = definition.get("right") if isinstance(definition.get("right"), dict) else {}
    if left_table and str(left.get("table_or_view") or "").casefold() != left_table.casefold():
        return False
    if right_table and str(right.get("table_or_view") or "").casefold() != right_table.casefold():
        return False
    if source_id:
        evidence_source_ids: set[str] = set()
        for item in entry.evidence or []:
            if not isinstance(item, dict):
                continue
            if item.get("source_id"):
                evidence_source_ids.add(str(item["source_id"]))
            evidence_source_ids.update(str(value) for value in item.get("source_ids") or [])
        if source_id not in evidence_source_ids:
            return False
    if search:
        needle = search.casefold()
        searchable = "\n".join(
            [
                entry.key,
                entry.value,
                entry.entry_type,
                entry.state,
                entry.validity,
                json.dumps(entry.definition, ensure_ascii=False, sort_keys=True),
                json.dumps(entry.evidence, ensure_ascii=False, sort_keys=True),
            ]
        ).casefold()
        if needle not in searchable:
            return False
    return True


async def _remember_candidate_rejection(
    db: AsyncSession,
    entry: SemanticEntry,
) -> str | None:
    """Return why this head cannot safely become governed knowledge."""

    if entry.execution_state != "verified" or not entry.definition:
        return "候选尚未通过真实执行验证"
    if entry.validity != "active":
        return "候选当前不是有效且已验证的定义"
    if entry.active_revision_id is None:
        return "候选缺少可绑定的当前版本"
    revision = await db.get(SemanticEntryRevision, entry.active_revision_id)
    if (
        revision is None
        or revision.project_id != entry.project_id
        or revision.semantic_entry_id != entry.id
        or revision.snapshot != semantic_entry_snapshot(entry)
    ):
        return "候选当前版本与验证证据不一致"

    details = entry.execution_details if isinstance(entry.execution_details, dict) else {}
    definition_hash = stable_payload_hash(entry.definition)
    value_hash = stable_payload_hash(entry.value)
    if (
        details.get("status") != "verified"
        or details.get("definition_hash") != definition_hash
        or not details.get("last_verified_run_id")
        or (details.get("value_hash") and details.get("value_hash") != value_hash)
    ):
        return "候选验证摘要不属于当前定义或当前值"

    verified_run_id = str(details["last_verified_run_id"])
    matching_proof = False
    for item in entry.evidence or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("definition_hash") or "") != definition_hash:
            continue
        if str(item.get("analysis_run_id") or "") != verified_run_id:
            continue
        kind = str(item.get("kind") or "")
        if kind == "deterministic_aggregate_metric_observation":
            matching_proof = bool(item.get("result_hash"))
            if matching_proof:
                break
        if kind in {"semantic_execution_verification", "correction_application", "semantic_human_attestation"}:
            if item.get("status") not in {None, "verified"}:
                continue
            if item.get("semantic_entry_id") and str(item["semantic_entry_id"]) != str(
                entry.id
            ):
                continue
            if item.get("rule_value") and str(item["rule_value"]) != entry.value:
                continue
            matching_proof = True
            break
        if kind in {"relationship_validation", "relationship_application"}:
            if str(item.get("semantic_entry_id") or "") != str(entry.id):
                continue
            if not item.get("result_hash") and not item.get("profile"):
                continue
            matching_proof = True
            break
    if not matching_proof:
        return "候选缺少与当前版本匹配的系统验证证据"
    return None


async def _restore_candidate_target(
    db: AsyncSession,
    entry: SemanticEntry,
) -> SemanticEntryRevision | None:
    if entry.active_revision_id is None or entry.is_active or entry.state != "candidate":
        return None
    current = await db.get(SemanticEntryRevision, entry.active_revision_id)
    if (
        current is None
        or current.project_id != entry.project_id
        or current.semantic_entry_id != entry.id
        or current.mutation_kind != "candidate_ignored"
        or current.parent_revision_id is None
        or current.snapshot != semantic_entry_snapshot(entry)
    ):
        return None
    target = await db.get(SemanticEntryRevision, current.parent_revision_id)
    if (
        target is None
        or target.project_id != entry.project_id
        or target.semantic_entry_id != entry.id
        or target.snapshot.get("state") != "candidate"
        or target.snapshot.get("is_active") is False
    ):
        return None
    return target


_NUMERIC_TYPE_HINTS = (
    "int",
    "float",
    "double",
    "decimal",
    "numeric",
    "real",
    "number",
)


def _probe_quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _probe_coerce(value: Any) -> Any:
    if isinstance(value, (int, str, bool)) or value is None:
        return value
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, (datetime,)):
        return value.isoformat()
    try:
        return float(value)
    except (TypeError, ValueError):
        return str(value)


def _run_file_probe(working_uri: str, select_sql: str) -> dict[str, Any]:
    import duckdb

    escaped_path = working_uri.replace("'", "''")
    relation = duckdb.sql(f"SELECT {select_sql} FROM read_parquet('{escaped_path}')")
    row = relation.fetchone()
    if row is None:
        return {}
    return {
        column[0]: _probe_coerce(value)
        for column, value in zip(relation.description, row)
    }


async def _probe_column_candidate(
    db: AsyncSession,
    *,
    project_id: UUID,
    entry: SemanticEntry,
) -> None:
    """Verify a metric/dimension candidate with a deterministic probe query.

    Relationship candidates earn verification through analyst-run joins. Column
    candidates (``metric_candidate:<source>:<column>`` / ``grain:<source>``) get
    the same real-execution bar via a direct aggregate probe against their bound
    source, then record the exact evidence shape ``remember`` already trusts.
    """
    key_parts = entry.key.split(":", 2)
    source_id: str
    column = ""
    table: str | None = None
    if (
        entry.entry_type == "metric"
        and len(key_parts) == 3
        and key_parts[0] == "metric_candidate"
    ):
        source_id, column = key_parts[1], key_parts[2]
    elif entry.entry_type == "dimension" and key_parts[0] == "grain" and len(key_parts) == 2:
        source_id = key_parts[1]
    else:
        raise HTTPException(
            status_code=409,
            detail=f"{entry.key} 缺少可探测的字段绑定，暂时无法系统验证",
        )

    try:
        source_uuid = UUID(source_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"{entry.key} 的来源标识无效，无法系统验证",
        ) from exc
    source = await db.get(ProjectDataSource, source_uuid)
    if (
        source is None
        or source.project_id != project_id
        or source.status == "superseded"
    ):
        raise HTTPException(
            status_code=409,
            detail="候选绑定的数据源已失效，无法系统验证",
        )
    profile = source.profile_data or {}

    if entry.entry_type == "dimension":
        grain = sorted(
            (
                profile.get("schema", {}).get("candidate_grain", [])
                or profile.get("preanalysis", {}).get("candidate_grain", [])
            ),
            key=lambda item: (
                int(item.get("evidence_priority", 9)),
                -float(item.get("uniqueness", 0)),
            ),
        )
        if not grain:
            raise HTTPException(
                status_code=409,
                detail="预检中没有可探测的粒度字段，无法系统验证",
            )
        column = str(grain[0].get("column") or "")
        table = str(grain[0].get("table") or "") or None

    column_details = [
        item
        for item in _profile_column_details(profile)
        if str(item.get("name") or "") == column
    ]
    if not column or not column_details:
        raise HTTPException(
            status_code=409,
            detail=f"当前数据里找不到字段“{column}”，无法系统验证",
        )
    declared_type = str(
        column_details[0].get("type") or column_details[0].get("dtype") or ""
    ).lower()
    is_numeric = any(hint in declared_type for hint in _NUMERIC_TYPE_HINTS)

    if source.kind == "connection":
        if table is None:
            table = str(column_details[0].get("table") or "") or None
        if table is None:
            raise HTTPException(
                status_code=409,
                detail=f"无法确定字段“{column}”所属的数据表，无法系统验证",
            )

    quoted_column = _probe_quote(column)
    select_parts = [
        "COUNT(*) AS total_rows",
        f"COUNT({quoted_column}) AS non_null_rows",
        f"COUNT(DISTINCT {quoted_column}) AS distinct_values",
    ]
    if entry.entry_type == "metric":
        select_parts.append(f"MIN({quoted_column}) AS min_value")
        select_parts.append(f"MAX({quoted_column}) AS max_value")
        if is_numeric:
            select_parts.append(f"AVG({quoted_column}) AS avg_value")
    select_sql = ", ".join(select_parts)

    if source.kind == "file":
        if not source.working_uri or not Path(source.working_uri).is_file():
            raise HTTPException(
                status_code=409,
                detail="可信数据副本不可用，无法系统验证",
            )
        stats = await asyncio.to_thread(
            _run_file_probe, source.working_uri, select_sql
        )
    else:
        connection = await db.get(Connection, source.connection_id)
        if connection is None:
            raise HTTPException(
                status_code=409,
                detail="数据库连接已失效，无法系统验证",
            )
        password = (
            encryptor.decrypt(connection.password_encrypted)
            if connection.password_encrypted
            else ""
        )
        manager = create_database_manager(
            {
                "driver": connection.driver,
                "host": connection.host,
                "port": connection.port,
                "user": connection.username,
                "password": password,
                "database": connection.database_name,
                "extra_options": connection.extra_options or {},
            }
        )
        sql = f"SELECT {select_sql} FROM {_probe_quote(str(table))}"
        try:
            result = await asyncio.to_thread(
                manager.execute_query, sql, True, 10
            )
        except Exception as exc:
            raise HTTPException(
                status_code=409,
                detail=f"探测查询没有执行成功：{exc}",
            ) from exc
        stats = {
            key: _probe_coerce(value)
            for key, value in (result.data[0] if result.data else {}).items()
        }

    total_rows = int(stats.get("total_rows") or 0)
    non_null_rows = int(stats.get("non_null_rows") or 0)
    distinct_values = int(stats.get("distinct_values") or 0)
    if total_rows <= 0:
        raise HTTPException(
            status_code=409,
            detail="探测到的数据为空，无法系统验证",
        )

    if entry.entry_type == "metric":
        summary = (
            f"系统探测：{column} 共 {total_rows} 行、非空 {non_null_rows} 行、"
            f"去重 {distinct_values} 个取值"
        )
        if "min_value" in stats:
            summary += f"，范围 {stats['min_value']} ~ {stats['max_value']}"
        if "avg_value" in stats:
            summary += f"，均值 {stats['avg_value']}"
    else:
        uniqueness = distinct_values / total_rows if total_rows else 0
        summary = (
            f"系统探测：{column} 唯一率 {uniqueness:.1%}"
            f"（{distinct_values}/{total_rows}）"
        )

    definition = {
        "version": 1,
        "kind": "column_metric" if entry.entry_type == "metric" else "grain_key",
        "source_id": str(source.id),
        "table": table,
        "column": column,
    }
    definition_hash = stable_payload_hash(definition)
    probe_run_id = uuid4()
    verified_at = datetime.now(UTC).isoformat()
    previous_revision_id = entry.active_revision_id
    entry.definition = definition
    entry.execution_state = "verified"
    entry.execution_details = {
        "version": 1,
        "status": "verified",
        "definition_hash": definition_hash,
        "last_verified_run_id": str(probe_run_id),
        "verified_at": verified_at,
        "checks": [{"name": key, "value": value} for key, value in stats.items()],
        "summary": summary,
    }
    entry.evidence = [
        *list(entry.evidence or []),
        {
            "kind": "semantic_execution_verification",
            "status": "verified",
            "semantic_entry_id": str(entry.id),
            "definition_hash": definition_hash,
            "analysis_run_id": str(probe_run_id),
            "rule_value": entry.value,
            "recorded_at": verified_at,
            "probe": stats,
        },
    ]
    await append_semantic_revision(
        db,
        entry,
        mutation_kind="execution_verified",
        actor_source="system",
        reason="系统探测查询已在真实数据上验证该候选",
        expected_active_revision_id=previous_revision_id,
    )


async def _semantic_entry_allowed_actions(
    db: AsyncSession,
    entry: SemanticEntry,
) -> list[str]:
    if entry.state != "candidate":
        return []
    if not entry.is_active:
        return ["restore"] if await _restore_candidate_target(db, entry) is not None else []

    actions = ["ignore"]
    if entry.validity != "stale" and entry.execution_state != "verified":
        if entry.entry_type == "relationship" and entry.definition:
            actions.append("queue_validation")
        elif entry.entry_type in {"metric", "dimension"} and (
            entry.key.startswith("metric_candidate:") or entry.key.startswith("grain:")
        ):
            actions.append("queue_validation")
    if entry.execution_state != "verified" and entry.definition:
        actions.append("attest")
    if await _remember_candidate_rejection(db, entry) is None:
        actions.append("remember")
    return actions


async def _semantic_entry_response(
    db: AsyncSession,
    entry: SemanticEntry,
    *,
    source_catalog: SemanticSourceCatalog | None = None,
    source_resolution: SemanticSourceResolution | None = None,
) -> SemanticEntryResponse:
    if source_catalog is None:
        source_catalog = await _semantic_source_catalog(db, entry.project_id)
    resolution = source_resolution or resolve_semantic_source_scope(entry, source_catalog)
    response = SemanticEntryResponse.model_validate(entry)
    response.allowed_actions = await _semantic_entry_allowed_actions(db, entry)
    response.source_refs = [
        SemanticSourceRef.model_validate(source_ref.as_dict())
        for source_ref in resolution.source_refs
    ]
    response.source_scope = resolution.source_scope
    return response


async def _semantic_source_catalog(
    db: AsyncSession,
    project_id: UUID,
) -> SemanticSourceCatalog:
    result = await db.execute(
        select(ProjectDataSource, Connection.driver)
        .outerjoin(Connection, Connection.id == ProjectDataSource.connection_id)
        .where(
            ProjectDataSource.project_id == project_id,
            ProjectDataSource.status != "superseded",
        )
    )
    return SemanticSourceCatalog.from_rows(result.all())


@router.get("/{project_id}/knowledge", response_model=APIResponse[list[SemanticEntryResponse]])
async def list_knowledge(project_id: UUID, db: AsyncSession = Depends(get_db)):
    await _project_or_404(db, project_id)
    source_catalog = await _semantic_source_catalog(db, project_id)
    result = await db.execute(
        select(SemanticEntry)
        .where(
            SemanticEntry.project_id == project_id,
            SemanticEntry.is_active.is_(True),
        )
        .order_by(SemanticEntry.state.desc(), SemanticEntry.key)
    )
    return APIResponse.ok(
        data=[
            await _semantic_entry_response(db, item, source_catalog=source_catalog)
            for item in result.scalars()
        ]
    )


@router.get(
    "/{project_id}/knowledge/summary",
    response_model=APIResponse[SemanticEntrySummaryResponse],
)
async def summarize_knowledge(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    await _project_or_404(db, project_id)
    active = SemanticEntry.is_active.is_(True)
    business_facing = _business_facing_semantic_entry_condition()
    active_business_facing = active & business_facing
    result = await db.execute(
        select(
            func.coalesce(
                func.sum(case((active_business_facing, 1), else_=0)), 0
            ).label("active_total"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            active
                            & (SemanticEntry.state == "candidate")
                            & (SemanticEntry.validity != "stale")
                            & business_facing,
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("pending_total"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            active_business_facing
                            & (SemanticEntry.entry_type == "relationship"),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("relationship_total"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            active_business_facing
                            & (SemanticEntry.state == "confirmed"),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("confirmed_total"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            active_business_facing
                            & (SemanticEntry.state == "locked"),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("locked_total"),
        ).where(SemanticEntry.project_id == project_id)
    )
    row = result.one()
    return APIResponse.ok(
        data=SemanticEntrySummaryResponse(
            active_total=int(row.active_total),
            pending_total=int(row.pending_total),
            relationship_total=int(row.relationship_total),
            confirmed_total=int(row.confirmed_total),
            locked_total=int(row.locked_total),
        )
    )


@router.get(
    "/{project_id}/knowledge/page",
    response_model=APIResponse[SemanticEntryPageResponse],
)
async def page_knowledge(
    project_id: UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    search: str | None = Query(default=None, max_length=200),
    entry_type: Literal[
        "metric",
        "dimension",
        "relationship",
        "business_rule",
        "cleaning_rule",
        "verified_query",
    ]
    | None = Query(default=None),
    state: Literal["candidate", "confirmed", "locked"] | None = Query(default=None),
    validity: Literal["active", "unverified", "stale"] | None = Query(default=None),
    source_scope: SemanticSourceScopeFilter | None = Query(default=None),
    source_id: str | None = Query(default=None, max_length=64),
    left_table: str | None = Query(default=None, max_length=255),
    right_table: str | None = Query(default=None, max_length=255),
    business_facing_only: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
):
    await _project_or_404(db, project_id)
    source_catalog = await _semantic_source_catalog(db, project_id)
    statement = select(SemanticEntry).where(SemanticEntry.project_id == project_id)
    if validity != "stale":
        statement = statement.where(SemanticEntry.is_active.is_(True))
    if business_facing_only:
        statement = statement.where(_business_facing_semantic_entry_condition())
    if entry_type is not None:
        statement = statement.where(SemanticEntry.entry_type == entry_type)
    if state is not None:
        statement = statement.where(SemanticEntry.state == state)
    if validity is not None:
        statement = statement.where(SemanticEntry.validity == validity)
    normalized_search = search.strip() if search else None
    normalized_source_id = source_id.strip() if source_id else None
    normalized_left_table = left_table.strip() if left_table else None
    normalized_right_table = right_table.strip() if right_table else None
    if normalized_left_table:
        statement = statement.where(
            func.lower(
                SemanticEntry.definition["left"]["table_or_view"].as_string()
            )
            == normalized_left_table.casefold()
        )
    if normalized_right_table:
        statement = statement.where(
            func.lower(
                SemanticEntry.definition["right"]["table_or_view"].as_string()
            )
            == normalized_right_table.casefold()
        )
    if normalized_search:
        escaped = (
            normalized_search.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        pattern = f"%{escaped}%"
        statement = statement.where(
            or_(
                SemanticEntry.key.ilike(pattern, escape="\\"),
                SemanticEntry.value.ilike(pattern, escape="\\"),
            )
        )
    statement = statement.order_by(*_semantic_entry_order_by())
    requires_source_filter = bool(normalized_source_id or source_scope)
    page_resolutions: dict[UUID, SemanticSourceResolution] = {}
    if requires_source_filter:
        result = await db.execute(statement)
        entries = []
        for entry in result.scalars():
            resolution = resolve_semantic_source_scope(entry, source_catalog)
            if normalized_source_id and normalized_source_id not in resolution.matching_source_ids:
                continue
            if source_scope and not resolution_matches_scope(resolution, source_scope):
                continue
            page_resolutions[entry.id] = resolution
            entries.append(entry)
        total = len(entries)
        page = entries[offset : offset + limit]
    else:
        count_statement = select(func.count()).select_from(statement.order_by(None).subquery())
        total = int(await db.scalar(count_statement) or 0)
        result = await db.execute(statement.offset(offset).limit(limit))
        page = list(result.scalars())
    next_offset = offset + len(page) if offset + len(page) < total else None
    return APIResponse.ok(
        data=SemanticEntryPageResponse(
            items=[
                await _semantic_entry_response(
                    db,
                    item,
                    source_catalog=source_catalog,
                    source_resolution=page_resolutions.get(item.id),
                )
                for item in page
            ],
            total=total,
            offset=offset,
            limit=limit,
            has_more=next_offset is not None,
            next_offset=next_offset,
        )
    )


@router.post(
    "/{project_id}/knowledge/batch",
    response_model=APIResponse[SemanticEntryBatchResponse],
)
async def batch_knowledge_candidates(
    project_id: UUID,
    payload: SemanticEntryBatchRequest,
    db: AsyncSession = Depends(get_db),
):
    await _project_or_404(db, project_id)
    entry_ids = [item.entry_id for item in payload.items]
    result = await db.execute(
        select(SemanticEntry)
        .where(
            SemanticEntry.project_id == project_id,
            SemanticEntry.id.in_(entry_ids),
        )
        .with_for_update()
    )
    entries_by_id = {entry.id: entry for entry in result.scalars()}
    if len(entries_by_id) != len(entry_ids):
        raise HTTPException(status_code=404, detail="批处理中的候选不存在")

    ordered_entries: list[SemanticEntry] = []
    restore_targets: dict[UUID, SemanticEntryRevision] = {}
    for item in payload.items:
        entry = entries_by_id[item.entry_id]
        if entry.active_revision_id != item.expected_active_revision_id:
            raise HTTPException(
                status_code=409,
                detail=f"候选 {entry.key} 已被更新，请刷新后重试",
            )
        if entry.state != "candidate":
            raise HTTPException(
                status_code=409,
                detail=f"{entry.key} 已不是可处理的候选",
            )
        if payload.action == "restore":
            target = await _restore_candidate_target(db, entry)
            if target is None:
                raise HTTPException(
                    status_code=409,
                    detail=f"{entry.key} 不是可恢复的已忽略候选",
                )
            restore_targets[entry.id] = target
        elif not entry.is_active:
            raise HTTPException(
                status_code=409,
                detail=f"{entry.key} 当前未启用，只能先恢复",
            )
        elif payload.action == "queue_validation":
            if entry.validity == "stale" or entry.execution_state == "verified":
                raise HTTPException(
                    status_code=409,
                    detail=f"{entry.key} 已验证或已失效，不需要重新验证",
                )
            if entry.entry_type == "relationship":
                if not entry.definition:
                    raise HTTPException(
                        status_code=409,
                        detail=f"{entry.key} 不是可排队验证的关联候选",
                    )
            elif entry.entry_type not in {"metric", "dimension"}:
                raise HTTPException(
                    status_code=409,
                    detail=f"{entry.key} 不是可验证的候选",
                )
        elif payload.action == "remember":
            rejection = await _remember_candidate_rejection(db, entry)
            if rejection:
                raise HTTPException(
                    status_code=409,
                    detail=f"{entry.key}：{rejection}",
                )
        elif payload.action == "attest":
            if not entry.is_active:
                raise HTTPException(
                    status_code=409,
                    detail=f"{entry.key} 已忽略，请先恢复再人工确认",
                )
            if entry.execution_state == "verified":
                raise HTTPException(
                    status_code=409,
                    detail=f"{entry.key} 已经通过验证，无需重复确认",
                )
            if not entry.definition:
                raise HTTPException(
                    status_code=409,
                    detail=f"{entry.key} 还没有业务定义，请先补充定义再人工确认",
                )
        ordered_entries.append(entry)

    now = datetime.now(UTC).isoformat()
    queued_entry_ids: list[UUID] = []
    try:
        for entry in ordered_entries:
            previous_revision_id = entry.active_revision_id
            if payload.action == "ignore":
                entry.is_active = False
                entry.validity = "stale"
                reset_semantic_execution_proof(entry)
                entry.evidence = [
                    *list(entry.evidence or []),
                    {
                        "kind": "semantic_candidate_ignored",
                        "semantic_entry_id": str(entry.id),
                        "based_on_revision_id": str(previous_revision_id),
                        "ignored_at": now,
                        "reason": payload.reason,
                    },
                ]
                await append_semantic_revision(
                    db,
                    entry,
                    mutation_kind="candidate_ignored",
                    actor_source="user",
                    reason=payload.reason or "用户忽略候选理解",
                    expected_active_revision_id=previous_revision_id,
                )
            elif payload.action == "queue_validation":
                if entry.entry_type != "relationship":
                    # Metric/dimension candidates are verified immediately by a
                    # deterministic probe query instead of an analyst round-trip.
                    await _probe_column_candidate(db, project_id=project_id, entry=entry)
                    continue
                definition_hash = stable_payload_hash(entry.definition)
                entry.validity = "unverified"
                entry.execution_state = "needs_validation"
                entry.execution_details = {
                    "version": 1,
                    "status": "needs_validation",
                    "definition_hash": definition_hash,
                    "queued_from_revision_id": str(previous_revision_id),
                    "queued_at": now,
                    "summary": "已选择这项关联候选；等待真实数据关联验收。",
                }
                entry.source = "user"
                entry.evidence = [
                    *list(entry.evidence or []),
                    {
                        "kind": "relationship_validation_requested",
                        "semantic_entry_id": str(entry.id),
                        "based_on_revision_id": str(previous_revision_id),
                        "definition_hash": definition_hash,
                        "requested_at": now,
                        "reason": payload.reason,
                    },
                ]
                await append_semantic_revision(
                    db,
                    entry,
                    mutation_kind="validation_queued",
                    actor_source="user",
                    reason=payload.reason or "用户请求验证关联候选",
                    expected_active_revision_id=previous_revision_id,
                )
                queued_entry_ids.append(entry.id)
            elif payload.action == "attest":
                # Human attestation: the user vouches for this candidate without
                # a system probe. Bookkeeping mirrors a verified execution so the
                # remember gate can bind proof to the current definition.
                definition_hash = stable_payload_hash(entry.definition)
                value_hash = stable_payload_hash(entry.value)
                attestation_run_id = f"human-attestation:{uuid4()}"
                entry.execution_state = "verified"
                entry.validity = "active"
                entry.source = "user"
                entry.execution_details = {
                    "version": 1,
                    "status": "verified",
                    "definition_hash": definition_hash,
                    "value_hash": value_hash,
                    "last_verified_run_id": attestation_run_id,
                    "verified_at": now,
                    "summary": "人工确认验证：用户直接确认这条理解可用，未走系统探测。",
                }
                entry.evidence = [
                    *list(entry.evidence or []),
                    {
                        "kind": "semantic_human_attestation",
                        "semantic_entry_id": str(entry.id),
                        "analysis_run_id": attestation_run_id,
                        "definition_hash": definition_hash,
                        "value_hash": value_hash,
                        "status": "verified",
                        "actor_source": "user",
                        "verified_at": now,
                        "reason": payload.reason,
                    },
                ]
                await append_semantic_revision(
                    db,
                    entry,
                    mutation_kind="execution_verified",
                    actor_source="user",
                    reason=payload.reason or "用户人工确认候选可用",
                    expected_active_revision_id=previous_revision_id,
                )
            elif payload.action == "remember":
                definition_hash = stable_payload_hash(entry.definition)
                value_hash = stable_payload_hash(entry.value)
                entry.state = "confirmed"
                entry.confidence = 1
                entry.source = "user"
                entry.evidence = [
                    *list(entry.evidence or []),
                    {
                        "kind": "verified_candidate_remembered",
                        "semantic_entry_id": str(entry.id),
                        "validated_revision_id": str(previous_revision_id),
                        "definition_hash": definition_hash,
                        "value_hash": value_hash,
                        "remembered_at": now,
                        "reason": payload.reason,
                    },
                ]
                await append_semantic_revision(
                    db,
                    entry,
                    mutation_kind="verified_candidate_remembered",
                    actor_source="user",
                    reason=payload.reason or "用户记住已验证候选",
                    expected_active_revision_id=previous_revision_id,
                )
                await resolve_confirmed_ambiguity(db, project_id, entry.key)
            else:
                await restore_semantic_revision(
                    db,
                    entry,
                    restore_targets[entry.id],
                    expected_active_revision_id=previous_revision_id,
                    reason=payload.reason or "重新考虑已忽略候选",
                    mutation_kind="candidate_restored",
                    actor_source="user",
                )
        await db.commit()
    except SemanticRevisionConflictError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    for entry in ordered_entries:
        await db.refresh(entry)
    validation_prompt = None
    validation_selection = []
    queue_message = "关联候选已排队等待真实数据验证"
    if payload.action == "queue_validation":
        relationship_entries = [
            entry for entry in ordered_entries if entry.entry_type == "relationship"
        ]
        probed_count = len(ordered_entries) - len(relationship_entries)
        validation_selection = [
            {
                "entry_id": entry.id,
                "expected_active_revision_id": entry.active_revision_id,
            }
            for entry in relationship_entries
        ]
        if relationship_entries:
            labels = "；".join(
                f"{entry.key}（{entry.value}）" for entry in relationship_entries[:20]
            )
            suffix = "；其余候选也按相同标准逐项核对" if len(relationship_entries) > 20 else ""
            validation_prompt = (
                "请基于当前项目的真实完整数据验证这些候选关联："
                f"{labels}{suffix}。逐项检查匹配率、唯一性和行数扩张，"
                "应用关联后重新验证最终结果；失败的候选不要确认。"
            )
        if probed_count and not relationship_entries:
            queue_message = "字段候选已在真实数据上探测验证，现在可以记住了"
        elif probed_count:
            queue_message = "关联候选已排队等待验证；字段候选已完成探测验证"
        else:
            queue_message = "关联候选已排队等待真实数据验证"
    message = {
        "ignore": "候选已停用，历史版本仍保留",
        "queue_validation": queue_message,
        "remember": "已记住通过当前版本验证的候选",
        "restore": "已恢复候选，可重新考虑或验证",
        "attest": "已人工确认这条理解可用，现在可以记住了",
    }[payload.action]
    source_catalog = await _semantic_source_catalog(db, project_id)
    return APIResponse.ok(
        data=SemanticEntryBatchResponse(
            action=payload.action,
            items=[
                await _semantic_entry_response(db, item, source_catalog=source_catalog)
                for item in ordered_entries
            ],
            queued_entry_ids=queued_entry_ids,
            validation_selection=validation_selection,
            validation_prompt=validation_prompt,
        ),
        message=message,
    )


@router.post("/{project_id}/knowledge", response_model=APIResponse[SemanticEntryResponse])
async def create_knowledge(
    project_id: UUID,
    payload: SemanticEntryCreate,
    db: AsyncSession = Depends(get_db),
):
    await _project_or_404(db, project_id)
    existing_result = await db.execute(
        select(SemanticEntry)
        .where(
            SemanticEntry.project_id == project_id,
            SemanticEntry.key == payload.key,
        )
        .with_for_update()
    )
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        if payload.source == "user":
            raise HTTPException(status_code=409, detail="这个业务标识已被当前项目使用")
        if existing.state == "candidate" and (
            payload.state != existing.state or payload.validity != existing.validity
        ):
            raise HTTPException(
                status_code=409,
                detail="待核对理解的采用状态只能通过项目理解操作修改",
            )
        if existing.state == "locked" and payload.source != "user":
            raise HTTPException(status_code=409, detail="该业务定义已锁定")
        changes_execution_contract = (
            existing.value != payload.value
            or existing.definition != payload.model_dump(mode="json").get("definition")
            or existing.validity != payload.validity
        )
        for key, value in payload.model_dump(mode="json").items():
            setattr(existing, key, value)
        existing.is_active = True
        if changes_execution_contract:
            _reset_semantic_execution_state(existing)
        try:
            await append_semantic_revision(
                db,
                existing,
                mutation_kind="user_upsert",
                actor_source=payload.source,
                reason="更新业务定义",
            )
        except SemanticRevisionConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if payload.state in {"confirmed", "locked"}:
            await resolve_confirmed_ambiguity(db, project_id, payload.key)
        await db.commit()
        await db.refresh(existing)
        return APIResponse.ok(
            data=await _semantic_entry_response(db, existing), message="理解已更新"
        )
    entry = SemanticEntry(project_id=project_id, **payload.model_dump(mode="json"))
    _reset_semantic_execution_state(entry)
    db.add(entry)
    await db.flush()
    await append_semantic_revision(
        db,
        entry,
        mutation_kind="created",
        actor_source=payload.source,
        reason="创建业务定义",
    )
    if payload.state in {"confirmed", "locked"}:
        await resolve_confirmed_ambiguity(db, project_id, payload.key)
    await db.commit()
    await db.refresh(entry)
    return APIResponse.ok(data=await _semantic_entry_response(db, entry), message="理解已保存")


@router.get(
    "/{project_id}/knowledge/{entry_id}",
    response_model=APIResponse[SemanticEntryResponse],
)
async def get_knowledge_entry(
    project_id: UUID,
    entry_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SemanticEntry).where(
            SemanticEntry.id == entry_id,
            SemanticEntry.project_id == project_id,
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=404, detail="业务理解不存在")
    return APIResponse.ok(data=await _semantic_entry_response(db, entry))


@router.put("/{project_id}/knowledge/{entry_id}", response_model=APIResponse[SemanticEntryResponse])
async def update_knowledge(
    project_id: UUID,
    entry_id: UUID,
    payload: SemanticEntryUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SemanticEntry)
        .where(SemanticEntry.id == entry_id, SemanticEntry.project_id == project_id)
        .with_for_update()
    )
    entry = result.scalar_one_or_none()
    if entry is None or entry.project_id != project_id:
        raise HTTPException(status_code=404, detail="业务理解不存在")
    changes = payload.model_dump(
        mode="json",
        exclude_unset=True,
        exclude={"expected_active_revision_id"},
    )
    next_entry_type = changes.get("entry_type", entry.entry_type)
    next_definition = changes.get("definition", entry.definition)
    try:
        validate_semantic_definition_compatibility(next_entry_type, next_definition)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if (
        entry.state == "candidate"
        and {"state", "validity"} & changes.keys()
        and payload.source != "user"
    ):
        raise HTTPException(
            status_code=409,
            detail="待核对理解的采用状态只能通过项目理解操作修改",
        )
    if entry.state == "locked" and changes and payload.source != "user":
        raise HTTPException(status_code=409, detail="固定口径只能由用户修改")
    if "key" in changes and changes["key"] != entry.key:
        duplicate_result = await db.execute(
            select(SemanticEntry.id).where(
                SemanticEntry.project_id == project_id,
                SemanticEntry.key == changes["key"],
                SemanticEntry.id != entry_id,
            )
        )
        if duplicate_result.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="这个业务标识已被当前项目使用")
    for key, value in changes.items():
        setattr(entry, key, value)
    if {"key", "value", "entry_type", "definition", "validity"} & changes.keys():
        _reset_semantic_execution_state(entry)
    if changes:
        try:
            await append_semantic_revision(
                db,
                entry,
                mutation_kind="user_updated",
                actor_source=payload.source or "user",
                reason="用户修改业务定义",
                expected_active_revision_id=(
                    payload.expected_active_revision_id
                    if payload.expected_active_revision_id is not None
                    else entry.active_revision_id
                ),
            )
        except SemanticRevisionConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    if entry.state in {"confirmed", "locked"}:
        await resolve_confirmed_ambiguity(db, project_id, entry.key)
    await db.commit()
    await db.refresh(entry)
    return APIResponse.ok(data=await _semantic_entry_response(db, entry), message="理解已更新")


@router.get(
    "/{project_id}/knowledge/{entry_id}/revisions",
    response_model=APIResponse[list[SemanticEntryRevisionResponse]],
)
async def list_knowledge_revisions(
    project_id: UUID,
    entry_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    entry = await db.get(SemanticEntry, entry_id)
    if entry is None or entry.project_id != project_id:
        raise HTTPException(status_code=404, detail="业务理解不存在")
    result = await db.execute(
        select(SemanticEntryRevision)
        .where(
            SemanticEntryRevision.project_id == project_id,
            SemanticEntryRevision.semantic_entry_id == entry_id,
        )
        .order_by(SemanticEntryRevision.revision_number.desc())
    )
    return APIResponse.ok(
        data=[SemanticEntryRevisionResponse.model_validate(item) for item in result.scalars()]
    )


@router.post(
    "/{project_id}/knowledge/{entry_id}/revisions/{revision_id}/restore",
    response_model=APIResponse[SemanticEntryResponse],
)
async def restore_knowledge_revision(
    project_id: UUID,
    entry_id: UUID,
    revision_id: UUID,
    payload: SemanticEntryRestoreRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SemanticEntry)
        .where(SemanticEntry.id == entry_id, SemanticEntry.project_id == project_id)
        .with_for_update()
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=404, detail="业务理解不存在")
    revision = await semantic_revision_or_none(
        db,
        project_id=project_id,
        entry_id=entry_id,
        revision_id=revision_id,
    )
    if revision is None:
        raise HTTPException(status_code=404, detail="历史版本不存在")
    try:
        await restore_semantic_revision(
            db,
            entry,
            revision,
            expected_active_revision_id=payload.expected_active_revision_id,
            reason=payload.reason,
        )
    except SemanticRevisionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if entry.state in {"confirmed", "locked"} and entry.validity == "active":
        await resolve_confirmed_ambiguity(db, project_id, entry.key)
    await db.commit()
    await db.refresh(entry)
    return APIResponse.ok(
        data=await _semantic_entry_response(db, entry),
        message="已恢复这个历史版本；执行方式需要重新验证",
    )


def _normalized_correction_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def _reset_semantic_execution_state(entry: SemanticEntry) -> None:
    """A user edit invalidates prior execution proof without discarding the meaning."""
    reset_semantic_execution_proof(entry)


def _correction_fingerprint(payload: AnalysisCorrectionCreate) -> str:
    material = "\n".join(
        [
            payload.correction_type,
            payload.scope,
            payload.target_key or "",
            payload.selection.field_ref if payload.selection is not None else "",
            _normalized_correction_text(payload.text),
        ]
    )
    return hashlib.sha256(material.encode()).hexdigest()


def _correction_rule_key(payload: AnalysisCorrectionCreate) -> str:
    if not payload.target_key:
        raise ValueError("project knowledge requires a stable target key")
    return payload.target_key


def _correction_evidence(
    correction: AnalysisCorrection,
    payload: AnalysisCorrectionCreate,
) -> dict[str, Any]:
    return {
        "kind": "user_correction",
        "correction_id": str(correction.id),
        "analysis_run_id": str(payload.analysis_run_id),
        "report_title": payload.report_title,
        "scope": payload.scope,
        "target_ref": payload.target_ref,
        "target_key": None if payload.target_ref else payload.target_key,
        "selection": (
            payload.selection.model_dump(mode="json")
            if payload.selection is not None
            else None
        ),
    }


def _public_correction_selection(
    correction: AnalysisCorrection,
) -> MetricColumnCorrectionSelection | None:
    for item in correction.evidence or []:
        if not isinstance(item, dict) or item.get("kind") != "user_correction":
            continue
        selection = item.get("selection")
        if not isinstance(selection, dict):
            continue
        try:
            return MetricColumnCorrectionSelection.model_validate(selection)
        except ValidationError:
            return None
    return None


def _analysis_correction_response(
    correction: AnalysisCorrection,
) -> AnalysisCorrectionResponse:
    response = AnalysisCorrectionResponse.model_validate(correction)
    return response.model_copy(update={"selection": _public_correction_selection(correction)})


def _inferred_correction_target_key(
    run: AnalysisRun,
    payload: AnalysisCorrectionCreate,
) -> str | None:
    """Reuse the stable business concept already resolved inside this run.

    A report correction may follow a material clarification.  The clarification
    receipt is system-owned evidence linking the report back to that semantic
    slot; using the correction text hash instead would make the same question
    reappear on the next data period.
    """

    if payload.target_key:
        return payload.target_key
    checkpoint = run.checkpoint if isinstance(run.checkpoint, dict) else {}
    tool_history = [
        item
        for item in checkpoint.get("tool_history") or []
        if isinstance(item, dict)
    ]
    if payload.correction_type == "relationship_rule":
        relationship_keys = {
            str(item.get(field) or "").strip()
            for item in tool_history
            if item.get("kind") in {"join", "relationship_validation", "relationship_application"}
            for field in ("relationship_key", "candidate_relationship_key")
            if str(item.get(field) or "").strip()
        }
        if len(relationship_keys) == 1:
            return next(iter(relationship_keys))[:160]
        # A relationship correction must never be attached to an unrelated
        # clarification key from the same report.
        return None

    applied_rule_keys = {
        str(item.get("rule_key") or "").strip()
        for item in tool_history
        if item.get("kind") == "business_rule_application"
        and str(item.get("rule_key") or "").strip()
    }
    if len(applied_rule_keys) == 1:
        return next(iter(applied_rule_keys))[:160]

    receipt = checkpoint.get("confirmation_receipt")
    if isinstance(receipt, dict) and receipt.get("applied") and not receipt.get("conflict"):
        key = str(receipt.get("key") or "").strip()
        if key:
            return key[:160]
    report = run.report if isinstance(run.report, dict) else {}
    confirmation = report.get("confirmation")
    if isinstance(confirmation, dict):
        key = str(confirmation.get("key") or "").strip()
        if key:
            return key[:160]
    return None


async def _effective_correction_payload(
    db: AsyncSession,
    run: AnalysisRun,
    payload: AnalysisCorrectionCreate,
    *,
    existing_correction: AnalysisCorrection | None = None,
) -> AnalysisCorrectionCreate:
    """Resolve an opaque target or preserve the conservative legacy contract."""

    if (
        existing_correction is not None
        and payload.scope == "project"
        and payload.target_ref == existing_correction.target_ref
        and "selection" not in payload.model_fields_set
    ):
        persisted_selection = _public_correction_selection(existing_correction)
        if persisted_selection is not None:
            payload = payload.model_copy(update={"selection": persisted_selection})
    if "target_ref" in payload.model_fields_set and payload.target_ref is None:
        # New clients use explicit null for “the overall conclusion / other”.
        # It is an intentional unbound choice and must not trigger legacy
        # single-target inference or accept a parallel internal key.
        return payload.model_copy(update={"target_ref": None, "target_key": None})
    if payload.target_ref:
        target = await resolve_report_correction_target(db, run, payload.target_ref)
        if target is None:
            may_edit_owned_head = (
                existing_correction is not None
                and payload.target_ref == existing_correction.target_ref
                and await _correction_owns_semantic_head(db, existing_correction)
            )
            if not may_edit_owned_head:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="这个修正目标不属于当前调查或已失效，请重新选择",
                )
            assert existing_correction is not None
            if payload.selection is not None:
                if existing_correction.correction_type != "metric_definition":
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="这个修正目标不支持指标字段选择",
                    )
                option = await resolve_metric_column_correction_option(
                    db,
                    run,
                    existing_correction.target_ref,
                    payload.selection.field_ref,
                    allow_unlisted_metric_target=True,
                )
                if option is None:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="所选指标字段不属于这次调查或已经失效，请重新选择",
                    )
            return payload.model_copy(
                update={
                    "target_ref": existing_correction.target_ref,
                    "target_key": existing_correction.target_key,
                    "correction_type": existing_correction.correction_type,
                }
            )
        if payload.selection is not None:
            if target.correction_type != "metric_definition":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="这个修正目标不支持指标字段选择",
                )
            option = await resolve_metric_column_correction_option(
                db,
                run,
                target.target_ref,
                payload.selection.field_ref,
            )
            if option is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="所选指标字段不属于这次调查或已经失效，请重新选择",
                )
        return payload.model_copy(
            update={
                "target_ref": target.target_ref,
                "target_key": target.target_key,
                "correction_type": target.correction_type,
            }
        )
    return payload.model_copy(
        update={
            "target_ref": None,
            "target_key": _inferred_correction_target_key(run, payload),
        }
    )


async def _correction_owns_semantic_head(
    db: AsyncSession,
    correction: AnalysisCorrection,
) -> bool:
    if correction.semantic_entry_id is None or not correction.target_key:
        return False
    entry = await db.get(SemanticEntry, correction.semantic_entry_id)
    if (
        entry is None
        or entry.project_id != correction.project_id
        or entry.key != correction.target_key
    ):
        return False
    revision_result = await db.execute(
        select(SemanticEntryRevision)
        .where(
            SemanticEntryRevision.semantic_entry_id == entry.id,
            SemanticEntryRevision.source_correction_id == str(correction.id),
            SemanticEntryRevision.mutation_kind == "correction_promoted",
        )
        .order_by(SemanticEntryRevision.revision_number.desc())
    )
    revision = revision_result.scalars().first()
    return revision is not None and entry.active_revision_id == revision.id


def _correction_entry_type(correction_type: str) -> str:
    if correction_type == "metric_definition":
        return "metric"
    if correction_type == "relationship_rule":
        return "relationship"
    return "business_rule"


async def _detach_correction_rule(
    db: AsyncSession,
    correction: AnalysisCorrection,
) -> str:
    """Detach one reversible correction from project knowledge."""

    if correction.semantic_entry_id is None:
        return "not_attached"
    rule = await db.get(SemanticEntry, correction.semantic_entry_id)
    if rule is None or rule.project_id != correction.project_id:
        correction.semantic_entry_id = None
        return "not_attached"
    if rule.state == "locked":
        return "head_superseded"

    revision_result = await db.execute(
        select(SemanticEntryRevision)
        .where(
            SemanticEntryRevision.semantic_entry_id == rule.id,
            SemanticEntryRevision.source_correction_id == str(correction.id),
            SemanticEntryRevision.mutation_kind == "correction_promoted",
        )
        .order_by(SemanticEntryRevision.revision_number.desc())
    )
    promotion_revision = revision_result.scalars().first()
    if promotion_revision is not None:
        # A later user edit, restore, validation, or correction owns the head now.
        # Removing this old correction may unlink it, but must never rewind that head.
        if rule.active_revision_id != promotion_revision.id:
            return "head_superseded"
        correction.semantic_entry_id = None
        if promotion_revision.parent_revision_id is None:
            await deactivate_semantic_entry(
                db,
                rule,
                expected_active_revision_id=promotion_revision.id,
                source_correction_id=correction.id,
            )
            return "deactivated"
        previous_revision = await semantic_revision_or_none(
            db,
            project_id=rule.project_id,
            entry_id=rule.id,
            revision_id=promotion_revision.parent_revision_id,
        )
        if previous_revision is None:
            return "not_attached"
        await restore_semantic_revision(
            db,
            rule,
            previous_revision,
            expected_active_revision_id=promotion_revision.id,
            reason="撤销项目修正并恢复此前定义",
            mutation_kind="correction_detached",
            actor_source="user",
            source_correction_id=correction.id,
        )
        return "detached"

    # Compatibility for records promoted before revision history was introduced.
    # Only revert when the current head still contains this correction's provenance.
    active_revision = (
        await semantic_revision_or_none(
            db,
            project_id=rule.project_id,
            entry_id=rule.id,
            revision_id=rule.active_revision_id,
        )
        if rule.active_revision_id is not None
        else None
    )
    if active_revision is not None and active_revision.mutation_kind != "migration_backfill":
        return "head_superseded"
    existing_evidence = list(rule.evidence or [])
    correction_evidence = next(
        (
            item
            for item in existing_evidence
            if item.get("kind") == "user_correction"
            and item.get("correction_id") == str(correction.id)
        ),
        None,
    )
    remaining_evidence = [
        item for item in existing_evidence if item.get("correction_id") != str(correction.id)
    ]
    previous = (
        correction_evidence.get("previous_semantic_snapshot")
        if isinstance(correction_evidence, dict)
        else None
    )
    if correction_evidence is None:
        return "head_superseded"
    correction.semantic_entry_id = None
    if isinstance(previous, dict):
        for field_name in (
            "value",
            "entry_type",
            "state",
            "confidence",
            "definition",
            "validity",
            "execution_state",
            "execution_details",
            "source",
        ):
            if field_name in previous:
                setattr(rule, field_name, previous[field_name])
        rule.evidence = remaining_evidence
        reset_semantic_execution_proof(rule)
        await append_semantic_revision(
            db,
            rule,
            mutation_kind="correction_detached",
            actor_source="user",
            reason="撤销旧版项目修正并恢复此前定义",
            source_correction_id=correction.id,
            expected_active_revision_id=rule.active_revision_id,
        )
        return "detached"
    if remaining_evidence:
        rule.evidence = remaining_evidence
        await append_semantic_revision(
            db,
            rule,
            mutation_kind="correction_detached",
            actor_source="user",
            reason="撤销旧版项目修正",
            source_correction_id=correction.id,
            expected_active_revision_id=rule.active_revision_id,
        )
        return "detached"
    await deactivate_semantic_entry(
        db,
        rule,
        expected_active_revision_id=rule.active_revision_id,
        source_correction_id=correction.id,
    )
    return "deactivated"


async def _promote_correction_rule(
    db: AsyncSession,
    run: AnalysisRun,
    correction: AnalysisCorrection,
    payload: AnalysisCorrectionCreate,
    evidence: dict[str, Any],
) -> None:
    rule_key = _correction_rule_key(payload)
    entry_type = _correction_entry_type(payload.correction_type)
    relationship_needs_validation = entry_type == "relationship"
    selected_metric_column: str | None = None
    selected_metric_binding: dict[str, str] | None = None
    if payload.selection is not None:
        if payload.target_ref is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="所选指标字段缺少调查目标，请重新选择",
            )
        option = await resolve_metric_column_correction_option(
            db,
            run,
            payload.target_ref,
            payload.selection.field_ref,
            # ``_effective_correction_payload`` has already proved either a
            # fresh run target or ownership of the saved correction head.  The
            # latter target intentionally disappears from the ordinary target
            # list after it creates project knowledge, but its run-bound field
            # ref still has to be revalidated against current source profiles.
            allow_unlisted_metric_target=True,
        )
        if option is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="所选指标字段不属于这次调查或已经失效，请重新选择",
            )
        selected_metric_column = option.column
        selected_metric_binding = option.binding
    compilation = await compile_report_correction(
        db,
        run=run,
        correction_id=correction.id,
        target_key=rule_key,
        text=payload.text,
        correction_type=payload.correction_type,
        selected_metric_column=selected_metric_column,
        selected_metric_binding=selected_metric_binding,
    )
    rule_result = await db.execute(
        select(SemanticEntry).where(
            SemanticEntry.project_id == correction.project_id,
            SemanticEntry.key == rule_key,
        )
    )
    rule = rule_result.scalar_one_or_none()
    compiled_definition = compilation.definition
    compiled_evidence = compilation.evidence
    if rule is None and payload.target_ref is not None and compiled_definition is None:
        # The ref proves what business object the user selected, not that free
        # text can be converted into a safe reusable execution contract.
        correction.evidence = [evidence, compiled_evidence]
        return
    rule_state = "candidate" if relationship_needs_validation else "confirmed"
    rule_validity = "unverified" if relationship_needs_validation else compilation.validity
    if compiled_definition is None:
        rule_validity = "unverified"
    if rule is None:
        rule = SemanticEntry(
            project_id=correction.project_id,
            key=rule_key,
            value=payload.text,
            entry_type=entry_type,
            state=rule_state,
            confidence=1,
            definition=compiled_definition,
            validity=rule_validity,
            execution_state=compilation.execution_state,
            execution_details=compilation.execution_details,
            evidence=[evidence, compiled_evidence],
            source="user",
        )
        db.add(rule)
        await db.flush()
        previous_revision_id = None
    else:
        previous_revision_id = rule.active_revision_id
        foreign_correction_ids = {
            str(item.get("correction_id"))
            for item in (rule.evidence or [])
            if item.get("kind") == "user_correction"
            and item.get("correction_id") != str(correction.id)
        }
        if foreign_correction_ids:
            raise HTTPException(
                status_code=409,
                detail="这个业务定义已有另一条项目修正，请先在数据理解中处理冲突",
            )
        definition_changed = rule.definition != compiled_definition
        value_changed = rule.value != payload.text
        if rule.state == "locked":
            raise HTTPException(status_code=409, detail="固定口径只能在数据理解中由用户修改")
        if rule.state != "locked" and (definition_changed or value_changed):
            evidence["previous_semantic_snapshot"] = {
                "value": rule.value,
                "entry_type": rule.entry_type,
                "state": rule.state,
                "confidence": rule.confidence,
                "definition": rule.definition,
                "validity": rule.validity,
                "execution_state": rule.execution_state,
                "execution_details": rule.execution_details,
                "source": rule.source,
            }
        existing_evidence = list(rule.evidence or [])
        if not any(item.get("correction_id") == str(correction.id) for item in existing_evidence):
            rule.evidence = [*existing_evidence, evidence, compiled_evidence]
        rule.value = payload.text
        rule.entry_type = entry_type
        rule.state = rule_state
        rule.definition = compiled_definition
        rule.validity = rule_validity
        rule.execution_state = compilation.execution_state
        rule.execution_details = compilation.execution_details
        rule.confidence = 1
        rule.source = "user"
        rule.is_active = True
    try:
        await append_semantic_revision(
            db,
            rule,
            mutation_kind="correction_promoted",
            actor_source="user",
            reason="将报告修正提升为项目定义",
            source_correction_id=correction.id,
            expected_active_revision_id=previous_revision_id,
        )
    except SemanticRevisionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    correction.evidence = [evidence, compiled_evidence]
    correction.semantic_entry_id = rule.id
    correction.state = "promoted"
    if rule.state in {"confirmed", "locked"} and rule.validity == "active":
        await resolve_confirmed_ambiguity(db, correction.project_id, rule_key)


@router.get(
    "/{project_id}/analysis-runs/{run_id}/correction-targets",
    response_model=APIResponse[list[AnalysisCorrectionTargetResponse]],
)
async def list_analysis_correction_targets(
    project_id: UUID,
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    await _project_or_404(db, project_id)
    run = await db.get(AnalysisRun, run_id)
    if run is None or run.project_id != project_id:
        raise HTTPException(status_code=404, detail="调查记录不存在")
    targets = await discover_report_correction_targets(db, run)
    return APIResponse.ok(
        data=[
            AnalysisCorrectionTargetResponse(
                target_ref=target.target_ref,
                label=target.label,
                description=target.description,
                correction_type=target.correction_type,
            )
            for target in targets
        ]
    )


@router.get(
    "/{project_id}/analysis-runs/{run_id}/correction-targets/{target_ref}/options",
    response_model=APIResponse[list[AnalysisCorrectionTargetOptionResponse]],
)
async def list_analysis_correction_target_options(
    project_id: UUID,
    run_id: UUID,
    target_ref: str,
    db: AsyncSession = Depends(get_db),
):
    await _project_or_404(db, project_id)
    run = await db.get(AnalysisRun, run_id)
    if run is None or run.project_id != project_id:
        raise HTTPException(status_code=404, detail="调查记录不存在")
    target = await resolve_report_correction_target(db, run, target_ref)
    allow_owned_metric_target = False
    if target is None:
        correction_result = await db.execute(
            select(AnalysisCorrection).where(
                AnalysisCorrection.project_id == project_id,
                AnalysisCorrection.analysis_run_id == run_id,
                AnalysisCorrection.target_ref == target_ref,
                AnalysisCorrection.correction_type == "metric_definition",
            )
        )
        owned = [
            correction
            for correction in correction_result.scalars()
            if await _correction_owns_semantic_head(db, correction)
        ]
        if len(owned) != 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="这个修正目标不属于当前调查或已失效，请重新选择",
            )
        allow_owned_metric_target = True
    options = await discover_metric_column_correction_options(
        db,
        run,
        target.target_ref if target is not None else target_ref,
        allow_unlisted_metric_target=allow_owned_metric_target,
    )
    return APIResponse.ok(
        data=[
            AnalysisCorrectionTargetOptionResponse(
                kind="metric_column",
                field_ref=option.field_ref,
                label=option.label,
                description=option.description,
            )
            for option in options
        ]
    )


@router.get(
    "/{project_id}/corrections",
    response_model=APIResponse[list[AnalysisCorrectionResponse]],
)
async def list_analysis_corrections(
    project_id: UUID,
    analysis_run_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    await _project_or_404(db, project_id)
    statement = select(AnalysisCorrection).where(AnalysisCorrection.project_id == project_id)
    if analysis_run_id is not None:
        statement = statement.where(AnalysisCorrection.analysis_run_id == analysis_run_id)
    result = await db.execute(statement.order_by(AnalysisCorrection.created_at.desc()))
    return APIResponse.ok(
        data=[_analysis_correction_response(item) for item in result.scalars()]
    )


@router.post(
    "/{project_id}/corrections",
    response_model=APIResponse[AnalysisCorrectionResponse],
)
async def create_analysis_correction(
    project_id: UUID,
    payload: AnalysisCorrectionCreate,
    db: AsyncSession = Depends(get_db),
):
    await _project_or_404(db, project_id)
    run = await db.get(AnalysisRun, payload.analysis_run_id)
    if run is None or run.project_id != project_id:
        raise HTTPException(status_code=404, detail="要纠正的调查记录不存在")

    effective_payload = await _effective_correction_payload(db, run, payload)

    fingerprint = _correction_fingerprint(effective_payload)
    existing_result = await db.execute(
        select(AnalysisCorrection).where(
            AnalysisCorrection.project_id == project_id,
            AnalysisCorrection.analysis_run_id == payload.analysis_run_id,
            AnalysisCorrection.fingerprint == fingerprint,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        if effective_payload.target_ref and existing.target_ref != effective_payload.target_ref:
            existing.target_ref = effective_payload.target_ref
            existing.evidence = [
                {
                    **item,
                    "target_ref": effective_payload.target_ref,
                }
                if isinstance(item, dict) and item.get("kind") == "user_correction"
                else item
                for item in (existing.evidence or [])
            ]
            await db.commit()
            await db.refresh(existing)
        return APIResponse.ok(
            data=_analysis_correction_response(existing),
            message="这条修正已经记录",
        )

    correction = AnalysisCorrection(
        project_id=project_id,
        analysis_run_id=effective_payload.analysis_run_id,
        target_ref=effective_payload.target_ref,
        target_key=effective_payload.target_key,
        correction_type=effective_payload.correction_type,
        text=effective_payload.text,
        scope=effective_payload.scope,
        state="recorded",
        fingerprint=fingerprint,
        evidence=[],
    )
    db.add(correction)
    await db.flush()
    evidence = _correction_evidence(correction, effective_payload)
    correction.evidence = [evidence]

    if effective_payload.scope == "project" and effective_payload.target_key:
        await _promote_correction_rule(
            db,
            run,
            correction,
            effective_payload,
            evidence,
        )

    await db.commit()
    await db.refresh(correction)
    return APIResponse.ok(
        data=_analysis_correction_response(correction),
        message=(
            "已记住这条业务定义"
            if correction.semantic_entry_id is not None
            else "已记录本次修正；尚未形成可安全复用的执行定义"
            if effective_payload.scope == "project" and effective_payload.target_ref
            else "已记录本次修正；明确业务对象后才能在以后自动复用"
            if effective_payload.scope == "project"
            else "已记录本次修正"
        ),
    )


@router.put(
    "/{project_id}/corrections/{correction_id}",
    response_model=APIResponse[AnalysisCorrectionResponse],
)
async def update_analysis_correction(
    project_id: UUID,
    correction_id: UUID,
    payload: AnalysisCorrectionCreate,
    db: AsyncSession = Depends(get_db),
):
    correction = await db.get(AnalysisCorrection, correction_id)
    if correction is None or correction.project_id != project_id:
        raise HTTPException(status_code=404, detail="修正记录不存在")
    if correction.analysis_run_id != payload.analysis_run_id:
        raise HTTPException(status_code=409, detail="修正记录不属于这次调查")

    run = await db.get(AnalysisRun, payload.analysis_run_id)
    if run is None or run.project_id != project_id:
        raise HTTPException(status_code=404, detail="要纠正的调查记录不存在")
    effective_payload = await _effective_correction_payload(
        db,
        run,
        payload,
        existing_correction=correction,
    )

    fingerprint = _correction_fingerprint(effective_payload)
    duplicate_result = await db.execute(
        select(AnalysisCorrection).where(
            AnalysisCorrection.project_id == project_id,
            AnalysisCorrection.analysis_run_id == payload.analysis_run_id,
            AnalysisCorrection.fingerprint == fingerprint,
            AnalysisCorrection.id != correction_id,
        )
    )
    if duplicate_result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="这条修正已经记录")

    detach_status = await _detach_correction_rule(db, correction)
    if detach_status == "head_superseded":
        raise HTTPException(
            status_code=409,
            detail="这条修正之后业务定义已被更新，请新建修正或先恢复对应版本",
        )
    correction.target_ref = effective_payload.target_ref
    correction.target_key = effective_payload.target_key
    correction.correction_type = effective_payload.correction_type
    correction.text = effective_payload.text
    correction.scope = effective_payload.scope
    correction.state = "recorded"
    correction.fingerprint = fingerprint
    evidence = _correction_evidence(correction, effective_payload)
    correction.evidence = [evidence]
    if effective_payload.scope == "project" and effective_payload.target_key:
        await _promote_correction_rule(
            db,
            run,
            correction,
            effective_payload,
            evidence,
        )

    await db.commit()
    await db.refresh(correction)
    return APIResponse.ok(
        data=_analysis_correction_response(correction),
        message=(
            "业务定义已更新"
            if correction.semantic_entry_id is not None
            else "本次修正已更新；尚未形成可安全复用的执行定义"
            if effective_payload.scope == "project" and effective_payload.target_ref
            else "本次修正已更新；明确业务对象后才能在以后自动复用"
            if effective_payload.scope == "project"
            else "本次修正已更新"
        ),
    )


@router.delete(
    "/{project_id}/corrections/{correction_id}",
    response_model=APIResponse[AnalysisCorrectionDeleteResponse],
)
async def delete_analysis_correction(
    project_id: UUID,
    correction_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    correction = await db.get(AnalysisCorrection, correction_id)
    if correction is None or correction.project_id != project_id:
        raise HTTPException(status_code=404, detail="修正记录不存在")

    project_rule_removed = False
    if correction.semantic_entry_id is not None:
        detach_status = await _detach_correction_rule(db, correction)
        project_rule_removed = detach_status == "deactivated"
        if detach_status == "head_superseded":
            correction.semantic_entry_id = None

    await db.delete(correction)
    await db.commit()
    return APIResponse.ok(
        data=AnalysisCorrectionDeleteResponse(
            deleted=True,
            correction_id=correction_id,
            project_rule_removed=project_rule_removed,
        ),
        message="修正已撤销",
    )


@router.post("/{project_id}/analysis-runs", response_model=APIResponse[AnalysisRunResponse])
async def create_analysis_run(
    project_id: UUID,
    payload: AnalysisRunCreate,
    db: AsyncSession = Depends(get_db),
):
    await _project_or_404(db, project_id)
    run = AnalysisRun(
        project_id=project_id,
        conversation_id=payload.conversation_id,
        query=payload.query,
        state="understanding",
        stage="understanding",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return APIResponse.ok(data=AnalysisRunResponse.model_validate(run))


@router.get("/{project_id}/analysis-runs", response_model=APIResponse[list[AnalysisRunResponse]])
async def list_analysis_runs(project_id: UUID, db: AsyncSession = Depends(get_db)):
    await _project_or_404(db, project_id)
    result = await db.execute(
        select(AnalysisRun)
        .where(AnalysisRun.project_id == project_id)
        .order_by(AnalysisRun.created_at.desc())
    )
    return APIResponse.ok(
        data=[AnalysisRunResponse.model_validate(item) for item in result.scalars()]
    )


@router.get(
    "/{project_id}/trusted-references",
    response_model=APIResponse[list[TrustedProjectReferenceResponse]],
)
async def list_trusted_references(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[TrustedProjectReferenceResponse]]:
    project = await _project_or_404(db, project_id)
    references = sorted(
        _stored_trusted_references(project),
        key=lambda item: item.updated_at,
        reverse=True,
    )
    return APIResponse.ok(data=references)


@router.post(
    "/{project_id}/trusted-references",
    response_model=APIResponse[TrustedProjectReferenceResponse],
)
async def capture_trusted_reference(
    project_id: UUID,
    payload: TrustedProjectReferenceCapture,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[TrustedProjectReferenceResponse]:
    project = await _locked_project_or_404(db, project_id)
    run_result = await db.execute(
        select(AnalysisRun).where(
            AnalysisRun.id == payload.analysis_run_id,
            AnalysisRun.project_id == project_id,
        )
    )
    run = run_result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="调查记录不存在")
    if run.state != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="只能把已完成的调查设为项目依据",
        )

    tool_history = list((run.checkpoint or {}).get("tool_history") or [])
    validation, _ = _final_validation(tool_history)
    evidence = _trusted_validation_evidence(tool_history)
    if not evidence:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="这次调查没有可保存的最终校验证据",
        )

    context = await load_project_context(db, project_id)
    playbook_roles = _playbook_source_roles(context.sources, tool_history, validation)
    source_by_role = {_source_logical_name(item): item for item in context.sources}
    source_roles = [
        TrustedProjectReferenceSourceRole(
            logical_name=item.logical_name,
            source_kind=item.source_kind,
            tables=item.tables[:50],
            fingerprint=(source_by_role.get(item.logical_name) or {}).get("fingerprint"),
            schema_signature=item.schema_signature,
        )
        for item in playbook_roles[:20]
    ]
    if not source_roles:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="最终结果无法绑定当前项目的数据来源，不能设为项目依据",
        )
    confirmed_keys = sorted(
        {
            str(item.get("rule_key") or item.get("knowledge_key") or "")
            for item in tool_history
            if item.get("kind") == "business_rule_application"
            and (item.get("rule_key") or item.get("knowledge_key"))
        }
    )[:100]

    references = _stored_trusted_references(project)
    reference_id = _trusted_reference_id(run.id)
    existing = next((item for item in references if item.id == reference_id), None)
    if existing is not None and existing.state == "active":
        return APIResponse.ok(data=existing, message="该调查已经是项目依据")
    active_count = sum(item.state == "active" for item in references)
    if active_count >= _MAX_ACTIVE_TRUSTED_REFERENCES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"每个项目最多保留 {_MAX_ACTIVE_TRUSTED_REFERENCES} 条有效依据，"
                "请先撤销不再使用的依据"
            ),
        )

    now = datetime.now(UTC)
    raw_report = run.report or {}
    title = str(raw_report.get("title") or run.query).strip()[:200] or "历史分析依据"
    reference = TrustedProjectReferenceResponse(
        id=reference_id,
        run_id=run.id,
        query=run.query,
        title=title,
        report=_trusted_report_snapshot(raw_report),
        source_roles=source_roles,
        confirmed_knowledge_keys=confirmed_keys,
        validation_evidence=evidence,
        state="active",
        created_at=existing.created_at if existing else now,
        updated_at=now,
        revoked_at=None,
    )
    if existing is None:
        if len(references) >= _MAX_STORED_TRUSTED_REFERENCES:
            oldest_revoked = sorted(
                (item for item in references if item.state == "revoked"),
                key=lambda item: item.updated_at,
            )
            while len(references) >= _MAX_STORED_TRUSTED_REFERENCES and oldest_revoked:
                stale = oldest_revoked.pop(0)
                references = [item for item in references if item.id != stale.id]
        if len(references) >= _MAX_STORED_TRUSTED_REFERENCES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="项目依据已达到保存上限，请先撤销或清理旧依据",
            )
        references.append(reference)
    else:
        references = [reference if item.id == reference_id else item for item in references]
    _save_trusted_references(project, references)
    await db.commit()
    await db.refresh(project)
    return APIResponse.ok(data=reference, message="已设为当前项目的历史依据")


@router.post(
    "/{project_id}/trusted-references/{reference_id}/revoke",
    response_model=APIResponse[TrustedProjectReferenceResponse],
)
async def revoke_trusted_reference(
    project_id: UUID,
    reference_id: str,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[TrustedProjectReferenceResponse]:
    project = await _locked_project_or_404(db, project_id)
    references = _stored_trusted_references(project)
    existing = next((item for item in references if item.id == reference_id), None)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目依据不存在")
    if existing.state == "revoked":
        return APIResponse.ok(data=existing, message="该项目依据已经撤销")
    now = datetime.now(UTC)
    revoked = existing.model_copy(update={"state": "revoked", "updated_at": now, "revoked_at": now})
    references = [revoked if item.id == reference_id else item for item in references]
    _save_trusted_references(project, references)
    await db.commit()
    await db.refresh(project)
    return APIResponse.ok(data=revoked, message="已撤销项目依据")


@router.get(
    "/{project_id}/analysis-playbooks",
    response_model=APIResponse[list[AnalysisPlaybookResponse]],
)
async def list_analysis_playbooks(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[AnalysisPlaybookResponse]]:
    project = await _project_or_404(db, project_id)
    playbooks = sorted(
        _stored_analysis_playbooks(project),
        key=lambda item: item.updated_at,
        reverse=True,
    )
    return APIResponse.ok(data=playbooks)


@router.post(
    "/{project_id}/analysis-playbooks",
    response_model=APIResponse[AnalysisPlaybookResponse],
)
async def capture_analysis_playbook(
    project_id: UUID,
    payload: AnalysisPlaybookCapture,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[AnalysisPlaybookResponse]:
    project = await _project_or_404(db, project_id)
    run_result = await db.execute(
        select(AnalysisRun).where(
            AnalysisRun.id == payload.analysis_run_id,
            AnalysisRun.project_id == project_id,
        )
    )
    run = run_result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="调查记录不存在")
    if run.state != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="只能把已完成的调查保存为可复用分析",
        )

    tool_history = list((run.checkpoint or {}).get("tool_history") or [])
    validation, final_data_step = _final_validation(tool_history)
    context = await load_project_context(db, project_id)
    source_roles = _playbook_source_roles(context.sources, tool_history, validation)
    steps, result_aliases = _business_playbook_steps(
        tool_history,
        context.sources,
        source_roles,
        context.executable_relationships,
    )
    validation_summary = _validation_summary(validation, result_aliases)
    playbook_id = _analysis_playbook_id(run.query)
    system_candidate_steps = [step for step in steps if step.kind != "visualize"]
    execution_mode = _playbook_execution_mode(
        tool_history=tool_history,
        source_roles=source_roles,
        steps=system_candidate_steps,
        validation=validation,
        final_data_step=final_data_step,
        playbook_id=playbook_id,
    )
    if execution_mode == "system_structured_query":
        steps = system_candidate_steps
    playbooks = _stored_analysis_playbooks(project)
    existing = next((item for item in playbooks if item.id == playbook_id), None)
    now = datetime.now(UTC)
    default_name = str((run.report or {}).get("title") or run.query).strip()[:160]
    confirmed_keys = sorted(
        {
            str(item.get("rule_key") or item.get("knowledge_key") or "")
            for item in tool_history
            if item.get("kind") == "business_rule_application"
            and (item.get("rule_key") or item.get("knowledge_key"))
        }
    )
    relationship_keys = sorted(
        {
            str(item.get("relationship_key") or "")
            for item in tool_history
            if item.get("relationship_key")
            and item.get("kind") in {"relationship_application", "relationship_validation", "join"}
        }
    )
    playbook = AnalysisPlaybookResponse(
        schema_version=3,
        execution_mode=execution_mode,
        id=playbook_id,
        name=(payload.name or (existing.name if existing else None) or default_name)[:160],
        query=run.query,
        source_roles=source_roles,
        confirmed_knowledge_keys=confirmed_keys,
        relationship_keys=relationship_keys,
        steps=steps,
        validation=validation_summary,
        shape_hash=_playbook_shape_hash(
            source_roles,
            steps,
            validation_summary,
            schema_version=3,
            execution_mode=execution_mode,
        ),
        created_at=existing.created_at if existing else now,
        updated_at=now,
    )
    try:
        await validate_playbook_run_freshness(db, playbook=playbook, run=run)
    except StandingWorkspaceError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if existing is None:
        playbooks.append(playbook)
    else:
        playbooks = [playbook if item.id == playbook_id else item for item in playbooks]
    project.extra_data = {
        **(project.extra_data or {}),
        "analysis_playbooks": [item.model_dump(mode="json") for item in playbooks[-100:]],
    }
    await db.commit()
    await db.refresh(project)
    return APIResponse.ok(
        data=playbook,
        message="已保存为项目可复用分析",
    )


@router.delete(
    "/{project_id}/analysis-playbooks/{playbook_id}",
    response_model=APIResponse[AnalysisPlaybookDeleteResponse],
)
async def delete_analysis_playbook(
    project_id: UUID,
    playbook_id: str,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[AnalysisPlaybookDeleteResponse]:
    project = await _project_or_404(db, project_id)
    playbooks = _stored_analysis_playbooks(project)
    remaining = [item for item in playbooks if item.id != playbook_id]
    if len(remaining) == len(playbooks):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="可复用分析不存在")
    project.extra_data = {
        **(project.extra_data or {}),
        "analysis_playbooks": [item.model_dump(mode="json") for item in remaining],
    }
    await db.commit()
    return APIResponse.ok(
        data=AnalysisPlaybookDeleteResponse(deleted=True, playbook_id=playbook_id),
        message="可复用分析已删除",
    )


@router.delete(
    "/{project_id}/analysis-runs/{run_id}",
    response_model=APIResponse[dict[str, bool]],
)
async def delete_analysis_run(
    project_id: UUID,
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnalysisRun).where(
            AnalysisRun.id == run_id,
            AnalysisRun.project_id == project_id,
        )
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="调查记录不存在")

    await db.execute(delete(ArtifactRecord).where(ArtifactRecord.analysis_run_id == run.id))
    await db.delete(run)
    await db.commit()
    return APIResponse.ok(data={"deleted": True}, message="调查记录已删除")


@router.post(
    "/{project_id}/dependencies",
    response_model=APIResponse[dict[str, Any]],
)
async def install_project_dependencies(
    project_id: UUID,
    payload: ProjectDependencyInstall,
    db: AsyncSession = Depends(get_db),
):
    await _project_or_404(db, project_id)
    manager = ProjectDependencyManager(settings.WORKSPACE_ROOT / str(project_id))
    try:
        message = await manager.install(payload.packages)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return APIResponse.ok(
        data={**manager.describe(), "ready": True},
        message=message,
    )


@router.get(
    "/{project_id}/dependencies",
    response_model=APIResponse[dict[str, Any]],
)
async def list_project_dependencies(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    await _project_or_404(db, project_id)
    manager = ProjectDependencyManager(settings.WORKSPACE_ROOT / str(project_id))
    return APIResponse.ok(data=manager.describe())


@router.get(
    "/{project_id}/analysis-runs/{run_id}/artifacts",
    response_model=APIResponse[list[ArtifactResponse]],
)
async def list_artifacts(project_id: UUID, run_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ArtifactRecord)
        .where(
            ArtifactRecord.project_id == project_id,
            ArtifactRecord.analysis_run_id == run_id,
        )
        .order_by(ArtifactRecord.created_at)
    )
    return APIResponse.ok(data=[ArtifactResponse.model_validate(item) for item in result.scalars()])


@router.get("/{project_id}/analysis-runs/{run_id}/artifacts/{artifact_id}/file")
async def get_artifact_file(
    project_id: UUID,
    run_id: UUID,
    artifact_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ArtifactRecord).where(
            ArtifactRecord.id == artifact_id,
            ArtifactRecord.project_id == project_id,
            ArtifactRecord.analysis_run_id == run_id,
        )
    )
    artifact = result.scalar_one_or_none()
    if artifact is None:
        raise HTTPException(status_code=404, detail="产物不存在")
    relative_path = (artifact.payload or {}).get("relative_path")
    if not relative_path:
        raise HTTPException(status_code=404, detail="该产物没有文件")
    workspace_root = settings.WORKSPACE_ROOT.resolve()
    file_path = (workspace_root / str(relative_path)).resolve()
    try:
        file_path.relative_to(workspace_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="产物路径无效") from exc
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="产物文件不存在")
    return FileResponse(
        file_path,
        media_type="image/png" if file_path.suffix.lower() == ".png" else None,
        filename=file_path.name,
    )


@router.get("/{project_id}/export", response_model=APIResponse[ProjectBundle])
async def export_project(project_id: UUID, db: AsyncSession = Depends(get_db)):
    project = await _project_or_404(db, project_id)
    knowledge_result = await db.execute(
        select(SemanticEntry)
        .where(SemanticEntry.project_id == project_id)
        .order_by(SemanticEntry.key, SemanticEntry.id)
    )
    revision_result = await db.execute(
        select(SemanticEntryRevision)
        .where(SemanticEntryRevision.project_id == project_id)
        .order_by(
            SemanticEntryRevision.semantic_entry_id,
            SemanticEntryRevision.revision_number,
        )
    )
    recipe_result = await db.execute(
        select(SanitationRecipeRecord)
        .where(SanitationRecipeRecord.project_id == project_id)
        .order_by(SanitationRecipeRecord.id)
    )
    sanitation_revision_result = await db.execute(
        select(SanitationRecipeRevisionRecord)
        .join(
            SanitationRecipeRecord,
            SanitationRecipeRecord.id == SanitationRecipeRevisionRecord.recipe_id,
        )
        .where(SanitationRecipeRecord.project_id == project_id)
        .order_by(
            SanitationRecipeRevisionRecord.recipe_id,
            SanitationRecipeRevisionRecord.revision_number,
        )
    )
    knowledge = list(knowledge_result.scalars())
    recipes = list(recipe_result.scalars())
    revisions_by_entry: dict[UUID, list[SemanticEntryRevision]] = {}
    for revision in revision_result.scalars():
        revisions_by_entry.setdefault(revision.semantic_entry_id, []).append(revision)
    if set(revisions_by_entry) - {entry.id for entry in knowledge}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="项目业务定义版本历史存在跨项目引用，无法安全导出",
        )
    semantic_histories: list[dict[str, Any]] = []
    for entry in knowledge:
        revisions = revisions_by_entry.get(entry.id, [])
        if not revisions:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="项目业务定义缺少版本历史，无法安全导出",
            )
        current_snapshot = semantic_entry_snapshot(entry)
        active_revision = next(
            (revision for revision in revisions if revision.id == entry.active_revision_id),
            None,
        )
        if active_revision is None or active_revision.snapshot != current_snapshot:
            changed_fields = sorted(
                field_name
                for field_name in current_snapshot
                if active_revision is None
                or (active_revision.snapshot or {}).get(field_name) != current_snapshot[field_name]
            )
            logger.error(
                "Semantic head %s cannot be exported safely; changed fields without revision: %s",
                entry.key,
                changed_fields,
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="项目业务定义当前值与版本历史不一致，无法安全导出",
            )
        semantic_histories.append(
            {
                "entry_id": entry.id,
                "head": {
                    **semantic_entry_snapshot(entry),
                    "revision_number": entry.revision_number,
                    "active_revision_id": entry.active_revision_id,
                    "created_at": entry.created_at,
                    "updated_at": entry.updated_at,
                },
                "revisions": [
                    {
                        "id": revision.id,
                        "revision_number": revision.revision_number,
                        "parent_revision_id": revision.parent_revision_id,
                        "restored_from_revision_id": revision.restored_from_revision_id,
                        "mutation_kind": revision.mutation_kind,
                        "actor_source": revision.actor_source,
                        "reason": revision.reason,
                        "source_correction_id": revision.source_correction_id,
                        "snapshot": revision.snapshot,
                        "created_at": revision.created_at,
                    }
                    for revision in revisions
                ],
            }
        )

    sanitation_revisions_by_recipe: dict[UUID, list[SanitationRecipeRevisionRecord]] = {}
    for revision in sanitation_revision_result.scalars():
        sanitation_revisions_by_recipe.setdefault(revision.recipe_id, []).append(revision)
    if set(sanitation_revisions_by_recipe) - {recipe.id for recipe in recipes}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="项目整理方法版本历史存在跨项目引用，无法安全导出",
        )
    sanitation_histories: list[dict[str, Any]] = []
    for stored_history in (project.extra_data or {}).get("recipe_template_histories") or []:
        portable_history = dict(stored_history)
        portable_head = dict(portable_history.get("head") or {})
        try:
            portable_head["operations"] = canonicalize_sanitation_operations(
                portable_head.get("operations")
            )
            portable_revisions = []
            for stored_revision in portable_history.get("revisions") or []:
                portable_revision = dict(stored_revision)
                portable_revision["operations"] = canonicalize_sanitation_operations(
                    portable_revision.get("operations")
                )
                portable_revisions.append(portable_revision)
        except SanitationContractError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="导入的历史整理方法包含不兼容步骤，无法安全导出",
            ) from exc
        portable_history["head"] = portable_head
        portable_history["revisions"] = portable_revisions
        sanitation_histories.append(portable_history)

    for recipe in recipes:
        revisions = sanitation_revisions_by_recipe.get(recipe.id, [])
        active_revision = next(
            (revision for revision in revisions if revision.id == recipe.active_revision_id),
            None,
        )
        if (
            not revisions
            or active_revision is None
            or active_revision.id != revisions[-1].id
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="项目整理方法缺少连续版本历史，无法安全导出",
            )
        try:
            canonical_head_operations = canonicalize_sanitation_operations(recipe.operations)
            canonical_revisions = [
                {
                    "id": revision.id,
                    "revision_number": revision.revision_number,
                    "parent_revision_id": revision.parent_revision_id,
                    "state": revision.state,
                    "operations": canonicalize_sanitation_operations(revision.operations),
                    "input_contract": revision.input_contract,
                    "output_contract": revision.output_contract,
                    "actor_source": revision.actor_source,
                    "reason": revision.reason,
                    "source_correction_id": revision.source_correction_id,
                    "created_at": revision.created_at,
                }
                for revision in revisions
            ]
        except SanitationContractError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="项目整理方法包含不兼容步骤，无法安全导出",
            ) from exc
        if (
            canonical_head_operations != canonical_revisions[-1]["operations"]
            or (active_revision.input_contract or {}).get("fingerprint")
            != recipe.input_fingerprint
            or (active_revision.output_contract or {}).get("fingerprint")
            != recipe.output_fingerprint
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="项目整理方法当前值与版本历史不一致，无法安全导出",
            )
        sanitation_histories.append(
            {
                "recipe_id": recipe.id,
                "head": {
                    "name": recipe.name,
                    "status": recipe.status,
                    "operations": canonical_head_operations,
                    "input_fingerprint": recipe.input_fingerprint,
                    "output_fingerprint": recipe.output_fingerprint,
                    "active_revision_id": recipe.active_revision_id,
                    "created_at": recipe.created_at,
                    "updated_at": recipe.updated_at,
                },
                "revisions": canonical_revisions,
            }
        )
    try:
        portable_standing_analyses = [
            StandingAnalysisResponse.model_validate(
                item.model_copy(
                    update={
                        "state": "paused",
                        "baseline": None,
                        "in_flight": None,
                        "last_evaluated_token": None,
                        "last_run_id": None,
                        "last_brief_artifact_id": None,
                        "attention_reason": None,
                    }
                ).model_dump()
            )
            for item in load_standing_analyses(project)
        ]
    except StandingWorkspaceCorruptError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    try:
        bundle = ProjectBundle(
            version=3,
            project=ProjectCreate(name=project.name, description=project.description),
            semantic_entries=[
                SemanticEntryCreate.model_validate(
                    {
                        "key": item.key,
                        "value": item.value,
                        "entry_type": item.entry_type,
                        "state": item.state,
                        "confidence": item.confidence,
                        "definition": item.definition,
                        "validity": item.validity,
                        "evidence": item.evidence,
                        "source": item.source,
                    }
                )
                for item in knowledge
                if item.is_active
            ],
            semantic_histories=semantic_histories,
            sanitation_recipes=[],
            sanitation_histories=sanitation_histories,
            golden_scenarios=list((project.extra_data or {}).get("golden_scenarios") or []),
            analysis_playbooks=_stored_analysis_playbooks(project),
            trusted_references=_stored_trusted_references(project),
            standing_analyses=portable_standing_analyses,
        )
    except ValidationError as exc:
        logger.exception("Project %s has an unsafe semantic revision history", project_id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="项目业务定义版本历史不一致，无法安全导出",
        ) from exc
    return APIResponse.ok(data=bundle)


@router.post("/import", response_model=APIResponse[ProjectResponse])
async def import_project(bundle: ProjectBundle, db: AsyncSession = Depends(get_db)):
    golden_scenarios: list[dict[str, Any]] = []
    for scenario in bundle.golden_scenarios:
        payload = scenario.model_dump(mode="json")
        for application in payload.get("required_rule_applications") or []:
            if application.get("formula_hash") is None:
                application.pop("formula_hash", None)
        golden_scenarios.append(payload)

    imported_at = datetime.now(UTC)
    recipe_template_histories: list[dict[str, Any]] = []
    recipe_template_candidates: list[dict[str, Any]] = []
    try:
        if bundle.version == 3:
            for history in bundle.sanitation_histories:
                new_recipe_id = uuid4()
                revision_id_map = {revision.id: uuid4() for revision in history.revisions}
                portable_revisions = []
                for revision in history.revisions:
                    portable_revisions.append(
                        {
                            **revision.model_dump(mode="json"),
                            "id": str(revision_id_map[revision.id]),
                            "parent_revision_id": (
                                str(revision_id_map[revision.parent_revision_id])
                                if revision.parent_revision_id is not None
                                else None
                            ),
                            "operations": canonicalize_sanitation_operations(
                                revision.operations
                            ),
                        }
                    )
                portable_head = {
                    **history.head.model_dump(mode="json"),
                    "active_revision_id": str(
                        revision_id_map[history.head.active_revision_id]
                    ),
                    "operations": canonicalize_sanitation_operations(
                        history.head.operations
                    ),
                }
                recipe_template_histories.append(
                    {
                        "recipe_id": str(new_recipe_id),
                        "head": portable_head,
                        "revisions": portable_revisions,
                    }
                )
                recipe_template_candidates.append(
                    {
                        "name": history.head.name,
                        "operations": portable_head["operations"],
                        "history_recipe_id": str(new_recipe_id),
                        "requires_explicit_binding": True,
                    }
                )
        else:
            for index, legacy_recipe in enumerate(bundle.sanitation_recipes, start=1):
                if not isinstance(legacy_recipe, dict):
                    raise SanitationContractError("历史整理方法必须是对象")
                name = str(legacy_recipe.get("name") or f"导入的整理方法 {index}").strip()
                if not name:
                    raise SanitationContractError("历史整理方法名称不能为空")
                operations = canonicalize_sanitation_operations(
                    legacy_recipe.get("operations")
                )
                recipe_id = uuid4()
                revision_id = uuid4()
                input_contract = sanitation_fingerprint_contract(None)
                output_contract = sanitation_fingerprint_contract(None)
                recipe_template_histories.append(
                    {
                        "recipe_id": str(recipe_id),
                        "head": {
                            "name": name[:160],
                            "status": "needs_attention",
                            "operations": operations,
                            "input_fingerprint": None,
                            "output_fingerprint": None,
                            "active_revision_id": str(revision_id),
                            "created_at": imported_at.isoformat(),
                            "updated_at": imported_at.isoformat(),
                        },
                        "revisions": [
                            {
                                "id": str(revision_id),
                                "revision_number": 1,
                                "parent_revision_id": None,
                                "state": "candidate",
                                "operations": operations,
                                "input_contract": input_contract,
                                "output_contract": output_contract,
                                "actor_source": "imported",
                                "reason": "从旧版项目备份导入，等待绑定到具体数据",
                                "source_correction_id": None,
                                "created_at": imported_at.isoformat(),
                            }
                        ],
                    }
                )
                recipe_template_candidates.append(
                    {
                        "name": name[:160],
                        "operations": operations,
                        "history_recipe_id": str(recipe_id),
                        "requires_explicit_binding": True,
                    }
                )
    except (KeyError, SanitationContractError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="项目备份中的整理方法不兼容，未执行导入",
        ) from exc

    project = Project(
        name=bundle.project.name,
        description=bundle.project.description,
        status="active",
        extra_data={
            "imported_bundle_version": bundle.version,
            "recipe_template_candidates": recipe_template_candidates,
            "recipe_template_histories": recipe_template_histories,
            "golden_scenarios": golden_scenarios,
            "analysis_playbooks": [
                playbook.model_dump(mode="json") for playbook in bundle.analysis_playbooks
            ],
            "trusted_references": [
                reference.model_dump(mode="json") for reference in bundle.trusted_references
            ],
        },
    )
    db.add(project)
    await db.flush()
    imported_standing_analyses = [
        StandingAnalysisResponse.model_validate(
            item.model_copy(
                update={
                    "id": standing_analysis_id(project.id, item.playbook_id),
                    "project_id": project.id,
                    "state": "paused",
                    "baseline": None,
                    "in_flight": None,
                    "last_evaluated_token": None,
                    "last_run_id": None,
                    "last_brief_artifact_id": None,
                    "attention_reason": None,
                }
            ).model_dump()
        )
        for item in bundle.standing_analyses
    ]
    save_standing_analyses(project, imported_standing_analyses)
    if bundle.version == 1:
        for payload in bundle.semantic_entries:
            entry = SemanticEntry(project_id=project.id, **payload.model_dump())
            db.add(entry)
            await db.flush()
            await append_semantic_revision(
                db,
                entry,
                mutation_kind="imported",
                actor_source="imported",
                reason="从旧版项目备份导入业务定义",
            )
    else:
        revision_id_map = {
            revision.id: uuid4()
            for history in bundle.semantic_histories
            for revision in history.revisions
        }
        entry_id_map = {history.entry_id: uuid4() for history in bundle.semantic_histories}
        for history in bundle.semantic_histories:
            head = history.head
            entry = SemanticEntry(
                id=entry_id_map[history.entry_id],
                project_id=project.id,
                key=head.key,
                value=head.value,
                entry_type=head.entry_type,
                state=head.state,
                confidence=head.confidence,
                definition=(head.definition.model_dump(mode="json") if head.definition else None),
                validity=head.validity,
                execution_state=head.execution_state,
                execution_details=head.execution_details,
                evidence=head.evidence,
                source=head.source,
                is_active=head.is_active,
                revision_number=head.revision_number,
                active_revision_id=revision_id_map[head.active_revision_id],
                created_at=head.created_at,
                updated_at=head.updated_at,
            )
            db.add(entry)
        await db.flush()
        for history in bundle.semantic_histories:
            for revision in history.revisions:
                db.add(
                    SemanticEntryRevision(
                        id=revision_id_map[revision.id],
                        project_id=project.id,
                        semantic_entry_id=entry_id_map[history.entry_id],
                        revision_number=revision.revision_number,
                        parent_revision_id=(
                            revision_id_map[revision.parent_revision_id]
                            if revision.parent_revision_id is not None
                            else None
                        ),
                        restored_from_revision_id=(
                            revision_id_map[revision.restored_from_revision_id]
                            if revision.restored_from_revision_id is not None
                            else None
                        ),
                        mutation_kind=revision.mutation_kind,
                        actor_source=revision.actor_source,
                        reason=revision.reason,
                        source_correction_id=revision.source_correction_id,
                        snapshot=revision.snapshot.model_dump(mode="json"),
                        created_at=revision.created_at,
                    )
                )
        await db.flush()
    await db.commit()
    await db.refresh(project)
    project_dir = settings.WORKSPACE_ROOT / str(project.id)
    (project_dir / "sources").mkdir(parents=True, exist_ok=True)
    return APIResponse.ok(
        data=ProjectResponse.model_validate(project),
        message="项目知识、清洗模板、可复用分析、持续关注定义、历史依据和已确认检查已导入",
    )
