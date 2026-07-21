from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from pydantic_ai import models
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.core.config import settings
from app.models import SSEEventType
from app.services import analyst_runtime
from app.services.analyst_runtime import (
    PydanticAnalystRuntime,
    StructuredQueryFilter,
    StructuredQueryMetric,
    StructuredQuerySort,
    _compile_structured_query,
    _query_project_file_rows,
    _resolve_structured_source,
    _validate_read_only,
)
from app.services.project_context import ProjectRuntimeContext


def _file_source(path: Path) -> dict:
    return {
        "id": "orders-source",
        "name": "线上订单",
        "kind": "file",
        "format": "parquet",
        "view_name": "online_orders",
        "working_uri": str(path),
        "profile": {
            "logical_name": "订单明细",
            "schema": {
                "columns": [
                    {"name": "商品品类", "dtype": "object"},
                    {"name": "实付金额", "dtype": "float64"},
                    {"name": "退款状态", "dtype": "object"},
                ]
            },
        },
    }


def test_structured_query_compiles_real_schema_and_executes_file(tmp_path: Path):
    source_path = tmp_path / "orders.parquet"
    pd.DataFrame(
        [
            {"商品品类": "办公用品", "实付金额": 32.0, "退款状态": "否"},
            {"商品品类": "办公用品", "实付金额": 30.0, "退款状态": "否"},
            {"商品品类": "耗材", "实付金额": 28.0, "退款状态": "已退款"},
        ]
    ).to_parquet(source_path, index=False)
    source = _file_source(source_path)

    sql, plan = _compile_structured_query(
        source,
        table=None,
        dimensions=["商品 品类"],
        metrics=[StructuredQueryMetric(operation="sum", column="实付金额", alias="销售额")],
        filters=[StructuredQueryFilter(column="退款状态", operator="eq", value="否")],
        sort=[StructuredQuerySort(field="销售额", direction="desc")],
        limit=100,
    )
    rows, truncated, available = _query_project_file_rows(
        [source], sql, tmp_path / "project"
    )

    assert plan["table"] == "online_orders"
    assert plan["table_or_view"] == "online_orders"
    assert plan["query_scope"] == "aggregated"
    assert plan["dimensions"] == ["商品品类"]
    assert rows == [{"商品品类": "办公用品", "销售额": 62.0}]
    assert truncated is False
    assert available == ["online_orders"]


def test_structured_query_scope_distinguishes_full_filtered_and_aggregated(tmp_path: Path):
    source = _file_source(tmp_path / "orders.parquet")
    _, full_plan = _compile_structured_query(
        source,
        table=None,
        dimensions=["商品品类", "实付金额", "退款状态"],
        metrics=[],
        filters=[],
        sort=[],
        limit=100,
    )
    _, filtered_plan = _compile_structured_query(
        source,
        table=None,
        dimensions=["商品品类", "实付金额"],
        metrics=[],
        filters=[StructuredQueryFilter(column="退款状态", operator="eq", value="否")],
        sort=[],
        limit=100,
    )
    _, aggregated_plan = _compile_structured_query(
        source,
        table=None,
        dimensions=["商品品类"],
        metrics=[StructuredQueryMetric(operation="sum", column="实付金额")],
        filters=[],
        sort=[],
        limit=100,
    )

    assert full_plan["query_scope"] == "full"
    assert filtered_plan["query_scope"] == "filtered"
    assert aggregated_plan["query_scope"] == "aggregated"


def test_structured_query_escapes_values_and_rejects_unknown_schema_names():
    source = {
        "id": "shop-db",
        "name": "门店库",
        "kind": "connection",
        "format": "mysql",
        "profile": {
            "tables": [
                {
                    "name": "order-items",
                    "columns": [
                        {"name": "store name", "type": "varchar"},
                        {"name": "amount", "type": "decimal"},
                    ],
                }
            ]
        },
    }
    sql, _ = _compile_structured_query(
        source,
        table="order items",
        dimensions=["store_name"],
        metrics=[StructuredQueryMetric(operation="sum", column="amount")],
        filters=[
            StructuredQueryFilter(
                column="store name",
                operator="eq",
                value="店铺'精选",
            )
        ],
        sort=[],
        limit=50,
    )

    assert "FROM `order-items`" in sql
    assert "`store name`" in sql
    assert "'店铺''精选'" in sql
    _validate_read_only(sql)

    with pytest.raises(ValueError, match="找不到汇总字段"):
        _compile_structured_query(
            source,
            table=None,
            dimensions=[],
            metrics=[StructuredQueryMetric(operation="sum", column="invented_revenue")],
            filters=[],
            sort=[],
            limit=50,
        )


@pytest.mark.parametrize(
    "unsafe_value",
    [
        "店铺\\' OR 1=1 #",
        "店铺#绕过",
        "店铺-- 注释",
        "店铺/*注释*/",
        "店铺; SELECT 1",
        "店铺\n下一行",
    ],
)
def test_structured_query_rejects_unsafe_mysql_literals(unsafe_value: str):
    source = {
        "id": "shop-db",
        "name": "门店库",
        "kind": "connection",
        "format": "mysql",
        "profile": {
            "tables": [
                {
                    "name": "shops",
                    "columns": [{"name": "store_name", "type": "varchar"}],
                }
            ]
        },
    }

    with pytest.raises(ValueError, match="不安全字符|无效字符"):
        _compile_structured_query(
            source,
            table=None,
            dimensions=["store_name"],
            metrics=[],
            filters=[
                StructuredQueryFilter(column="store_name", operator="eq", value=unsafe_value)
            ],
            sort=[],
            limit=50,
        )


@pytest.mark.parametrize("operator", ["in", "not_in"])
def test_structured_query_rejects_null_inside_list_filter(operator: str):
    source = _file_source(Path("orders.parquet"))

    with pytest.raises(ValueError, match="列表不能包含空值.*is_null.*not_null"):
        _compile_structured_query(
            source,
            table=None,
            dimensions=["商品品类"],
            metrics=[],
            filters=[
                StructuredQueryFilter(
                    column="退款状态",
                    operator=operator,
                    value=["否", None],
                )
            ],
            sort=[],
            limit=50,
        )


@pytest.mark.parametrize("operation", ["sum", "avg"])
def test_structured_query_rejects_non_numeric_or_unknown_metric_types(operation: str):
    source = _file_source(Path("orders.parquet"))

    with pytest.raises(ValueError, match="必须是预检明确识别的数值字段.*object"):
        _compile_structured_query(
            source,
            table=None,
            dimensions=[],
            metrics=[StructuredQueryMetric(operation=operation, column="商品品类")],
            filters=[],
            sort=[],
            limit=50,
        )

    source["profile"]["schema"]["columns"].append({"name": "口径待定"})
    with pytest.raises(ValueError, match="必须是预检明确识别的数值字段.*unknown"):
        _compile_structured_query(
            source,
            table=None,
            dimensions=[],
            metrics=[StructuredQueryMetric(operation=operation, column="口径待定")],
            filters=[],
            sort=[],
            limit=50,
        )


def test_structured_source_resolution_accepts_product_names_but_rejects_ambiguity(
    tmp_path: Path,
):
    first = _file_source(tmp_path / "first.parquet")
    assert _resolve_structured_source([first], "订单明细") is first
    second = {
        **_file_source(tmp_path / "second.parquet"),
        "id": "orders-source-2",
        "name": "线上订单",
    }
    with pytest.raises(ValueError, match="不唯一"):
        _resolve_structured_source([first, second], "线上订单")


@pytest.mark.asyncio
async def test_agent_structured_query_is_executed_validated_and_bound_to_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "WORKSPACE_ROOT", tmp_path / "projects")
    source_path = tmp_path / "orders.parquet"
    pd.DataFrame(
        [
            {"商品品类": "办公用品", "实付金额": 32.0, "退款状态": "否"},
            {"商品品类": "办公用品", "实付金额": 30.0, "退款状态": "否"},
            {"商品品类": "耗材", "实付金额": 28.0, "退款状态": "已退款"},
        ]
    ).to_parquet(source_path, index=False)
    source = _file_source(source_path)
    calls = 0

    def model(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        nonlocal calls
        calls += 1
        if calls == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "query_source_data",
                        {
                            "purpose": "按品类核对有效销售额",
                            "result_name": "category_sales",
                            "source_id": "订单明细",
                            "dimensions": ["商品品类"],
                            "metrics": [
                                {
                                    "operation": "sum",
                                    "column": "实付金额",
                                    "alias": "销售额",
                                }
                            ],
                            "filters": [
                                {"column": "退款状态", "operator": "eq", "value": "否"}
                            ],
                            "sort": [{"field": "销售额", "direction": "desc"}],
                            "limit": 100,
                        },
                    )
                ]
            )
        if calls == 2:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "validate_result",
                        {
                            "result_name": "category_sales",
                            "purpose": "核对最终品类汇总",
                            "key_columns": ["商品品类"],
                            "numeric_columns": ["销售额"],
                        },
                    )
                ]
            )
        return ModelResponse(
            parts=[
                ToolCallPart(
                    info.output_tools[0].name,
                    {
                        "status": "completed",
                        "title": "有效销售额",
                        "summary": "办公用品有效销售额为 62。",
                        "primary_result": "category_sales",
                        "metrics": [{"label": "办公用品销售额", "value": "62"}],
                        "visualization": {
                            "type": "bar",
                            "title": "品类有效销售额",
                            "result_name": "category_sales",
                            "xKey": "商品品类",
                            "yKeys": ["销售额"],
                        },
                    },
                )
            ]
        )

    monkeypatch.setattr(models, "ALLOW_MODEL_REQUESTS", False)
    monkeypatch.setattr(
        analyst_runtime,
        "build_pydantic_model",
        lambda _config: FunctionModel(model),
    )
    runtime = PydanticAnalystRuntime(
        model_config={},
        project_context=ProjectRuntimeContext(name="销售项目", sources=[source]),
    )

    events = [event async for event in runtime.execute(query="比较各商品品类有效销售额")]
    result = next(event for event in events if event.type == SSEEventType.RESULT)

    assert [item["kind"] for item in runtime.deps.tool_history] == [
        "structured_query",
        "validation",
    ]
    assert runtime.deps.dataframes["category_sales"] == [
        {"商品品类": "办公用品", "销售额": 62.0}
    ]
    assert runtime.deps.replay_journal[0]["op"] == "query_source_data"
    assert runtime.deps.result_metadata["category_sales"]["source_id"] == "orders-source"
    assert runtime.deps.result_metadata["category_sales"]["table_or_view"] == "online_orders"
    assert runtime.deps.result_metadata["category_sales"]["query_scope"] == "aggregated"
    assert runtime.deps.result_metadata["category_sales"]["source_refs"] == [
        {
            "source_id": "orders-source",
            "source_logical_name": "订单明细",
            "source_kind": "file",
            "table_or_view": "online_orders",
            "query_scope": "aggregated",
        }
    ]
    assert result.data["report"]["visualization"]["data"] == [
        {"商品品类": "办公用品", "销售额": 62.0}
    ]
