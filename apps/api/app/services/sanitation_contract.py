"""Versioned, deterministic contract for persisted sanitation recipes.

Recipes are data, not code.  This module intentionally exposes a small whitelist of
operations implemented by :mod:`app.services.data_preflight`; arbitrary expressions,
SQL, or Python are never accepted as recipe fields.
"""

from __future__ import annotations

import math
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

SANITATION_CONTRACT_VERSION = 1

EXECUTABLE_SANITATION_OPERATIONS = frozenset(
    {
        "select_sheet",
        "select_header",
        "normalize_column_names",
        "drop_empty",
        "exclude_summary_rows",
        "drop_exact_duplicates",
        "trim_text",
        "normalize_currency",
        "normalize_datetime",
        "fill_missing",
    }
)

VISUAL_SANITATION_OPERATIONS = frozenset(
    {
        "drop_exact_duplicates",
        "trim_text",
        "normalize_currency",
        "normalize_datetime",
        "fill_missing",
    }
)

# These records explain where a recipe came from.  They are validated and retained in
# storage, but must never reach the sanitation executor.
SANITATION_PROVENANCE_OPERATIONS = frozenset(
    {
        "replay_prior_recipe",
        "replay_imported_recipe",
        "reapply_recipe",
    }
)


class SanitationContractError(ValueError):
    """Raised when an untrusted or incompatible recipe cannot be replayed safely."""


class _Operation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    operation: str
    contract_version: Literal[1] = SANITATION_CONTRACT_VERSION
    replayed: bool = False


class _NamedOperation(_Operation):
    @staticmethod
    def _require_visible_name(value: str, label: str) -> str:
        if not value.strip():
            raise ValueError(f"{label} cannot be blank")
        return value


class SelectSheetOperation(_NamedOperation):
    operation: Literal["select_sheet"]
    sheet: str = Field(min_length=1, max_length=255)

    @field_validator("sheet")
    @classmethod
    def validate_sheet(cls, value: str) -> str:
        return cls._require_visible_name(value, "sheet")


class SelectHeaderOperation(_Operation):
    operation: Literal["select_header"]
    row: int = Field(ge=1, le=1_000_000)


class NormalizeColumnNamesOperation(_Operation):
    operation: Literal["normalize_column_names"]
    columns: list[str] = Field(min_length=1, max_length=100_000)

    @field_validator("columns")
    @classmethod
    def validate_columns(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("columns cannot contain blank names")
        if len(values) != len(set(values)):
            raise ValueError("columns must be unique after normalization")
        return values


class DropEmptyOperation(_Operation):
    operation: Literal["drop_empty"]
    rows: int = Field(ge=0)
    columns: int = Field(ge=0)


class ExcludeSummaryRowsOperation(_Operation):
    operation: Literal["exclude_summary_rows"]
    count: int = Field(ge=0)


class DropExactDuplicatesOperation(_Operation):
    operation: Literal["drop_exact_duplicates"]
    # A user-authored preview does not know the resulting count yet. The executor
    # replaces this default with the observed count before a revision is persisted.
    count: int = Field(default=0, ge=0)


class _ColumnOperation(_NamedOperation):
    column: str = Field(min_length=1, max_length=10_000)

    @field_validator("column")
    @classmethod
    def validate_column(cls, value: str) -> str:
        return cls._require_visible_name(value, "column")


class TrimTextOperation(_ColumnOperation):
    operation: Literal["trim_text"]
    error_policy: Literal["preserve_original"] = "preserve_original"


class NormalizeCurrencyOperation(_ColumnOperation):
    operation: Literal["normalize_currency"]
    error_policy: Literal["set_null"] = "set_null"


class NormalizeDatetimeOperation(_ColumnOperation):
    operation: Literal["normalize_datetime"]
    error_policy: Literal["set_null"] = "set_null"


class FillMissingOperation(_ColumnOperation):
    operation: Literal["fill_missing"]
    value: str | int | float | bool

    @field_validator("value")
    @classmethod
    def validate_bounded_json_scalar(cls, value: str | int | float | bool):
        if isinstance(value, str):
            if len(value) > 1000:
                raise ValueError("fill value cannot exceed 1000 characters")
            return value
        if isinstance(value, bool):
            return value
        if abs(value) > 1_000_000_000_000_000:
            raise ValueError("numeric fill value is outside the supported range")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("numeric fill value must be finite")
        return value


class ReplayPriorRecipeOperation(_Operation):
    operation: Literal["replay_prior_recipe"]
    source_id: str = Field(min_length=1, max_length=64)
    recipe_id: str = Field(min_length=1, max_length=64)

    @field_validator("source_id", "recipe_id")
    @classmethod
    def validate_ids(cls, value: str) -> str:
        try:
            return str(UUID(value))
        except ValueError as exc:
            raise ValueError("recipe provenance ids must be UUIDs") from exc


class ReplayImportedRecipeOperation(_NamedOperation):
    operation: Literal["replay_imported_recipe"]
    template: str = Field(min_length=1, max_length=512)

    @field_validator("template")
    @classmethod
    def validate_template(cls, value: str) -> str:
        return cls._require_visible_name(value, "template")


class ReapplyRecipeOperation(_Operation):
    operation: Literal["reapply_recipe"]
    recipe_id: str = Field(min_length=1, max_length=64)

    @field_validator("recipe_id")
    @classmethod
    def validate_recipe_id(cls, value: str) -> str:
        try:
            return str(UUID(value))
        except ValueError as exc:
            raise ValueError("recipe_id must be a UUID") from exc


_OPERATION_MODELS: dict[str, type[_Operation]] = {
    "select_sheet": SelectSheetOperation,
    "select_header": SelectHeaderOperation,
    "normalize_column_names": NormalizeColumnNamesOperation,
    "drop_empty": DropEmptyOperation,
    "exclude_summary_rows": ExcludeSummaryRowsOperation,
    "drop_exact_duplicates": DropExactDuplicatesOperation,
    "trim_text": TrimTextOperation,
    "normalize_currency": NormalizeCurrencyOperation,
    "normalize_datetime": NormalizeDatetimeOperation,
    "fill_missing": FillMissingOperation,
    "replay_prior_recipe": ReplayPriorRecipeOperation,
    "replay_imported_recipe": ReplayImportedRecipeOperation,
    "reapply_recipe": ReapplyRecipeOperation,
}

_LEGACY_ERROR_POLICIES = {
    "trim_text": "preserve_original",
    "normalize_currency": "set_null",
    "normalize_datetime": "set_null",
}


def _validation_message(error: ValidationError) -> str:
    first = error.errors(include_url=False)[0]
    location = ".".join(str(part) for part in first.get("loc") or ()) or "operation"
    return f"{location}: {first.get('msg', 'invalid value')}"


def canonicalize_sanitation_operations(
    operations: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Validate and upgrade legacy recipe dictionaries to the current v1 shape.

    Legacy operations produced before the contract existed omitted ``contract_version``
    and field error policies.  Only those two known omissions are upgraded.  Unknown
    operations, future versions, wrong types, and extra fields fail closed.
    """

    if operations is None:
        return []
    if not isinstance(operations, list):
        raise SanitationContractError("整理配方必须是步骤列表")

    canonical: list[dict[str, Any]] = []
    for index, raw_operation in enumerate(operations):
        if not isinstance(raw_operation, dict):
            raise SanitationContractError(f"整理步骤 {index + 1} 必须是对象")
        operation = raw_operation.get("operation")
        if not isinstance(operation, str) or not operation:
            raise SanitationContractError(f"整理步骤 {index + 1} 缺少有效 operation")
        model = _OPERATION_MODELS.get(operation)
        if model is None:
            raise SanitationContractError(f"整理步骤 {index + 1} 使用了未知操作 {operation}")

        payload = dict(raw_operation)
        payload.setdefault("contract_version", SANITATION_CONTRACT_VERSION)
        legacy_error_policy = _LEGACY_ERROR_POLICIES.get(operation)
        if legacy_error_policy is not None:
            payload.setdefault("error_policy", legacy_error_policy)
        try:
            parsed = model.model_validate(payload)
        except ValidationError as exc:
            raise SanitationContractError(
                f"整理步骤 {index + 1}（{operation}）不符合合同：{_validation_message(exc)}"
            ) from exc

        serialized = parsed.model_dump(mode="json")
        if not serialized.get("replayed"):
            serialized.pop("replayed", None)
        canonical.append(serialized)
    return canonical


def executable_sanitation_operations(
    operations: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Return validated executable steps while excluding provenance records."""

    return [
        operation
        for operation in canonicalize_sanitation_operations(operations)
        if operation["operation"] in EXECUTABLE_SANITATION_OPERATIONS
    ]


def canonicalize_visual_sanitation_operations(
    operations: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Validate the deliberately small operation set exposed by the visual editor."""

    canonical = canonicalize_sanitation_operations(operations)
    if len(canonical) > 100:
        raise SanitationContractError("一次最多可以预览 100 个整理操作")
    for index, operation in enumerate(canonical):
        operation_name = str(operation.get("operation") or "")
        if operation_name not in VISUAL_SANITATION_OPERATIONS:
            raise SanitationContractError(
                f"整理步骤 {index + 1}（{operation_name}）不能在可视化编辑器中执行"
            )
        if operation_name == "fill_missing":
            value = operation.get("value")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value != 0:
                raise SanitationContractError(
                    f"整理步骤 {index + 1}（fill_missing）目前只支持用数字 0 填补空值"
                )
    return canonical
