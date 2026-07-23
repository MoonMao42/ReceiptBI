from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.models.workspace import (
    AggregateMetricDefinition,
    DerivedMetricDefinition,
    DimensionDefinition,
    RelationshipDefinition,
    ScopePresentationDefinition,
    SemanticEntryCreate,
    SemanticRecommendationScope,
)
from app.services.metric_formula import metric_formula_columns
from app.services.result_filters import stable_field_binding_candidates, stable_schema_signature
from app.services.semantic_recommendations import (
    SemanticRecommendationError,
    generate_semantic_recommendations,
)


def _orders_context() -> tuple[SimpleNamespace, UUID]:
    source_id = uuid4()
    columns = [
        {"name": "order_id", "dtype": "str"},
        {"name": "order_date", "dtype": "datetime64[ns]"},
        {"name": "department", "dtype": "str"},
        {"name": "region", "dtype": "str"},
        {"name": "channel", "dtype": "str"},
        {"name": "product", "dtype": "str"},
        {"name": "quantity", "dtype": "int64"},
        {"name": "unit_price", "dtype": "float64"},
        {"name": "unit_cost", "dtype": "float64"},
        {"name": "refund_amount", "dtype": "float64"},
    ]
    roles = [
        {
            "column": "order_id",
            "role": "identifier",
            "status": "candidate",
            "non_null": 100,
            "unique": 100,
            "uniqueness": 1.0,
        },
        {
            "column": "order_date",
            "role": "time",
            "status": "candidate",
            "non_null": 100,
            "unique": 60,
        },
        *[
            {
                "column": name,
                "role": "dimension",
                "status": "candidate",
                "non_null": 100,
                "unique": unique,
            }
            for name, unique in (
                ("department", 4),
                ("region", 6),
                ("channel", 3),
                ("product", 12),
            )
        ],
        *[
            {
                "column": name,
                "role": "measure",
                "status": "candidate",
                "non_null": 100,
                "unique": 20,
                "distribution": {"min": 0, "median": 4, "max": 100},
            }
            for name in ("quantity", "unit_price", "unit_cost", "refund_amount")
        ],
    ]
    source = {
        "id": str(source_id),
        "name": "orders.csv",
        "kind": "file",
        "format": "csv",
        "status": "ready",
        # This is intentionally different from logical_name. Stable semantic
        # bindings must never retain this physical attachment view.
        "view_name": "orders_9d9d9d",
        "profile": {
            "logical_name": "orders",
            "is_current": True,
            "schema": {
                "columns": columns,
                "candidate_grain": [
                    {"column": "order_id", "uniqueness": 1.0, "evidence_kind": "sample_profile"},
                    # A daily transaction export can have one distinct date per row.
                    # The explicit time role must still win over grain heuristics.
                    {
                        "column": "order_date",
                        "uniqueness": 1.0,
                        "evidence_kind": "sample_profile",
                    },
                ],
            },
            "preanalysis": {
                "generated_by": "deterministic_preflight",
                "candidate_roles": roles,
            },
        },
    }
    return SimpleNamespace(sources=[source]), source_id


def _database_context() -> tuple[SimpleNamespace, UUID]:
    source_id = uuid4()
    tables = [
        {
            "name": "orders",
            "schema": "public",
            "columns": [
                {"name": "order_id", "type": "BIGINT"},
                {"name": "customer_id", "type": "BIGINT"},
                {"name": "amount", "type": "DECIMAL"},
            ],
        },
        {
            "name": "customers",
            "schema": "public",
            "columns": [
                {"name": "id", "type": "BIGINT"},
                {"name": "region", "type": "VARCHAR"},
            ],
        },
        {
            "name": "payments",
            "schema": "public",
            "columns": [
                {"name": "order_id", "type": "BIGINT"},
                {"name": "amount", "type": "DECIMAL"},
            ],
        },
    ]
    roles = [
        {"table": "orders", "column": "order_id", "role": "identifier", "non_null": 20},
        {
            "table": "orders",
            "column": "customer_id",
            "role": "identifier",
            "non_null": 20,
        },
        {"table": "orders", "column": "amount", "role": "measure", "non_null": 20},
        {"table": "customers", "column": "id", "role": "identifier", "non_null": 10},
        {"table": "customers", "column": "region", "role": "dimension", "non_null": 10},
        {"table": "payments", "column": "order_id", "role": "identifier", "non_null": 20},
        {"table": "payments", "column": "amount", "role": "measure", "non_null": 20},
    ]
    relationships = [
        {
            "kind": "declared_foreign_key",
            "catalog_verified": True,
            "binding_complete": True,
            "constraint_name": "orders_customer_id_fkey",
            "source": {"schema": "public", "table": "orders", "columns": ["customer_id"]},
            "target": {"schema": "public", "table": "customers", "columns": ["id"]},
        },
        {
            "kind": "declared_foreign_key",
            "catalog_verified": True,
            "binding_complete": True,
            "constraint_name": "payments_order_id_fkey",
            "source": {"schema": "public", "table": "payments", "columns": ["order_id"]},
            "target": {"schema": "public", "table": "orders", "columns": ["order_id"]},
        },
    ]
    source = {
        "id": str(source_id),
        "name": "业务数据库",
        "kind": "connection",
        "status": "ready",
        "profile": {
            "logical_name": "commerce",
            "is_current": True,
            "tables": tables,
            "preanalysis": {
                "generated_by": "deterministic_database_value_preflight",
                "candidate_roles": roles,
                "relationship_evidence": relationships,
            },
        },
    }
    return SimpleNamespace(sources=[source]), source_id


def _definition_name(item: SemanticEntryCreate) -> str:
    return str(getattr(item.definition, "business_name", ""))


@pytest.mark.asyncio
async def test_orders_profile_produces_typed_governed_candidates() -> None:
    context, source_id = _orders_context()
    batch_id = uuid4()

    batch = await generate_semantic_recommendations(
        context,
        [SemanticRecommendationScope(source_id=source_id)],
        "zh",
        50,
        batch_id,
        None,
    )

    assert batch.batch_id == batch_id
    assert batch.generated_by == "preflight"
    assert batch.items
    assert len({item.key for item in batch.items}) == len(batch.items)
    assert len({_definition_name(item) for item in batch.items}) == len(batch.items)
    assert all(item.state == "candidate" and item.validity == "unverified" for item in batch.items)
    assert all(item.evidence[0]["batch_id"] == str(batch_id) for item in batch.items)
    assert all(item.evidence[0]["candidate_id"] == item.key for item in batch.items)

    dimensions = [
        item.definition for item in batch.items if isinstance(item.definition, DimensionDefinition)
    ]
    dimension_by_name = {item.business_name: item for item in dimensions}
    assert {"下单日期", "部门", "地区", "渠道", "商品"} <= set(dimension_by_name)
    assert dimension_by_name["下单日期"].role == "time"
    assert {"year", "month", "day"} <= set(dimension_by_name["下单日期"].time_granularities)

    aggregate_metrics = [
        item.definition
        for item in batch.items
        if isinstance(item.definition, AggregateMetricDefinition)
    ]
    assert any(
        metric.business_name == "销量" and metric.operation == "sum" for metric in aggregate_metrics
    )

    derived = [
        item.definition
        for item in batch.items
        if isinstance(item.definition, DerivedMetricDefinition)
    ]
    derived_by_name = {item.business_name: item for item in derived}
    assert {"销售额", "成本", "毛利"} <= set(derived_by_name)
    assert set(metric_formula_columns(derived_by_name["销售额"].formula.model_dump())) == {
        "quantity",
        "unit_price",
    }
    assert set(metric_formula_columns(derived_by_name["成本"].formula.model_dump())) == {
        "quantity",
        "unit_cost",
    }
    assert set(metric_formula_columns(derived_by_name["毛利"].formula.model_dump())) == {
        "quantity",
        "unit_price",
        "unit_cost",
    }
    assert "refund_amount" not in metric_formula_columns(
        derived_by_name["毛利"].formula.model_dump()
    )
    assert "没有扣除退款" in str(derived_by_name["毛利"].description)

    source = context.sources[0]
    for item in batch.items:
        definition = item.definition
        bindings = []
        if isinstance(definition, AggregateMetricDefinition | DimensionDefinition):
            bindings = [definition.source]
        elif isinstance(definition, DerivedMetricDefinition):
            bindings = definition.sources
        for binding in bindings:
            assert binding.table_or_view == "orders"
            runtime_candidates = stable_field_binding_candidates(source, binding.action_column)
            assert binding.model_dump(mode="json") in runtime_candidates
        # Re-validating the public create payload catches discriminator drift.
        SemanticEntryCreate.model_validate(item.model_dump(mode="python"))


@pytest.mark.asyncio
async def test_relationships_require_declared_profile_evidence_and_full_table_scope() -> None:
    context, source_id = _database_context()

    scoped = await generate_semantic_recommendations(
        context,
        [{"source_id": source_id, "tables": ["public.orders", "customers"]}],
        "zh",
        50,
        uuid4(),
        None,
    )
    relationships = [
        item for item in scoped.items if isinstance(item.definition, RelationshipDefinition)
    ]
    assert len(relationships) == 1
    relationship = relationships[0]
    assert relationship.definition.left.table_or_view == "public.orders"
    assert relationship.definition.right.table_or_view == "public.customers"
    assert relationship.definition.left.schema_signature == stable_schema_signature(
        context.sources[0]["profile"]["tables"][0]["columns"]
    )
    assert relationship.definition.right.schema_signature == stable_schema_signature(
        context.sources[0]["profile"]["tables"][1]["columns"]
    )
    assert relationship.evidence[0]["kind"] == "declared_foreign_key"
    assert relationship.evidence[0]["requires_value_validation"] is True
    assert "payments" not in relationship.value
    assert relationship.value == "建议关联：订单信息与客户信息的关联。"
    assert relationship.definition.description == "订单信息与客户信息可关联，采纳前会核对。"
    assert relationship.definition.example_questions == ["按客户信息查看订单信息，结果有什么变化？"]
    assert relationship.definition.synonyms == []
    public_copy = " ".join(
        [
            relationship.value,
            relationship.definition.description or "",
            *relationship.definition.example_questions,
        ]
    )
    assert "public" not in public_copy
    assert "customer_id" not in public_copy
    source = context.sources[0]
    for item in scoped.items:
        definition = item.definition
        if isinstance(definition, AggregateMetricDefinition | DimensionDefinition):
            assert definition.source.model_dump(mode="json") in stable_field_binding_candidates(
                source, definition.source.action_column
            )

    one_table = await generate_semantic_recommendations(
        context,
        [{"source_id": source_id, "tables": ["orders"]}],
        "zh",
        50,
        uuid4(),
        None,
    )
    assert not any(isinstance(item.definition, RelationshipDefinition) for item in one_table.items)


@pytest.mark.asyncio
async def test_connection_scope_must_name_known_tables() -> None:
    context, source_id = _database_context()

    with pytest.raises(SemanticRecommendationError, match="必须明确选择表"):
        await generate_semantic_recommendations(
            context, [{"source_id": source_id}], "zh", 10, uuid4(), None
        )
    with pytest.raises(SemanticRecommendationError, match="不包含唯一可识别"):
        await generate_semantic_recommendations(
            context,
            [{"source_id": source_id, "tables": ["unknown"]}],
            "zh",
            10,
            uuid4(),
            None,
        )
    with pytest.raises(SemanticRecommendationError, match="未知或尚未就绪"):
        await generate_semantic_recommendations(
            context,
            [{"source_id": uuid4(), "tables": ["orders"]}],
            "zh",
            10,
            uuid4(),
            None,
        )


@pytest.mark.asyncio
async def test_same_table_name_in_two_schemas_never_leaks_semantics() -> None:
    context, source_id = _database_context()
    profile = context.sources[0]["profile"]
    profile["tables"].append(
        {
            "name": "orders",
            "schema": "archive",
            "columns": [
                {"name": "legacy_order_id", "type": "BIGINT"},
                {"name": "legacy_label", "type": "VARCHAR"},
            ],
        }
    )
    profile["preanalysis"]["candidate_roles"].extend(
        [
            {
                "table": "public.orders",
                "column": "order_id",
                "role": "identifier",
                "non_null": 20,
            },
            {
                "table": "archive.orders",
                "column": "legacy_label",
                "role": "dimension",
                "non_null": 8,
            },
        ]
    )

    with pytest.raises(SemanticRecommendationError, match="不包含唯一可识别"):
        await generate_semantic_recommendations(
            context,
            [{"source_id": source_id, "tables": ["orders"]}],
            "zh",
            50,
            uuid4(),
            None,
            mode="structure",
        )

    public_batch = await generate_semantic_recommendations(
        context,
        [{"source_id": source_id, "tables": ["public.orders"]}],
        "zh",
        50,
        uuid4(),
        None,
        mode="structure",
    )
    public_dimensions = [
        item.definition
        for item in public_batch.items
        if isinstance(item.definition, DimensionDefinition)
    ]
    assert public_dimensions
    assert {item.source.table_or_view for item in public_dimensions} == {"public.orders"}
    assert "legacy_label" not in {item.source.action_column for item in public_dimensions}

    archive_batch = await generate_semantic_recommendations(
        context,
        [{"source_id": source_id, "tables": ["archive.orders"]}],
        "zh",
        50,
        uuid4(),
        None,
        mode="structure",
    )
    archive_dimensions = [
        item.definition
        for item in archive_batch.items
        if isinstance(item.definition, DimensionDefinition)
    ]
    assert {item.source.table_or_view for item in archive_dimensions} == {"archive.orders"}
    assert "legacy_label" in {item.source.action_column for item in archive_dimensions}
    assert not {item.source.action_column for item in archive_dimensions}.intersection(
        {"order_id", "customer_id", "amount"}
    )


@pytest.mark.asyncio
async def test_account_rep_fields_never_become_amount_metrics_from_name_substrings() -> None:
    context, source_id = _database_context()
    context.sources[0]["profile"]["tables"].append(
        {
            "name": "account_reps",
            "columns": [
                {"name": "account_rep_name", "type": "TEXT"},
                {"name": "account_rep_id", "type": "TEXT"},
                {"name": "other_account_rep_code", "type": "TEXT"},
                {"name": "updated_by", "type": "TEXT"},
                {"name": "paid_amount", "type": "DECIMAL"},
                {"name": "sales_amount", "type": "DECIMAL"},
            ],
        }
    )
    # Simulate a stored profile created by the old substring classifier.  The
    # recommendation layer must still enforce the physical numeric type gate.
    context.sources[0]["profile"]["preanalysis"]["candidate_roles"].extend(
        [
            {
                "table": "account_reps",
                "column": "account_rep_name",
                "role": "measure",
                "non_null": 20,
            },
            {
                "table": "account_reps",
                "column": "account_rep_id",
                "role": "identifier",
                "non_null": 20,
            },
            {
                "table": "account_reps",
                "column": "other_account_rep_code",
                "role": "identifier",
                "non_null": 20,
            },
            {
                "table": "account_reps",
                "column": "sales_amount",
                "role": "measure",
                "non_null": 20,
            },
            {
                "table": "account_reps",
                "column": "updated_by",
                "role": "time",
                "non_null": 20,
            },
            {
                "table": "account_reps",
                "column": "paid_amount",
                "role": "identifier",
                "non_null": 20,
            },
        ]
    )

    batch = await generate_semantic_recommendations(
        context,
        [{"source_id": source_id, "tables": ["account_reps"]}],
        "zh",
        20,
        uuid4(),
        None,
    )

    metrics = [
        item.definition
        for item in batch.items
        if isinstance(item.definition, AggregateMetricDefinition)
    ]
    dimensions = [
        item.definition for item in batch.items if isinstance(item.definition, DimensionDefinition)
    ]
    assert {metric.source.action_column for metric in metrics} == {
        "paid_amount",
        "sales_amount",
    }
    assert {dimension.source.action_column for dimension in dimensions} == {
        "account_rep_name",
        "account_rep_id",
        "other_account_rep_code",
        "updated_by",
    }
    roles = {dimension.source.action_column: dimension.role for dimension in dimensions}
    assert roles == {
        "account_rep_name": "category",
        "account_rep_id": "identifier",
        "other_account_rep_code": "identifier",
        "updated_by": "category",
    }


@pytest.mark.asyncio
async def test_keys_are_stable_across_batches_and_duplicate_roles_do_not_duplicate() -> None:
    context, source_id = _orders_context()
    context.sources[0]["profile"]["preanalysis"]["candidate_roles"].append(
        {
            "column": "quantity",
            "role": "measure",
            "status": "candidate",
            "non_null": 100,
        }
    )

    first = await generate_semantic_recommendations(
        context, [{"source_id": source_id}], "zh", 50, uuid4(), None
    )
    second = await generate_semantic_recommendations(
        context, [{"source_id": source_id}], "zh", 50, uuid4(), None
    )

    assert [item.key for item in first.items] == [item.key for item in second.items]
    quantity_metrics = [
        item
        for item in first.items
        if isinstance(item.definition, AggregateMetricDefinition)
        and item.definition.source.action_column == "quantity"
    ]
    assert len(quantity_metrics) == 1


@pytest.mark.asyncio
async def test_enhancer_can_only_change_presentation_without_reordering() -> None:
    context, source_id = _orders_context()
    batch_id = uuid4()
    deterministic = await generate_semantic_recommendations(
        context, [{"source_id": source_id}], "zh", 8, batch_id, None
    )
    original_by_id = {item.key: item for item in deterministic.items}

    async def enhancer(payload: list[dict[str, object]]) -> list[dict[str, object]]:
        assert payload
        assert all("definition" not in item and "formula" not in item for item in payload)
        assert all(item["immutable_context"]["source_technical_name"] for item in payload)
        assert all(item["immutable_context"]["table_technical_name"] for item in payload)
        assert all(len(item["immutable_context"]["same_table_fields"]) <= 80 for item in payload)
        return [
            {
                "candidate_id": item["candidate_id"],
                "business_name": f"推荐 {item['business_name']}",
                "description": f"已润色：{item['description']}",
                "example_questions": [f"请分析 {item['business_name']}"],
                "synonyms": ["业务同义词"],
            }
            for item in reversed(payload)
        ]

    enhanced = await generate_semantic_recommendations(
        context, [{"source_id": source_id}], "zh", 8, batch_id, enhancer
    )

    assert enhanced.generated_by == "ai"
    assert [item.key for item in enhanced.items] == [item.key for item in deterministic.items]
    for item in enhanced.items:
        original = original_by_id[item.key]
        assert _definition_name(item).startswith("推荐 ")
        assert item.confidence == original.confidence
        assert "业务同义词" in item.definition.synonyms
        assert item.definition.model_dump(
            exclude={"business_name", "description", "example_questions", "synonyms"}
        ) == (
            original.definition.model_dump(
                exclude={"business_name", "description", "example_questions", "synonyms"}
            )
        )
        assert item.evidence[-1]["kind"] == "model_presentation_enhancement"


@pytest.mark.asyncio
async def test_product_published_at_has_chinese_label_synonyms_and_physical_binding() -> None:
    context, source_id = _database_context()
    context.sources[0]["profile"]["tables"].append(
        {
            "name": "catalog_items_2024",
            "columns": [
                {"name": "sku_id", "type": "TEXT"},
                {"name": "product_name", "type": "TEXT"},
                {"name": "published_at", "type": "TIMESTAMP"},
            ],
        }
    )
    context.sources[0]["profile"]["preanalysis"]["candidate_roles"].append(
        {
            "table": "catalog_items_2024",
            "column": "published_at",
            "role": "time",
            "status": "candidate",
            "non_null": 20,
        }
    )

    batch = await generate_semantic_recommendations(
        context,
        [{"source_id": source_id, "tables": ["catalog_items_2024"]}],
        "zh",
        20,
        uuid4(),
        None,
    )

    published_at = next(
        item
        for item in batch.items
        if isinstance(item.definition, DimensionDefinition)
        and item.definition.source.action_column == "published_at"
    )
    assert published_at.definition.business_name == "发布时间"
    assert published_at.definition.synonyms == ["published_at", "表格时间", "发布日期"]
    assert "发布时间" not in published_at.definition.synonyms
    assert published_at.definition.source.table_or_view == "catalog_items_2024"
    table_presentation = next(
        item.definition
        for item in batch.items
        if isinstance(item.definition, ScopePresentationDefinition)
        and item.definition.scope_kind == "table"
    )
    assert table_presentation.business_name == "2024 年商品信息"


@pytest.mark.asyncio
async def test_structure_mode_translates_safe_fields_without_guessing_metrics() -> None:
    context, source_id = _database_context()
    context.sources[0]["profile"]["tables"].append(
        {
            "name": "catalog_items_2024",
            "schema": "public",
            "columns": [
                {"name": "sku_id", "type": "TEXT"},
                {"name": "published_at", "type": "TIMESTAMP"},
                {"name": "quantity", "type": "INTEGER"},
                {"name": "unit_price", "type": "DECIMAL"},
                {"name": "unit_cost", "type": "DECIMAL"},
                {"name": "sales_amount", "type": "DECIMAL"},
            ],
        }
    )

    batch = await generate_semantic_recommendations(
        context,
        [{"source_id": source_id, "tables": ["public.catalog_items_2024"]}],
        "zh",
        50,
        uuid4(),
        None,
        mode="structure",
    )

    published_at = next(
        item
        for item in batch.items
        if isinstance(item.definition, DimensionDefinition)
        and item.definition.source.action_column == "published_at"
    )
    assert published_at.definition.business_name == "发布时间"
    assert "表格时间" in published_at.definition.synonyms
    assert published_at.evidence[0]["metadata_only"] is True
    assert all(
        not isinstance(item.definition, AggregateMetricDefinition | DerivedMetricDefinition)
        for item in batch.items
    )
    assert not any(
        isinstance(item.definition, DimensionDefinition)
        and item.definition.source.action_column
        in {"quantity", "unit_price", "unit_cost", "sales_amount"}
        for item in batch.items
    )
    assert {
        item.definition.scope_kind
        for item in batch.items
        if isinstance(item.definition, ScopePresentationDefinition)
    } == {"source", "table"}


@pytest.mark.asyncio
async def test_structure_inventory_keeps_the_last_wide_table_field_and_chunks_ai() -> None:
    context, source_id = _database_context()
    columns = [{"name": f"attribute_{index:03d}", "type": "VARCHAR"} for index in range(1, 81)]
    context.sources[0]["profile"]["tables"].append(
        {
            "name": "wide_product_attributes",
            "schema": "public",
            "columns": columns,
        }
    )
    chunk_sizes: list[int] = []

    async def enhancer(payload: list[dict[str, object]]) -> list[dict[str, object]]:
        chunk_sizes.append(len(payload))
        return [{"candidate_id": item["candidate_id"]} for item in payload]

    batch = await generate_semantic_recommendations(
        context,
        [{"source_id": source_id, "tables": ["wide_product_attributes"]}],
        "zh",
        242,
        uuid4(),
        enhancer,
        mode="structure",
    )

    field_candidates = [
        item for item in batch.items if isinstance(item.definition, DimensionDefinition)
    ]
    assert len(field_candidates) == 80
    assert any(item.definition.source.action_column == "attribute_080" for item in field_candidates)
    assert chunk_sizes == [50, 32]
    assert batch.generated_by == "ai"


@pytest.mark.asyncio
async def test_one_invalid_ai_chunk_falls_back_for_the_whole_wide_table() -> None:
    context, source_id = _database_context()
    context.sources[0]["profile"]["tables"].append(
        {
            "name": "wide_product_attributes",
            "columns": [
                {"name": f"attribute_{index:03d}", "type": "VARCHAR"} for index in range(1, 81)
            ],
        }
    )
    call_count = 0

    async def enhancer(payload: list[dict[str, object]]) -> list[dict[str, object]]:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            return [{"candidate_id": "unknown-candidate"}]
        return [
            {
                "candidate_id": item["candidate_id"],
                "business_name": f"AI {item['business_name']}",
            }
            for item in payload
        ]

    batch = await generate_semantic_recommendations(
        context,
        [{"source_id": source_id, "tables": ["wide_product_attributes"]}],
        "zh",
        242,
        uuid4(),
        enhancer,
        mode="structure",
    )

    assert call_count == 2
    assert batch.generated_by == "preflight"
    assert all(
        not any(
            evidence.get("kind") == "model_presentation_enhancement" for evidence in item.evidence
        )
        for item in batch.items
    )


@pytest.mark.asyncio
async def test_relationship_mode_only_uses_catalog_verified_foreign_keys() -> None:
    context, source_id = _database_context()

    declared = await generate_semantic_recommendations(
        context,
        [{"source_id": source_id, "tables": ["orders", "customers"]}],
        "zh",
        50,
        uuid4(),
        None,
        mode="relationships",
    )

    assert len(declared.items) == 1
    assert isinstance(declared.items[0].definition, RelationshipDefinition)
    assert declared.items[0].evidence[0]["catalog_verified"] is True
    assert declared.items[0].evidence[0]["requires_value_validation"] is True

    context.sources[0]["profile"]["tables"].extend(
        [
            {
                "name": "alpha",
                "columns": [{"name": "customer_id", "type": "BIGINT"}],
            },
            {
                "name": "beta",
                "columns": [{"name": "customer_id", "type": "BIGINT"}],
            },
        ]
    )
    same_name_only = await generate_semantic_recommendations(
        context,
        [{"source_id": source_id, "tables": ["alpha", "beta"]}],
        "zh",
        50,
        uuid4(),
        None,
        mode="relationships",
    )
    assert same_name_only.items == []


@pytest.mark.asyncio
async def test_relationship_mode_reads_foreign_keys_from_profiled_table_catalog() -> None:
    context, source_id = _database_context()
    profile = context.sources[0]["profile"]
    profile["preanalysis"]["relationship_evidence"] = []
    orders, customers = profile["tables"][:2]
    orders["constraint_metadata_status"] = "available"
    orders["foreign_keys"] = [
        {
            "name": "orders_customer_id_fkey",
            "columns": ["customer_id"],
            "referenced_schema": "public",
            "referenced_table": "customers",
            "referenced_columns": ["id"],
        }
    ]
    customers["constraint_metadata_status"] = "available"
    customers["foreign_keys"] = []

    batch = await generate_semantic_recommendations(
        context,
        [{"source_id": source_id, "tables": ["orders", "customers"]}],
        "zh",
        50,
        uuid4(),
        None,
        mode="relationships",
    )

    assert len(batch.items) == 1
    relationship = batch.items[0].definition
    assert isinstance(relationship, RelationshipDefinition)
    assert relationship.left.table_or_view == "public.orders"
    assert relationship.right.table_or_view == "public.customers"


@pytest.mark.asyncio
async def test_per_table_inventory_omits_source_until_one_final_source_pass() -> None:
    context, source_id = _database_context()

    per_table = [
        await generate_semantic_recommendations(
            context,
            [{"source_id": source_id, "tables": [table]}],
            "zh",
            242,
            uuid4(),
            None,
            mode="structure",
            include_source_presentation=False,
        )
        for table in ("orders", "customers", "payments")
    ]
    assert not any(
        isinstance(item.definition, ScopePresentationDefinition)
        and item.definition.scope_kind == "source"
        for batch in per_table
        for item in batch.items
    )

    source_pass = await generate_semantic_recommendations(
        context,
        [
            {
                "source_id": source_id,
                "tables": ["orders", "customers", "payments"],
            }
        ],
        "zh",
        50,
        uuid4(),
        None,
        mode="presentation",
        include_table_presentations=False,
    )
    source_candidates = [
        item
        for item in source_pass.items
        if isinstance(item.definition, ScopePresentationDefinition)
        and item.definition.scope_kind == "source"
    ]
    assert len(source_candidates) == 1
    assert len(source_candidates[0].evidence[0]["recommendation_context"]["source_relations"]) == 3


@pytest.mark.asyncio
async def test_unknown_abbreviation_gets_readable_unresolved_label() -> None:
    context, source_id = _database_context()
    context.sources[0]["profile"]["tables"].append(
        {
            "name": "catalog_items_2024",
            "columns": [{"name": "unknown_code_a", "type": "TEXT"}],
        }
    )
    context.sources[0]["profile"]["preanalysis"]["candidate_roles"].append(
        {
            "table": "catalog_items_2024",
            "column": "unknown_code_a",
            "role": "dimension",
            "status": "candidate",
            "non_null": 20,
            "unique": 4,
        }
    )

    batch = await generate_semantic_recommendations(
        context,
        [{"source_id": source_id, "tables": ["catalog_items_2024"]}],
        "zh",
        20,
        uuid4(),
        None,
    )
    candidate = next(
        item
        for item in batch.items
        if isinstance(item.definition, DimensionDefinition)
        and item.definition.source.action_column == "unknown_code_a"
    )
    assert candidate.definition.business_name == "UNKNOWN 编码 A"
    assert candidate.definition.description == "名称和业务含义待核对。"
    assert candidate.definition.example_questions == []
    assert candidate.definition.synonyms == ["unknown_code_a"]
    assert candidate.confidence <= 0.3


@pytest.mark.asyncio
async def test_unknown_label_suffix_is_translated_without_inventing_abbreviation() -> None:
    context, source_id = _database_context()
    context.sources[0]["profile"]["tables"].append(
        {
            "name": "catalog_items_2024",
            "columns": [{"name": "unknown_label_a", "type": "TEXT"}],
        }
    )
    context.sources[0]["profile"]["preanalysis"]["candidate_roles"].append(
        {
            "table": "catalog_items_2024",
            "column": "unknown_label_a",
            "role": "dimension",
            "status": "candidate",
            "non_null": 20,
            "unique": 4,
        }
    )

    batch = await generate_semantic_recommendations(
        context,
        [{"source_id": source_id, "tables": ["catalog_items_2024"]}],
        "zh",
        20,
        uuid4(),
        None,
    )
    candidate = next(
        item
        for item in batch.items
        if isinstance(item.definition, DimensionDefinition)
        and item.definition.source.action_column == "unknown_label_a"
    )
    assert candidate.definition.business_name == "UNKNOWN 标签 A"
    assert candidate.definition.example_questions == []
    assert candidate.definition.synonyms == ["unknown_label_a"]
    assert candidate.confidence <= 0.3


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["unknown", "duplicate"])
async def test_invalid_enhancer_ids_fall_back_as_a_whole(mode: str) -> None:
    context, source_id = _orders_context()
    batch_id = uuid4()
    deterministic = await generate_semantic_recommendations(
        context, [{"source_id": source_id}], "zh", 6, batch_id, None
    )

    def invalid(payload: list[dict[str, object]]) -> list[dict[str, object]]:
        result = [{"candidate_id": item["candidate_id"]} for item in payload]
        if mode == "unknown":
            result[0] = {"candidate_id": "not-an-allowed-candidate"}
        else:
            result[0] = {"candidate_id": result[1]["candidate_id"]}
        return result

    fallback = await generate_semantic_recommendations(
        context, [{"source_id": source_id}], "zh", 6, batch_id, invalid
    )

    assert fallback.generated_by == "preflight"
    assert [item.model_dump(mode="json") for item in fallback.items] == [
        item.model_dump(mode="json") for item in deterministic.items
    ]
