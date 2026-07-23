"""Deterministic, scope-bound semantic recommendations.

This module deliberately has no database or provider dependency.  It consumes the
already prepared profiles in :class:`ProjectRuntimeContext`, produces typed
``SemanticEntryCreate`` candidates, and optionally lets an injected enhancer
rewrite presentation text and order.  The enhancer never owns bindings, formulas,
confidence, evidence, or candidate identity.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import re
from collections import defaultdict
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Literal, TypeAlias
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, ValidationError

from app.models.workspace import (
    AggregateMetricDefinition,
    BusinessRuleMetricFormulaAction,
    BusinessRuleSourceBinding,
    DerivedMetricDefinition,
    DimensionDefinition,
    RelationshipDefinition,
    RelationshipEndpoint,
    ScopePresentationDefinition,
    SemanticEntryCreate,
    SemanticRecommendationScope,
)
from app.services.result_filters import canonical_data_type, stable_schema_signature
from app.services.semantic_field_roles import (
    SEMANTIC_ROLE_INFERENCE_VERSION,
    infer_semantic_field_role,
    suggested_metric_operation,
)

if TYPE_CHECKING:
    from app.services.project_context import ProjectRuntimeContext

Locale: TypeAlias = Literal["zh", "en"]
GeneratedBy: TypeAlias = Literal["ai", "preflight"]
RecommendationMode: TypeAlias = Literal["full", "presentation", "structure", "relationships"]

_MAX_SCOPES = 20
_MAX_TABLES_PER_SCOPE = 100
_MAX_COLUMNS_PER_TABLE = 240
_MAX_PUBLIC_RECOMMENDATIONS = 50
_MAX_QUESTIONS = 5
_MAX_INVENTORY_RECOMMENDATIONS = _MAX_COLUMNS_PER_TABLE + 2

_ZH_COLUMN_NAMES = {
    "amount": "金额",
    "category": "类别",
    "channel": "渠道",
    "cost": "成本",
    "costamount": "成本",
    "customerid": "客户编号",
    "customername": "客户名称",
    "date": "日期",
    "department": "部门",
    "discount": "折扣",
    "discountamount": "优惠金额",
    "gmv": "成交金额",
    "grossamount": "原始金额",
    "grossprofit": "毛利",
    "isobsolete": "是否已停用",
    "isskucore": "是否核心商品",
    "netamount": "净额",
    "orderdate": "下单日期",
    "orderid": "订单编号",
    "order": "订单",
    "price": "价格",
    "productid": "商品编号",
    "productname": "商品名称",
    "profit": "利润",
    "product": "商品",
    "publishedat": "发布时间",
    "quantity": "销量",
    "qty": "销量",
    "region": "地区",
    "refundamount": "退款金额",
    "revenue": "收入",
    "sales": "销售额",
    "salesamount": "销售额",
    "shopid": "门店编号",
    "storeid": "门店编号",
    "totalamount": "总金额",
    "unitcost": "单位成本",
    "unitprice": "单价",
}

_ZH_TABLE_TOPICS = {
    "customer": "客户",
    "customers": "客户",
    "cust": "客户",
    "items": "商品",
    "order": "订单",
    "orders": "订单",
    "product": "商品",
    "prd": "商品",
    "sku": "商品",
    "sales": "销售",
    "region": "地区",
    "center": "中心",
    "dict": "字典",
}

_TECHNICAL_TABLE_TOKENS = {
    "d",
    "dim",
    "f",
    "fact",
    "info",
    "catalog",
    "new",
    "tbl",
    "table",
    "v",
    "view",
}

_ZH_IDENTIFIER_TOKENS = {
    "actual": "实际",
    "address": "地址",
    "area": "区域",
    "category": "类别",
    "channel": "渠道",
    "code": "编码",
    "cost": "成本",
    "customer": "客户",
    "date": "日期",
    "datetime": "时间",
    "department": "部门",
    "dept": "部门",
    "flag": "标记",
    "id": "编号",
    "is": "是否",
    "label": "标签",
    "line": "线",
    "listing": "上架",
    "name": "名称",
    "no": "编号",
    "number": "编号",
    "order": "订单",
    "other": "其他",
    "price": "价格",
    "product": "商品",
    "quantity": "数量",
    "qty": "数量",
    "region": "地区",
    "sales": "销售",
    "rep": "代表",
    "shop": "门店",
    "sku": "SKU",
    "status": "状态",
    "store": "门店",
    "time": "时间",
    "total": "合计",
    "type": "类型",
    "unit": "单位",
}

_ZH_IDENTIFIER_PHRASES = {
    ("account", "rep"): "客户代表",
    ("published", "at"): "发布时间",
    ("product", "line"): "产品线",
}


class SemanticRecommendationError(ValueError):
    """The requested source/table scope cannot be proven from the context."""


class SemanticRecommendationEnhancement(BaseModel):
    """The complete set of fields an optional model may supply for one candidate."""

    candidate_id: str = Field(..., min_length=1, max_length=160)
    business_name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, min_length=1, max_length=1000)
    example_questions: list[str] | None = Field(default=None, max_length=_MAX_QUESTIONS)
    synonyms: list[str] | None = Field(default=None, max_length=20)

    model_config = {"extra": "forbid"}


EnhancementPayload: TypeAlias = Sequence[SemanticRecommendationEnhancement | Mapping[str, Any]]
SemanticRecommendationEnhancer: TypeAlias = Callable[
    [list[dict[str, Any]]],
    EnhancementPayload | Awaitable[EnhancementPayload],
]


@dataclass(frozen=True, slots=True)
class SemanticRecommendationBatch:
    """A caller-owned batch ready to persist as candidate semantic entries."""

    batch_id: UUID
    generated_by: GeneratedBy
    items: list[SemanticEntryCreate]


@dataclass(frozen=True, slots=True)
class _ScopedTable:
    source_id: str
    source_name: str
    source_kind: Literal["file", "connection"]
    logical_name: str
    table_name: str
    source_description: str | None
    table_description: str | None
    source_business_name: str | None
    table_business_name: str | None
    table_profiled: bool
    source_table_names: tuple[str, ...]
    columns: tuple[dict[str, Any], ...]
    roles: tuple[dict[str, Any], ...]
    grain: tuple[dict[str, Any], ...]
    schema_signature: str


@dataclass(frozen=True, slots=True)
class _Draft:
    entry_type: Literal["metric", "dimension", "relationship", "scope_presentation"]
    definition: (
        AggregateMetricDefinition
        | DerivedMetricDefinition
        | DimensionDefinition
        | RelationshipDefinition
        | ScopePresentationDefinition
    )
    confidence: float
    evidence: list[dict[str, Any]]
    rank: int


def _normalized_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", str(value or "").casefold())


def _human_column_name(column: str, locale: Locale) -> str:
    normalized = _normalized_name(column)
    if locale == "zh" and normalized in _ZH_COLUMN_NAMES:
        return _ZH_COLUMN_NAMES[normalized]
    rendered = re.sub(r"[_\-.]+", " ", column).strip()
    if not rendered:
        return column
    if locale == "en" and not re.search(r"[\u4e00-\u9fff]", rendered):
        return rendered.title()
    return rendered


def _identifier_tokens(value: str) -> list[str]:
    """Split a physical identifier without pretending unknown abbreviations have meaning."""

    expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    return [
        token.casefold() for token in re.split(r"[^a-zA-Z0-9\u4e00-\u9fff]+", expanded) if token
    ]


def _readable_zh_identifier(
    value: str,
    *,
    ignored_tokens: set[str] | None = None,
) -> str:
    """Return a readable label while leaving unknown abbreviations visibly unresolved."""

    tokens = [
        token
        for token in _identifier_tokens(value)
        if not ignored_tokens or token not in ignored_tokens
    ]
    rendered: list[str] = []
    index = 0
    while index < len(tokens):
        phrase = tuple(tokens[index : index + 2])
        if len(phrase) == 2 and phrase in _ZH_IDENTIFIER_PHRASES:
            rendered.append(_ZH_IDENTIFIER_PHRASES[phrase])
            index += 2
            continue
        token = tokens[index]
        rendered.append(
            token
            if re.search(r"[\u4e00-\u9fff]", token)
            else _ZH_IDENTIFIER_TOKENS.get(token, token.upper())
        )
        index += 1
    return " ".join(rendered).strip()


def _field_presentation_name(
    table: _ScopedTable,
    column: str,
    locale: Locale,
) -> tuple[str, bool]:
    if locale == "en":
        return _human_column_name(column, locale), True
    normalized = _normalized_name(column)
    if normalized == "publishedat" and any(
        token in {"product", "prd", "sku", "goods", "item"}
        for token in _technical_tokens(table.table_name)
    ):
        return "发布时间", True
    translated = _ZH_COLUMN_NAMES.get(normalized)
    if translated:
        return translated, True
    rendered = re.sub(r"[_\-.]+", " ", column).strip()
    if re.search(r"[\u4e00-\u9fff]", rendered):
        return rendered, True
    # Unknown abbreviations stay unresolved, but the default surface still gets
    # a readable display label. The physical identifier remains in the binding
    # and synonyms for matching; it is not presented as a business definition.
    return _readable_zh_identifier(column) or "名称待确认", False


def _field_synonyms(column: str, business_name: str, locale: Locale) -> list[str]:
    values = [column]
    if locale == "zh" and _normalized_name(column) == "publishedat" and business_name == "发布时间":
        values.extend(["表格时间", "发布日期"])
    business_key = business_name.strip().casefold()
    return list(
        dict.fromkeys(
            value.strip()
            for value in values
            if value.strip() and value.strip().casefold() != business_key
        )
    )


def _normalized_synonyms(values: Sequence[Any], business_name: str) -> list[str]:
    business_key = business_name.strip().casefold()
    seen: set[str] = set()
    normalized: list[str] = []
    for raw in values:
        value = str(raw).strip()
        marker = value.casefold()
        if not value or marker == business_key or marker in seen:
            continue
        seen.add(marker)
        normalized.append(value)
    return normalized[:20]


def _technical_tokens(value: str) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9\u4e00-\u9fff]+", value.casefold()) if token]


def _zh_table_presentation(table_name: str) -> tuple[str, bool]:
    tokens = _technical_tokens(table_name)
    year = next((token for token in tokens if re.fullmatch(r"(?:19|20)\d{2}", token)), None)
    topics: list[str] = []
    unknown: list[str] = []
    for token in tokens:
        if token == year or token in _TECHNICAL_TABLE_TOKENS:
            continue
        translated = _ZH_TABLE_TOPICS.get(token)
        if translated and translated not in topics:
            topics.append(translated)
        elif not translated:
            unknown.append(token)
    if topics:
        topic = "与".join(topics[:2])
        label = f"{year} 年{topic}信息" if year else f"{topic}信息"
        return label, not unknown
    readable = _readable_zh_identifier(
        table_name,
        ignored_tokens=_TECHNICAL_TABLE_TOKENS | ({year} if year else set()),
    )
    if year and readable:
        return f"{year} 年{readable}数据", False
    if readable:
        return f"{readable}数据", False
    return "数据表", False


def _zh_source_presentation(table_names: Sequence[str], source_name: str) -> tuple[str, bool]:
    topics: list[str] = []
    for table_name in table_names:
        for token in _technical_tokens(table_name):
            translated = _ZH_TABLE_TOPICS.get(token)
            if translated and translated not in topics:
                topics.append(translated)
    if topics:
        topic = "与".join(topics[:2])
        suffix = "数据仓库" if len(table_names) > 1 else "数据源"
        return f"{topic}{suffix}", True
    readable = re.sub(r"\.[^.]+$", "", source_name).strip()
    if readable and re.search(r"[\u4e00-\u9fff]", readable):
        return readable, True
    fallback = _readable_zh_identifier(
        re.sub(r"\.[^.]+$", "", source_name),
        ignored_tokens=_TECHNICAL_TABLE_TOKENS | {"db", "database"},
    )
    return (f"{fallback}数据源" if fallback else "数据源"), False


def _relationship_table_name(
    table: _ScopedTable,
    *,
    locale: Locale,
    fallback: str,
) -> str:
    if table.table_business_name:
        return table.table_business_name
    if locale == "zh":
        name, resolved = _zh_table_presentation(table.table_name.rsplit(".", 1)[-1])
        return name if resolved else fallback
    return fallback


def _schema_signature(columns: Sequence[Mapping[str, Any]]) -> str:
    """Match the stable execution binding signature used by result_filters.py."""

    return stable_schema_signature(columns)


def _stable_canonical_type(
    column: Mapping[str, Any],
) -> Literal["boolean", "number", "datetime", "text"] | None:
    inferred = canonical_data_type(
        column.get("type") or column.get("dtype") or column.get("data_type") or "unknown"
    )
    return inferred if inferred != "unknown" else None


def _column_role(column: Mapping[str, Any], grain_columns: set[str]) -> tuple[str, bool]:
    explicit = str(column.get("role") or "").casefold()
    name = str(column.get("name") or column.get("column") or "")
    normalized = _normalized_name(name)
    role_profile_is_current = column.get("_role_inference_current") is True
    if role_profile_is_current and explicit in {
        "measure",
        "time",
        "identifier",
        "dimension",
        "category",
    }:
        explicit_role = "dimension" if explicit == "category" else explicit
        canonical = canonical_data_type(
            column.get("type")
            or column.get("dtype")
            or column.get("declared_type")
            or column.get("data_type")
            or "unknown"
        )
        # Historical profiles could label a text column as a measure from a
        # substring match (for example, ``presales_owner`` containing ``sales``).
        # A measure requires numeric type evidence, so fall back to conservative
        # inference instead of preserving an impossible explicit role.
        if explicit_role != "measure" or canonical == "number":
            return explicit_role, True
    raw_type = (
        column.get("type")
        or column.get("dtype")
        or column.get("declared_type")
        or column.get("data_type")
    )
    canonical = canonical_data_type(raw_type or "unknown")
    return (
        infer_semantic_field_role(
            name,
            is_numeric=canonical == "number",
            is_datetime=canonical == "datetime",
            is_grain=normalized in grain_columns,
        ),
        False,
    )


def _binding(table: _ScopedTable, column: Mapping[str, Any]) -> BusinessRuleSourceBinding:
    canonical = _stable_canonical_type(column)
    if canonical is None:
        raise SemanticRecommendationError("字段类型不足以创建可执行绑定")
    return BusinessRuleSourceBinding(
        source_logical_name=table.logical_name,
        source_kind=table.source_kind,
        table_or_view=table.table_name,
        action_column=str(column.get("name") or column.get("column") or ""),
        canonical_type=canonical,
        schema_signature=table.schema_signature,
    )


def _bounded_profile_evidence(column: Mapping[str, Any]) -> dict[str, Any]:
    allowed = (
        "role",
        "status",
        "non_null",
        "missing",
        "unique",
        "sample_unique",
        "uniqueness",
        "sampled",
        "value_visibility",
        "range",
        "distribution",
    )
    return {key: column[key] for key in allowed if column.get(key) is not None}


def _base_evidence(
    table: _ScopedTable,
    *,
    batch_id: UUID,
    kind: str,
    columns: Sequence[str],
) -> dict[str, Any]:
    bounded_fields: list[dict[str, Any]] = []
    for column in table.columns[:80]:
        name = str(column.get("name") or "").strip()
        if not name:
            continue
        canonical = _stable_canonical_type(column)
        role = str(column.get("role") or "").strip() or infer_semantic_field_role(
            name,
            is_numeric=canonical == "number",
            is_datetime=canonical == "datetime",
            is_grain=False,
        )
        bounded_fields.append(
            {
                "binding": name,
                "type": canonical or "unknown",
                "role": role,
                "profile": {
                    key: column[key]
                    for key in (
                        "non_null",
                        "missing",
                        "unique",
                        "uniqueness",
                        "value_visibility",
                        "range",
                    )
                    if column.get(key) is not None
                },
            }
        )
    return {
        "kind": kind,
        "batch_id": str(batch_id),
        "generated_by": "deterministic_profile",
        "source_id": table.source_id,
        "source": table.source_name,
        "source_logical_name": table.logical_name,
        "table_or_view": table.table_name,
        "columns": list(columns),
        "schema_signature": table.schema_signature,
        "requires_validation": True,
        "recommendation_context": {
            "source_technical_name": table.source_name,
            "source_logical_name": table.logical_name,
            "source_kind": table.source_kind,
            "source_description": table.source_description,
            "source_relation_names": list(table.source_table_names[:100]),
            "table_technical_name": table.table_name,
            "table_description": table.table_description,
            "same_table_fields": bounded_fields,
        },
    }


def _table_name_candidates(table: Mapping[str, Any]) -> tuple[str, ...]:
    name = str(table.get("name") or "").strip()
    schema = str(table.get("schema") or "").strip()
    return tuple(item for item in (name, f"{schema}.{name}" if schema and name else "") if item)


def _canonical_table_name(table: Mapping[str, Any]) -> str:
    """Return the durable semantic identity for one catalog relation."""

    name = str(table.get("name") or "").strip()
    schema = str(table.get("schema") or "").strip()
    return f"{schema}.{name}" if schema and name else name


def _table_reference_matches(
    reference: Any,
    table: Mapping[str, Any],
    all_tables: Sequence[Mapping[str, Any]],
) -> bool:
    """Match a role/grain reference without leaking across same-name schemas."""

    requested = str(reference or "").strip()
    if not requested:
        return False
    canonical = _canonical_table_name(table)
    if requested.casefold() == canonical.casefold():
        return True
    if "." in requested:
        return False
    bare = str(table.get("name") or "").strip()
    if requested.casefold() != bare.casefold():
        return False
    same_name = [
        item
        for item in all_tables
        if str(item.get("name") or "").strip().casefold() == bare.casefold()
    ]
    return len(same_name) == 1


def _resolve_requested_table(
    requested: str,
    tables: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    matches = [
        table
        for table in tables
        if requested.casefold() in {name.casefold() for name in _table_name_candidates(table)}
    ]
    return matches[0] if len(matches) == 1 else None


def _profile_tables(profile: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Merge the full lightweight relation index with bounded deep portraits."""

    relation_index = (profile.get("preanalysis") or {}).get("relation_index") or {}
    indexed = [
        dict(item)
        for item in relation_index.get("relations") or []
        if isinstance(item, Mapping) and str(item.get("name") or "").strip()
    ]
    deep = [
        dict(item)
        for item in profile.get("tables") or []
        if isinstance(item, Mapping) and str(item.get("name") or "").strip()
    ]

    def identity(table: Mapping[str, Any]) -> tuple[str, str]:
        return (
            str(table.get("schema") or "").strip().casefold(),
            str(table.get("name") or "").strip().casefold(),
        )

    merged: dict[tuple[str, str], dict[str, Any]] = {}
    order: list[tuple[str, str]] = []
    for item in [*indexed, *deep]:
        key = identity(item)
        if key not in merged:
            order.append(key)
            merged[key] = {
                **item,
                "description": item.get("description") or item.get("comment"),
                "columns": list(item.get("columns") or []),
                "profile_status": "catalog_only",
            }
            continue
        previous = merged[key]
        merged[key] = {
            **previous,
            **item,
            "description": (
                item.get("description") or item.get("comment") or previous.get("description")
            ),
            "columns": list(item.get("columns") or previous.get("columns") or []),
            "profile_status": (
                "profiled" if item.get("columns") or previous.get("columns") else "catalog_only"
            ),
        }
    return [merged[key] for key in order]


def _scope_value(scope: Any, field_name: str, default: Any = None) -> Any:
    if isinstance(scope, Mapping):
        return scope.get(field_name, default)
    return getattr(scope, field_name, default)


def _scoped_tables(
    context: ProjectRuntimeContext,
    scopes: Sequence[SemanticRecommendationScope | Mapping[str, Any]],
) -> list[_ScopedTable]:
    if not scopes:
        raise SemanticRecommendationError("至少选择一个数据源后才能生成推荐")
    if len(scopes) > _MAX_SCOPES:
        raise SemanticRecommendationError(f"一次最多选择 {_MAX_SCOPES} 个数据源")

    sources = {
        str(source.get("id") or ""): source
        for source in context.sources
        if isinstance(source, Mapping) and source.get("id")
    }
    seen_sources: set[str] = set()
    resolved: list[_ScopedTable] = []
    for raw_scope in scopes:
        source_id = str(_scope_value(raw_scope, "source_id") or "").strip()
        if not source_id or source_id in seen_sources:
            raise SemanticRecommendationError("推荐范围中的数据源必须明确且不能重复")
        seen_sources.add(source_id)
        source = sources.get(source_id)
        if source is None:
            raise SemanticRecommendationError(f"推荐范围包含未知或尚未就绪的数据源：{source_id}")
        profile = source.get("profile")
        if not isinstance(profile, Mapping) or not profile:
            raise SemanticRecommendationError(
                f"数据源“{source.get('name') or source_id}”尚无可用画像"
            )
        if (
            profile.get("is_current") is False
            or profile.get("activation_state") == "pending_confirmation"
        ):
            raise SemanticRecommendationError(f"数据源“{source.get('name') or source_id}”尚未启用")

        source_kind = str(source.get("kind") or "")
        if source_kind not in {"file", "connection"}:
            raise SemanticRecommendationError(
                f"数据源“{source.get('name') or source_id}”类型不受支持"
            )
        source_name = str(source.get("name") or source_id)
        logical_name = str(profile.get("logical_name") or source_name).strip()
        requested_tables = [
            str(item).strip()
            for item in (_scope_value(raw_scope, "tables", []) or [])
            if str(item).strip()
        ]
        if len(requested_tables) > _MAX_TABLES_PER_SCOPE:
            raise SemanticRecommendationError(
                f"数据源“{source_name}”一次最多选择 {_MAX_TABLES_PER_SCOPE} 张表"
            )
        if len({item.casefold() for item in requested_tables}) != len(requested_tables):
            raise SemanticRecommendationError(f"数据源“{source_name}”的表范围不能重复")

        preanalysis = profile.get("preanalysis") or {}
        role_profile_is_current = (
            preanalysis.get("semantic_role_inference_version") == SEMANTIC_ROLE_INFERENCE_VERSION
        )
        all_roles = [
            {**dict(item), "_role_inference_current": role_profile_is_current}
            for item in preanalysis.get("candidate_roles") or []
            if isinstance(item, Mapping)
        ]
        all_grain = [
            item
            for item in (
                (profile.get("schema") or {}).get("candidate_grain")
                or preanalysis.get("candidate_grain")
                or []
            )
            if isinstance(item, Mapping)
        ]

        if source_kind == "file":
            # Stable file bindings use the maintained logical role, never the
            # physical DuckDB view name that changes with one attachment.
            table_name = logical_name
            if requested_tables and any(
                requested.casefold() != table_name.casefold() for requested in requested_tables
            ):
                raise SemanticRecommendationError(
                    f"文件数据源“{source_name}”不包含所选表：{'、'.join(requested_tables)}"
                )
            columns = [
                dict(item)
                for item in (profile.get("schema") or {}).get("columns") or []
                if isinstance(item, Mapping) and item.get("name")
            ][:_MAX_COLUMNS_PER_TABLE]
            if not columns:
                raise SemanticRecommendationError(f"数据源“{source_name}”没有可推荐的字段画像")
            resolved.append(
                _make_scoped_table(
                    source_id=source_id,
                    source_name=source_name,
                    source_kind="file",
                    logical_name=logical_name,
                    table_name=table_name,
                    source_description=str(
                        profile.get("description") or profile.get("summary") or ""
                    ).strip()
                    or None,
                    table_description=str(profile.get("table_description") or "").strip() or None,
                    source_business_name=str(profile.get("business_name") or "").strip() or None,
                    table_business_name=str(profile.get("table_business_name") or "").strip()
                    or None,
                    table_profiled=True,
                    source_table_names=[table_name],
                    columns=columns,
                    roles=all_roles,
                    grain=all_grain,
                )
            )
            continue

        profile_tables = _profile_tables(profile)
        if not requested_tables:
            raise SemanticRecommendationError(f"数据库数据源“{source_name}”必须明确选择表")
        for requested in requested_tables:
            table = _resolve_requested_table(requested, profile_tables)
            if table is None:
                raise SemanticRecommendationError(
                    f"数据库数据源“{source_name}”不包含唯一可识别的表“{requested}”"
                )
            table_name = _canonical_table_name(table)
            columns = [
                dict(item)
                for item in table.get("columns") or []
                if isinstance(item, Mapping) and item.get("name")
            ][:_MAX_COLUMNS_PER_TABLE]
            roles = [
                item
                for item in all_roles
                if _table_reference_matches(item.get("table"), table, profile_tables)
            ]
            grain = [
                item
                for item in all_grain
                if _table_reference_matches(item.get("table"), table, profile_tables)
            ]
            resolved.append(
                _make_scoped_table(
                    source_id=source_id,
                    source_name=source_name,
                    source_kind="connection",
                    logical_name=logical_name,
                    table_name=table_name,
                    source_description=str(
                        profile.get("description") or profile.get("summary") or ""
                    ).strip()
                    or None,
                    table_description=str(table.get("description") or "").strip() or None,
                    source_business_name=str(profile.get("business_name") or "").strip() or None,
                    table_business_name=str(table.get("business_name") or "").strip() or None,
                    table_profiled=bool(columns),
                    source_table_names=[
                        _canonical_table_name(item)
                        for item in profile_tables
                        if str(item.get("name") or "").strip()
                    ],
                    columns=columns,
                    roles=roles,
                    grain=grain,
                )
            )
    return resolved


def _make_scoped_table(
    *,
    source_id: str,
    source_name: str,
    source_kind: Literal["file", "connection"],
    logical_name: str,
    table_name: str,
    source_description: str | None,
    table_description: str | None,
    source_business_name: str | None,
    table_business_name: str | None,
    table_profiled: bool,
    source_table_names: Sequence[str],
    columns: Sequence[dict[str, Any]],
    roles: Sequence[Mapping[str, Any]],
    grain: Sequence[Mapping[str, Any]],
) -> _ScopedTable:
    role_lookup = {
        str(item.get("column") or "").casefold(): dict(item) for item in roles if item.get("column")
    }
    merged_columns = []
    for raw_column in columns:
        name = str(raw_column.get("name") or "")
        merged_columns.append({**raw_column, **role_lookup.get(name.casefold(), {})})
        merged_columns[-1]["name"] = name
    return _ScopedTable(
        source_id=source_id,
        source_name=source_name,
        source_kind=source_kind,
        logical_name=logical_name,
        table_name=table_name,
        source_description=source_description,
        table_description=table_description,
        source_business_name=source_business_name,
        table_business_name=table_business_name,
        table_profiled=table_profiled,
        source_table_names=tuple(source_table_names),
        columns=tuple(merged_columns),
        roles=tuple(dict(item) for item in roles),
        grain=tuple(dict(item) for item in grain),
        schema_signature=_schema_signature(columns),
    )


def _grain_columns(table: _ScopedTable) -> tuple[set[str], dict[str, Mapping[str, Any]]]:
    columns: set[str] = set()
    evidence: dict[str, Mapping[str, Any]] = {}
    for item in table.grain:
        raw_columns = [str(value) for value in item.get("columns") or [] if value]
        if not raw_columns and item.get("column"):
            raw_columns = [str(item["column"])]
        if len(raw_columns) != 1:
            continue
        normalized = _normalized_name(raw_columns[0])
        columns.add(normalized)
        evidence[normalized] = item
    return columns, evidence


def _metric_operation(column: str) -> Literal["sum", "avg"]:
    return suggested_metric_operation(column)


def _presentation_for_metric(
    table: _ScopedTable,
    column: str,
    operation: Literal["sum", "avg"],
    locale: Locale,
) -> tuple[str, str, list[str], bool]:
    name, resolved = _field_presentation_name(table, column, locale)
    if locale == "en":
        operation_name = "average" if operation == "avg" else "total"
        return (
            name,
            f"Use {column} as a candidate {operation_name} metric; confirm its business meaning before use.",
            [f"What is the {operation_name} {name}?", f"How has {name} changed over time?"],
            resolved,
        )
    operation_name = "平均值" if operation == "avg" else "合计"
    return (
        name,
        (
            f"建议按{operation_name}理解这项业务数值，采用前请核对它的业务含义。"
            if resolved
            else "名称和计算口径待核对。"
        ),
        [f"{name}是多少？", f"{name}随时间有什么变化？"] if resolved else [],
        resolved,
    )


def _presentation_for_dimension(
    table: _ScopedTable,
    column: str,
    role: Literal["time", "category", "identifier"],
    locale: Locale,
) -> tuple[str, str, list[str], bool]:
    name, resolved = _field_presentation_name(table, column, locale)
    if locale == "en":
        descriptions = {
            "time": f"Use {column} to view trends by date or period.",
            "identifier": f"Use {column} to identify and inspect individual records.",
            "category": f"Use {column} to group and compare results.",
        }
        questions = {
            "time": [
                "What were the results in 2023?",
                "How have results changed by year or month?",
            ],
            "identifier": [f"Which record corresponds to this {name}?"],
            "category": [f"How do results differ by {name}?"],
        }
        return name, descriptions[role], questions[role], resolved
    descriptions = {
        "time": f"可按“{column}”查看日期或周期趋势。",
        "identifier": f"可用“{column}”定位和核对单条记录。",
        "category": f"可按“{column}”分组比较结果。",
    }
    questions = {
        "time": ["2023年的结果是多少？", "按年或月看，结果有什么变化？"],
        "identifier": [f"哪个记录对应这个{name}？"],
        "category": [f"按{name}看，结果有什么差异？"],
    }
    if not resolved:
        return name, "名称和业务含义待核对。", [], False
    return name, descriptions[role], questions[role], True


def _scope_presentation_drafts(
    tables: Sequence[_ScopedTable],
    *,
    batch_id: UUID,
    locale: Locale,
    include_source: bool = True,
    include_tables: bool = True,
) -> list[_Draft]:
    drafts: list[_Draft] = []
    by_source: dict[str, list[_ScopedTable]] = defaultdict(list)
    for table in tables:
        by_source[table.source_id].append(table)

    for source_tables in by_source.values() if include_source else ():
        first = source_tables[0]
        if locale == "zh":
            source_name, source_resolved = _zh_source_presentation(
                first.source_table_names,
                first.source_name,
            )
            source_description = first.source_description or (
                f"包含 {len(first.source_table_names)} 张目录表的数据范围。"
            )
            source_questions = [f"{source_name}包含哪些可分析的业务数据？"]
        else:
            source_name = first.source_business_name or re.sub(r"\.[^.]+$", "", first.source_name)
            source_resolved = bool(source_name)
            source_description = first.source_description or (
                f"Data source containing {len(first.source_table_names)} cataloged tables."
            )
            source_questions = [f"What business data is available in {source_name}?"]
        source_definition = ScopePresentationDefinition(
            kind="scope_presentation",
            scope_kind="source",
            source_logical_name=first.logical_name,
            source_kind=first.source_kind,
            business_name=source_name,
            description=source_description,
            synonyms=_normalized_synonyms(
                [first.source_name, first.logical_name],
                source_name,
            ),
            example_questions=source_questions,
        )
        source_evidence = _base_evidence(
            first,
            batch_id=batch_id,
            kind="scope_presentation_profile",
            columns=[],
        )
        source_evidence["scope_kind"] = "source"
        source_evidence["requires_validation"] = False
        source_evidence["requires_human_review"] = True
        source_evidence["recommendation_context"]["source_relations"] = [
            {
                "technical_name": item.table_name,
                "description": item.table_description,
            }
            for item in source_tables[:100]
        ]
        drafts.append(
            _Draft(
                entry_type="scope_presentation",
                definition=source_definition,
                confidence=0.68 if source_resolved else 0.3,
                evidence=[source_evidence],
                rank=0,
            )
        )

    for table in tables if include_tables else ():
        if locale == "zh":
            table_name, table_resolved = _zh_table_presentation(table.table_name)
            if table.table_business_name and re.search(
                r"[\u4e00-\u9fff]", table.table_business_name
            ):
                table_name = table.table_business_name
                table_resolved = True
            table_description = table.table_description or (
                f"用于了解{table_name.rstrip('信息')}相关业务信息。"
                if table_resolved
                else "这张表的业务用途尚待确认。"
            )
            if not table.table_profiled:
                table_description = f"{table_description.rstrip('。')}；目前先根据表名和字段整理用途，确认后可继续完善。"
            table_questions = [
                f"{table_name}可以回答哪些业务问题？"
                if table_resolved
                else "这张表主要记录什么业务信息？"
            ]
        else:
            table_name = (
                table.table_business_name
                or re.sub(r"[_\-.]+", " ", table.table_name).strip().title()
            )
            table_resolved = bool(table_name)
            table_description = table.table_description or (
                f"Business records provided by {table_name}."
            )
            if not table.table_profiled:
                table_description = (
                    f"{table_description.rstrip('.')} For now, its name and fields are used "
                    "to organize the purpose; you can refine it after confirmation."
                )
            table_questions = [f"What business questions can {table_name} answer?"]
        table_definition = ScopePresentationDefinition(
            kind="scope_presentation",
            scope_kind="table",
            source_logical_name=table.logical_name,
            source_kind=table.source_kind,
            table_or_view=table.table_name,
            business_name=table_name,
            description=table_description,
            synonyms=_normalized_synonyms([table.table_name], table_name),
            example_questions=table_questions,
        )
        table_evidence = _base_evidence(
            table,
            batch_id=batch_id,
            kind="scope_presentation_profile",
            columns=[],
        )
        table_evidence["scope_kind"] = "table"
        table_evidence["requires_validation"] = False
        table_evidence["requires_human_review"] = True
        drafts.append(
            _Draft(
                entry_type="scope_presentation",
                definition=table_definition,
                confidence=0.72 if table_resolved else 0.28,
                evidence=[table_evidence],
                rank=1,
            )
        )
    return drafts


def _profile_drafts(
    table: _ScopedTable,
    *,
    batch_id: UUID,
    locale: Locale,
    metadata_only: bool = False,
) -> list[_Draft]:
    """Build field candidates without overstating the available evidence.

    ``metadata_only`` is used by the database-wide structure inventory.  It can
    identify safe grouping fields from names and declared types, but deliberately
    emits no numeric metric and no formula because no business values were read.
    """

    grain_columns, grain_evidence = _grain_columns(table)
    drafts: list[_Draft] = []
    for column in table.columns:
        column_name = str(column.get("name") or "").strip()
        if not column_name or column.get("value_visibility") == "suppressed_sensitive":
            continue
        if column.get("non_null") == 0:
            continue
        role, explicit_role = _column_role(column, grain_columns)
        canonical = _stable_canonical_type(column)
        if canonical is None:
            continue
        if role == "measure" and canonical == "number":
            if metadata_only:
                continue
            operation = _metric_operation(column_name)
            business_name, description, questions, name_resolved = _presentation_for_metric(
                table, column_name, operation, locale
            )
            definition = AggregateMetricDefinition(
                kind="aggregate_metric",
                operation=operation,
                source=_binding(table, column),
                business_name=business_name,
                description=description,
                synonyms=_field_synonyms(column_name, business_name, locale),
                example_questions=questions,
            )
            evidence = _base_evidence(
                table,
                batch_id=batch_id,
                kind="profile_metric_role",
                columns=[column_name],
            )
            evidence["profile"] = _bounded_profile_evidence(column)
            evidence["role_inference"] = "explicit" if explicit_role else "schema"
            drafts.append(
                _Draft(
                    entry_type="metric",
                    definition=definition,
                    confidence=(0.76 if explicit_role else 0.58) if name_resolved else 0.32,
                    evidence=[evidence],
                    rank=30 if explicit_role else 60,
                )
            )
            continue
        if role not in {"time", "identifier", "dimension"}:
            continue
        uniqueness = float(column.get("uniqueness") or 0)
        non_null = int(column.get("non_null") or 0)
        if role == "dimension" and non_null > 20 and uniqueness >= 0.98:
            # A nearly unique free-text field is not a useful grouping suggestion.
            continue
        dimension_role: Literal["time", "category", "identifier"] = (
            "category" if role == "dimension" else role
        )
        business_name, description, questions, name_resolved = _presentation_for_dimension(
            table, column_name, dimension_role, locale
        )
        definition = DimensionDefinition(
            kind="dimension",
            role=dimension_role,
            source=_binding(table, column),
            business_name=business_name,
            description=description,
            synonyms=_field_synonyms(column_name, business_name, locale),
            example_questions=questions,
            time_granularities=(
                ["year", "quarter", "month", "week", "day"] if dimension_role == "time" else []
            ),
        )
        evidence = _base_evidence(
            table,
            batch_id=batch_id,
            kind=("structure_dimension_role" if metadata_only else "profile_dimension_role"),
            columns=[column_name],
        )
        if metadata_only:
            evidence["generated_by"] = "deterministic_structure"
            evidence["metadata_only"] = True
            evidence["role_inference"] = "declared_type_and_name"
        else:
            evidence["profile"] = _bounded_profile_evidence(column)
            evidence["role_inference"] = "explicit" if explicit_role else "schema"
        if _normalized_name(column_name) in grain_evidence:
            evidence["grain"] = {
                key: grain_evidence[_normalized_name(column_name)].get(key)
                for key in (
                    "constraint_name",
                    "constraint_type",
                    "uniqueness",
                    "uniqueness_basis",
                    "catalog_verified",
                    "evidence_kind",
                )
                if grain_evidence[_normalized_name(column_name)].get(key) is not None
            }
        confidence = 0.78 if dimension_role == "time" else 0.68
        rank = 25 if dimension_role == "time" else 40
        if dimension_role == "identifier":
            confidence = 0.84 if _normalized_name(column_name) in grain_columns else 0.72
            rank = 20 if _normalized_name(column_name) in grain_columns else 45
        drafts.append(
            _Draft(
                entry_type="dimension",
                definition=definition,
                confidence=(
                    min(confidence, 0.52)
                    if metadata_only and name_resolved
                    else (confidence if explicit_role else min(confidence, 0.58))
                    if name_resolved
                    else 0.3
                ),
                evidence=[evidence],
                rank=(rank + 40) if metadata_only else rank if explicit_role else rank + 30,
            )
        )
    return drafts


@dataclass(frozen=True, slots=True)
class _FormulaRule:
    rule_id: str
    left_aliases: frozenset[str]
    right_aliases: frozenset[str]
    output_aliases: frozenset[str]
    operation: Literal["subtract", "multiply"]
    output_column: str
    zh_name: str
    en_name: str


_FORMULA_RULES = (
    _FormulaRule(
        rule_id="quantity_times_unit_price",
        left_aliases=frozenset({"quantity", "qty", "数量", "件数"}),
        right_aliases=frozenset({"unitprice", "priceperunit", "单价"}),
        output_aliases=frozenset(
            {"sales", "revenue", "salesamount", "totalamount", "收入", "金额", "销售额"}
        ),
        operation="multiply",
        output_column="recommended_sales_amount",
        zh_name="销售额",
        en_name="Sales Amount",
    ),
    _FormulaRule(
        rule_id="quantity_times_unit_cost",
        left_aliases=frozenset({"quantity", "qty", "数量", "件数"}),
        right_aliases=frozenset({"unitcost", "costperunit", "单位成本", "单件成本"}),
        output_aliases=frozenset({"salescost", "totalcost", "销售成本", "总成本"}),
        operation="multiply",
        output_column="recommended_sales_cost",
        zh_name="成本",
        en_name="Sales Cost",
    ),
    _FormulaRule(
        rule_id="revenue_minus_cost",
        left_aliases=frozenset({"revenue", "sales", "salesamount", "收入", "销售额"}),
        right_aliases=frozenset({"cost", "costamount", "成本", "营业成本"}),
        output_aliases=frozenset({"profit", "marginamount", "利润"}),
        operation="subtract",
        output_column="recommended_profit",
        zh_name="利润",
        en_name="Profit",
    ),
    _FormulaRule(
        rule_id="gross_minus_discount",
        left_aliases=frozenset({"grossamount", "originalamount", "原始金额", "原价金额"}),
        right_aliases=frozenset({"discountamount", "discount", "优惠金额", "折扣金额"}),
        output_aliases=frozenset({"netamount", "netrevenue", "净额", "净收入"}),
        operation="subtract",
        output_column="recommended_net_amount",
        zh_name="净额",
        en_name="Net Amount",
    ),
)


def _one_numeric_match(
    numeric: Mapping[str, list[Mapping[str, Any]]],
    aliases: Sequence[str] | frozenset[str],
) -> Mapping[str, Any] | None:
    matches = [column for alias in aliases for column in numeric.get(alias, [])]
    return matches[0] if len(matches) == 1 else None


def _derived_draft(
    table: _ScopedTable,
    *,
    batch_id: UUID,
    locale: Locale,
    rule_id: str,
    business_name: str,
    output_column: str,
    expression: dict[str, Any],
    operands: Sequence[Mapping[str, Any]],
    formula_summary: str,
    refund_present: bool,
) -> _Draft:
    operand_names = [str(operand.get("name") or "") for operand in operands]
    formula = BusinessRuleMetricFormulaAction(
        kind="metric_formula",
        output_column=output_column,
        expression=expression,
        evaluation_order="row_then_aggregate",
        null_policy="propagate",
        divide_by_zero="null",
    )
    if locale == "zh":
        description = (
            f"逐行按“{formula_summary}”计算，再汇总为候选指标；"
            "公式由系统固定生成，使用前仍需确认业务口径。"
        )
        if refund_present:
            description += " 数据中另有退款金额字段；当前公式没有扣除退款，是否扣除仍需确认。"
        questions = [
            f"{business_name}合计是多少？",
            f"{business_name}随时间有什么变化？",
        ]
    else:
        description = (
            f"Calculate {formula_summary} per row, then sum it; "
            "confirm the business meaning before use."
        )
        if refund_present:
            description += (
                " A refund amount field is present; this formula does not subtract it, "
                "and that treatment still needs confirmation."
            )
        questions = [
            f"What is total {business_name}?",
            f"How has {business_name} changed over time?",
        ]
    definition = DerivedMetricDefinition(
        kind="derived_metric",
        aggregate="sum",
        formula=formula,
        sources=[_binding(table, operand) for operand in operands],
        business_name=business_name,
        description=description,
        synonyms=[output_column],
        example_questions=questions,
    )
    evidence = _base_evidence(
        table,
        batch_id=batch_id,
        kind="deterministic_metric_formula",
        columns=operand_names,
    )
    evidence.update(
        {
            "formula_rule": rule_id,
            "model_authored": False,
            "refund_handling": "not_applied_needs_confirmation"
            if refund_present
            else "not_applicable",
        }
    )
    return _Draft(
        entry_type="metric",
        definition=definition,
        confidence=0.82,
        evidence=[evidence],
        rank=15,
    )


def _derived_metric_drafts(
    table: _ScopedTable,
    *,
    batch_id: UUID,
    locale: Locale,
) -> list[_Draft]:
    numeric: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    all_column_names = {_normalized_name(column.get("name")) for column in table.columns}
    refund_present = bool(
        all_column_names & {"refund", "refundamount", "refundedamount", "退款", "退款金额"}
    )
    for column in table.columns:
        if _stable_canonical_type(column) == "number":
            numeric[_normalized_name(column.get("name"))].append(column)

    drafts: list[_Draft] = []
    for rule in _FORMULA_RULES:
        if all_column_names & rule.output_aliases:
            continue
        left = _one_numeric_match(numeric, rule.left_aliases)
        right = _one_numeric_match(numeric, rule.right_aliases)
        if left is None or right is None:
            continue
        left_name = str(left.get("name") or "")
        right_name = str(right.get("name") or "")
        if left_name == right_name:
            continue
        business_name = rule.zh_name if locale == "zh" else rule.en_name
        symbol = "×" if rule.operation == "multiply" else "−"
        drafts.append(
            _derived_draft(
                table,
                batch_id=batch_id,
                locale=locale,
                rule_id=rule.rule_id,
                business_name=business_name,
                output_column=rule.output_column,
                expression={
                    "op": rule.operation,
                    "left": {"op": "column", "name": left_name},
                    "right": {"op": "column", "name": right_name},
                },
                operands=[left, right],
                formula_summary=f"{left_name} {symbol} {right_name}",
                refund_present=refund_present,
            )
        )

    # A gross-profit formula has a clear physical meaning only when all three
    # operands are uniquely identifiable in one scoped table.  It remains a
    # candidate because taxes, refunds, and other business adjustments are unknown.
    quantity = _one_numeric_match(numeric, frozenset({"quantity", "qty", "数量", "件数"}))
    unit_price = _one_numeric_match(numeric, frozenset({"unitprice", "priceperunit", "单价"}))
    unit_cost = _one_numeric_match(
        numeric, frozenset({"unitcost", "costperunit", "单位成本", "单件成本"})
    )
    if (
        quantity is not None
        and unit_price is not None
        and unit_cost is not None
        and not all_column_names & {"grossprofit", "marginamount", "毛利", "毛利润"}
    ):
        quantity_name = str(quantity.get("name") or "")
        price_name = str(unit_price.get("name") or "")
        cost_name = str(unit_cost.get("name") or "")
        gross_profit_name = "毛利" if locale == "zh" else "Gross Profit"
        drafts.append(
            _derived_draft(
                table,
                batch_id=batch_id,
                locale=locale,
                rule_id="quantity_times_price_minus_cost",
                business_name=gross_profit_name,
                output_column="recommended_gross_profit",
                expression={
                    "op": "multiply",
                    "left": {"op": "column", "name": quantity_name},
                    "right": {
                        "op": "subtract",
                        "left": {"op": "column", "name": price_name},
                        "right": {"op": "column", "name": cost_name},
                    },
                },
                operands=[quantity, unit_price, unit_cost],
                formula_summary=f"{quantity_name} × ({price_name} − {cost_name})",
                refund_present=refund_present,
            )
        )
    return drafts


def declared_relationship_evidence(
    profile: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Return only relationships proven by database constraint metadata."""

    evidence = [
        dict(item)
        for item in (profile.get("preanalysis") or {}).get("relationship_evidence", [])
        if isinstance(item, Mapping)
        and item.get("kind") == "declared_foreign_key"
        and item.get("catalog_verified") is True
        and item.get("binding_complete") is True
    ]
    for table in _profile_tables(profile):
        if table.get("constraint_metadata_status") != "available":
            continue
        table_name = str(table.get("name") or "").strip()
        table_schema = str(table.get("schema") or "").strip() or None
        if not table_name:
            continue
        for foreign_key in table.get("foreign_keys") or []:
            if not isinstance(foreign_key, Mapping):
                continue
            source_columns = [
                str(value).strip()
                for value in foreign_key.get("columns") or []
                if str(value).strip()
            ]
            target_columns = [
                str(value).strip()
                for value in foreign_key.get("referenced_columns") or []
                if str(value).strip()
            ]
            target_table = str(foreign_key.get("referenced_table") or "").strip()
            if not target_table or not source_columns or len(source_columns) != len(target_columns):
                continue
            evidence.append(
                {
                    "kind": "declared_foreign_key",
                    "catalog_verified": True,
                    "binding_complete": True,
                    "constraint_name": foreign_key.get("name"),
                    "source": {
                        "schema": table_schema,
                        "table": table_name,
                        "columns": source_columns,
                    },
                    "target": {
                        "schema": foreign_key.get("referenced_schema") or table_schema,
                        "table": target_table,
                        "columns": target_columns,
                    },
                    "on_update": foreign_key.get("on_update"),
                    "on_delete": foreign_key.get("on_delete"),
                }
            )
    return evidence


def _relationship_drafts(
    context: ProjectRuntimeContext,
    tables: Sequence[_ScopedTable],
    *,
    batch_id: UUID,
    locale: Locale,
) -> list[_Draft]:
    selected_by_source: dict[str, dict[str, _ScopedTable]] = defaultdict(dict)
    for table in tables:
        selected_by_source[table.source_id][table.table_name.casefold()] = table
    source_lookup = {
        str(source.get("id") or ""): source
        for source in context.sources
        if isinstance(source, Mapping)
    }
    drafts: list[_Draft] = []
    for source_id, selected in selected_by_source.items():
        source = source_lookup[source_id]
        profile = source.get("profile") or {}
        for relationship in declared_relationship_evidence(profile):
            if (
                not isinstance(relationship, Mapping)
                or relationship.get("kind") != "declared_foreign_key"
                or relationship.get("catalog_verified") is not True
                or relationship.get("binding_complete") is not True
            ):
                continue
            source_binding = relationship.get("source") or {}
            target_binding = relationship.get("target") or {}
            source_columns = [str(value) for value in source_binding.get("columns") or []]
            target_columns = [str(value) for value in target_binding.get("columns") or []]
            if len(source_columns) != 1 or len(target_columns) != 1:
                continue

            def resolve_endpoint(binding: Mapping[str, Any]) -> _ScopedTable | None:
                bare = str(binding.get("table") or "").strip()
                schema = str(binding.get("schema") or "").strip()
                if not bare:
                    return None
                if schema:
                    return selected.get(f"{schema}.{bare}".casefold())
                bare_matches = [
                    table
                    for canonical, table in selected.items()
                    if canonical.rsplit(".", 1)[-1] == bare.casefold()
                ]
                return bare_matches[0] if len(bare_matches) == 1 else None

            left_table = resolve_endpoint(source_binding)
            right_table = resolve_endpoint(target_binding)
            if left_table is None or right_table is None:
                continue
            left_column = next(
                (
                    column
                    for column in left_table.columns
                    if str(column.get("name") or "") == source_columns[0]
                ),
                None,
            )
            right_column = next(
                (
                    column
                    for column in right_table.columns
                    if str(column.get("name") or "") == target_columns[0]
                ),
                None,
            )
            if left_column is None or right_column is None:
                continue
            left = RelationshipEndpoint(
                source_logical_name=left_table.logical_name,
                source_kind=left_table.source_kind,
                table_or_view=left_table.table_name,
                column=source_columns[0],
                data_type=str(left_column.get("type") or left_column.get("dtype") or "unknown"),
                schema_signature=left_table.schema_signature,
            )
            right = RelationshipEndpoint(
                source_logical_name=right_table.logical_name,
                source_kind=right_table.source_kind,
                table_or_view=right_table.table_name,
                column=target_columns[0],
                data_type=str(right_column.get("type") or right_column.get("dtype") or "unknown"),
                schema_signature=right_table.schema_signature,
            )
            if locale == "zh":
                left_name = _relationship_table_name(
                    left_table,
                    locale=locale,
                    fallback="业务明细",
                )
                right_name = _relationship_table_name(
                    right_table,
                    locale=locale,
                    fallback="关联资料",
                )
                business_name = f"{left_name}与{right_name}的关联"
                description = f"{left_name}与{right_name}可关联，采纳前会核对。"
                questions = [f"按{right_name}查看{left_name}，结果有什么变化？"]
            else:
                left_name = _relationship_table_name(
                    left_table,
                    locale=locale,
                    fallback="Business records",
                )
                right_name = _relationship_table_name(
                    right_table,
                    locale=locale,
                    fallback="Related records",
                )
                business_name = f"{left_name} and {right_name} relationship"
                description = f"{left_name} can be related to {right_name}; ReceiptBI will verify it before use."
                questions = [f"How do {left_name} results vary by {right_name}?"]
            definition = RelationshipDefinition(
                kind="relationship",
                left=left,
                right=right,
                normalization="exact",
                cardinality="many_to_one",
                default_join="left",
                minimum_left_match_rate=0.8,
                maximum_expansion_ratio=1.2,
                business_name=business_name,
                description=description,
                synonyms=[],
                example_questions=questions,
            )
            evidence = _base_evidence(
                left_table,
                batch_id=batch_id,
                kind="declared_foreign_key",
                columns=[source_columns[0], target_columns[0]],
            )
            evidence.update(
                {
                    "constraint_name": relationship.get("constraint_name"),
                    "sources": [
                        f"{left_table.source_name}.{left_table.table_name}.{source_columns[0]}",
                        f"{right_table.source_name}.{right_table.table_name}.{target_columns[0]}",
                    ],
                    "catalog_verified": True,
                    "binding_complete": True,
                    "automatic_confirmation": False,
                    "requires_value_validation": True,
                }
            )
            drafts.append(
                _Draft(
                    entry_type="relationship",
                    definition=definition,
                    confidence=0.85,
                    evidence=[evidence],
                    rank=10,
                )
            )
    return drafts


def _definition_identity(draft: _Draft) -> str:
    payload = draft.definition.model_dump(mode="json")
    for field_name in ("business_name", "description", "example_questions", "synonyms"):
        payload.pop(field_name, None)
    serialized = json.dumps(
        {"entry_type": draft.entry_type, "definition": payload},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _business_name(definition: Any) -> str:
    return str(getattr(definition, "business_name", None) or "候选理解")


def _with_business_name(draft: _Draft, business_name: str) -> _Draft:
    payload = draft.definition.model_dump(mode="python")
    payload["business_name"] = business_name
    definition_type = type(draft.definition)
    return replace(draft, definition=definition_type.model_validate(payload))


def _deduplicate_and_disambiguate(drafts: Sequence[_Draft], locale: Locale) -> list[_Draft]:
    by_identity: dict[str, _Draft] = {}
    for draft in drafts:
        identity = _definition_identity(draft)
        existing = by_identity.get(identity)
        if existing is None or (draft.rank, -draft.confidence) < (
            existing.rank,
            -existing.confidence,
        ):
            by_identity[identity] = draft
    unique = list(by_identity.values())
    groups: dict[str, list[int]] = defaultdict(list)
    for index, draft in enumerate(unique):
        groups[_business_name(draft.definition).casefold()].append(index)
    for indices in groups.values():
        if len(indices) < 2:
            continue
        for index in indices:
            draft = unique[index]
            evidence = draft.evidence[0]
            table = str(evidence.get("table_or_view") or "")
            source = str(evidence.get("source") or "")
            base = _business_name(draft.definition)
            separator = " · "
            qualifier = table or source
            unique[index] = _with_business_name(draft, f"{qualifier}{separator}{base}")

    # A repeated physical table name across sources can still collide; add the source
    # only to those remaining collisions without changing candidate identity.
    final_groups: dict[str, list[int]] = defaultdict(list)
    for index, draft in enumerate(unique):
        final_groups[_business_name(draft.definition).casefold()].append(index)
    for indices in final_groups.values():
        if len(indices) < 2:
            continue
        for index in indices:
            draft = unique[index]
            source = str(draft.evidence[0].get("source") or "数据源")
            unique[index] = _with_business_name(
                draft,
                f"{source} · {_business_name(draft.definition)}",
            )
    remaining_groups: dict[str, list[int]] = defaultdict(list)
    for index, draft in enumerate(unique):
        remaining_groups[_business_name(draft.definition).casefold()].append(index)
    for indices in remaining_groups.values():
        if len(indices) < 2:
            continue
        for index in indices:
            draft = unique[index]
            columns = [str(value) for value in draft.evidence[0].get("columns") or []]
            qualifier = "+".join(columns) or _definition_identity(draft)[:8]
            unique[index] = _with_business_name(
                draft,
                f"{_business_name(draft.definition)} · {qualifier}",
            )
    return sorted(
        unique, key=lambda item: (item.rank, -item.confidence, _definition_identity(item))
    )


def _candidate_key(draft: _Draft) -> str:
    return f"semantic_recommendation:{draft.entry_type}:{_definition_identity(draft)[:24]}"


def _render_value(definition: Any, locale: Locale) -> str:
    name = _business_name(definition)
    if isinstance(definition, AggregateMetricDefinition):
        if locale == "en":
            operation = "average" if definition.operation == "avg" else "total"
            return f"Candidate metric: calculate {operation} {name}."
        operation = "平均" if definition.operation == "avg" else "合计"
        return f"候选指标：按{operation}计算“{name}”。"
    if isinstance(definition, DerivedMetricDefinition):
        if locale == "en":
            return f"Candidate derived metric: calculate the fixed row formula, then {definition.aggregate} {name}."
        return f"候选派生指标：按固定公式逐行计算后汇总“{name}”。"
    if isinstance(definition, DimensionDefinition):
        if locale == "en":
            return f"Candidate dimension: use {name} to group or inspect results."
        return f"候选维度：可按“{name}”分组或核对结果。"
    if isinstance(definition, ScopePresentationDefinition):
        if locale == "en":
            label = "data source" if definition.scope_kind == "source" else "table"
            return f"Candidate {label} name: {name}."
        label = "数据源" if definition.scope_kind == "source" else "数据表"
        return f"候选{label}名称：“{name}”。"
    if locale == "en":
        return f"Suggested relationship: {name}."
    return f"建议关联：{name}。"


def _entry_from_draft(draft: _Draft, locale: Locale) -> SemanticEntryCreate:
    key = _candidate_key(draft)
    evidence = [dict(item) for item in draft.evidence]
    for item in evidence:
        item["candidate_id"] = key
    return SemanticEntryCreate(
        key=key,
        value=_render_value(draft.definition, locale),
        entry_type=draft.entry_type,
        state="candidate",
        confidence=draft.confidence,
        definition=draft.definition,
        validity="unverified",
        evidence=evidence,
        source="inferred",
    )


def _enhancer_payload(items: Sequence[SemanticEntryCreate], locale: Locale) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for item in items:
        definition = item.definition
        payload.append(
            {
                "candidate_id": item.key,
                "entry_type": item.entry_type,
                "business_name": _business_name(definition),
                "description": getattr(definition, "description", None),
                "example_questions": list(getattr(definition, "example_questions", []) or []),
                "synonyms": list(getattr(definition, "synonyms", []) or []),
                "locale": locale,
                "immutable_context": next(
                    (
                        dict(evidence.get("recommendation_context") or {})
                        for evidence in item.evidence
                        if isinstance(evidence, Mapping)
                        and isinstance(evidence.get("recommendation_context"), Mapping)
                    ),
                    {},
                ),
                "immutable_definition": definition.model_dump(
                    mode="json",
                    exclude={
                        "business_name",
                        "description",
                        "example_questions",
                        "synonyms",
                    },
                ),
            }
        )
    return payload


def _validate_enhancements(
    raw: Any,
    items: Sequence[SemanticEntryCreate],
) -> list[SemanticRecommendationEnhancement] | None:
    if isinstance(raw, (str, bytes, Mapping)) or not isinstance(raw, Sequence):
        return None
    try:
        enhancements = [SemanticRecommendationEnhancement.model_validate(item) for item in raw]
    except (TypeError, ValidationError, ValueError):
        return None
    expected = {item.key for item in items}
    received = [item.candidate_id for item in enhancements]
    if len(received) != len(set(received)) or set(received) != expected:
        return None
    current_names = {item.key: _business_name(item.definition) for item in items}
    proposed_names = [
        (item.business_name or current_names[item.candidate_id]).strip().casefold()
        for item in enhancements
    ]
    if any(not name for name in proposed_names) or len(proposed_names) != len(set(proposed_names)):
        return None
    return enhancements


def _apply_enhancement(
    item: SemanticEntryCreate,
    enhancement: SemanticRecommendationEnhancement,
    *,
    batch_id: UUID,
    locale: Locale,
) -> SemanticEntryCreate:
    definition = item.definition
    definition_payload = definition.model_dump(mode="python")
    if enhancement.business_name is not None:
        definition_payload["business_name"] = enhancement.business_name.strip()
    if enhancement.description is not None:
        definition_payload["description"] = enhancement.description.strip()
    if enhancement.example_questions is not None:
        definition_payload["example_questions"] = [
            question.strip() for question in enhancement.example_questions if question.strip()
        ]
    if enhancement.synonyms is not None:
        existing_synonyms = list(definition_payload.get("synonyms") or [])
        definition_payload["synonyms"] = _normalized_synonyms(
            [*existing_synonyms, *enhancement.synonyms],
            str(definition_payload.get("business_name") or ""),
        )
    enhanced_definition = type(definition).model_validate(definition_payload)
    evidence = [dict(value) for value in item.evidence]
    evidence.append(
        {
            "kind": "model_presentation_enhancement",
            "batch_id": str(batch_id),
            "candidate_id": item.key,
            "allowed_fields": [
                "business_name",
                "description",
                "example_questions",
                "synonyms",
            ],
        }
    )
    return item.model_copy(
        update={
            "definition": enhanced_definition,
            "value": _render_value(enhanced_definition, locale),
            "evidence": evidence,
        }
    )


async def generate_semantic_recommendations(
    context: ProjectRuntimeContext,
    scopes: Sequence[SemanticRecommendationScope | Mapping[str, Any]],
    locale: Locale = "zh",
    limit: int = _MAX_PUBLIC_RECOMMENDATIONS,
    batch_id: UUID | None = None,
    enhancer: SemanticRecommendationEnhancer | None = None,
    *,
    mode: RecommendationMode = "full",
    presentation_only: bool | None = None,
    include_source_presentation: bool = True,
    include_table_presentations: bool = True,
) -> SemanticRecommendationBatch:
    """Build governed candidates from explicit, already-profiled source scopes.

    ``enhancer`` receives only candidate IDs and presentation text.  It must return
    each allowed ID exactly once; malformed, partial, duplicate, or unknown output
    causes an all-or-nothing fallback to the deterministic batch.
    """

    if locale not in {"zh", "en"}:
        raise SemanticRecommendationError("locale must be zh or en")
    if presentation_only is not None:
        if mode != "full":
            raise SemanticRecommendationError(
                "presentation_only cannot be combined with an explicit recommendation mode"
            )
        mode = "presentation" if presentation_only else "full"
    if mode not in {"full", "presentation", "structure", "relationships"}:
        raise SemanticRecommendationError("recommendation mode is invalid")
    if (
        not isinstance(limit, int)
        or isinstance(limit, bool)
        or not 1 <= limit <= _MAX_INVENTORY_RECOMMENDATIONS
    ):
        raise SemanticRecommendationError(
            f"推荐数量必须在 1 到 {_MAX_INVENTORY_RECOMMENDATIONS} 之间"
        )
    resolved_batch_id = batch_id or uuid4()
    tables = _scoped_tables(context, scopes)

    drafts = (
        []
        if mode == "relationships"
        else _scope_presentation_drafts(
            tables,
            batch_id=resolved_batch_id,
            locale=locale,
            include_source=include_source_presentation,
            include_tables=include_table_presentations,
        )
    )
    if mode == "full":
        drafts.extend(
            [
                draft
                for table in tables
                for draft in (
                    _derived_metric_drafts(table, batch_id=resolved_batch_id, locale=locale)
                    + _profile_drafts(table, batch_id=resolved_batch_id, locale=locale)
                )
            ]
        )
        drafts.extend(
            _relationship_drafts(
                context,
                tables,
                batch_id=resolved_batch_id,
                locale=locale,
            )
        )
    elif mode == "structure":
        drafts.extend(
            draft
            for table in tables
            for draft in _profile_drafts(
                table,
                batch_id=resolved_batch_id,
                locale=locale,
                metadata_only=True,
            )
        )
    elif mode == "relationships":
        drafts.extend(
            _relationship_drafts(
                context,
                tables,
                batch_id=resolved_batch_id,
                locale=locale,
            )
        )
    deterministic = [
        _entry_from_draft(draft, locale)
        for draft in _deduplicate_and_disambiguate(drafts, locale)[:limit]
    ]
    if enhancer is None or not deterministic:
        return SemanticRecommendationBatch(
            batch_id=resolved_batch_id,
            generated_by="preflight",
            items=deterministic,
        )

    try:
        enhancement_chunks: list[SemanticRecommendationEnhancement] = []
        for offset in range(0, len(deterministic), _MAX_PUBLIC_RECOMMENDATIONS):
            chunk = deterministic[offset : offset + _MAX_PUBLIC_RECOMMENDATIONS]
            raw_enhancements = enhancer(_enhancer_payload(chunk, locale))
            if inspect.isawaitable(raw_enhancements):
                raw_enhancements = await raw_enhancements
            validated_chunk = _validate_enhancements(raw_enhancements, chunk)
            if validated_chunk is None:
                raise ValueError("invalid enhancement chunk")
            enhancement_chunks.extend(validated_chunk)
        enhancements = _validate_enhancements(enhancement_chunks, deterministic)
        if enhancements is None:
            raise ValueError("invalid enhancement batch")
        enhancements_by_id = {item.candidate_id: item for item in enhancements}
        enhanced = [
            _apply_enhancement(
                item,
                enhancements_by_id[item.key],
                batch_id=resolved_batch_id,
                locale=locale,
            )
            for item in deterministic
        ]
    except Exception:
        # Provider/model failure is presentation-only and must never make the
        # deterministic recommendation path unavailable.
        return SemanticRecommendationBatch(
            batch_id=resolved_batch_id,
            generated_by="preflight",
            items=deterministic,
        )
    return SemanticRecommendationBatch(
        batch_id=resolved_batch_id,
        generated_by="ai",
        items=enhanced,
    )


__all__ = [
    "SemanticRecommendationBatch",
    "SemanticRecommendationEnhancement",
    "SemanticRecommendationEnhancer",
    "SemanticRecommendationError",
    "declared_relationship_evidence",
    "generate_semantic_recommendations",
]
