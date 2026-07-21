from __future__ import annotations

from types import SimpleNamespace

from app.services.semantic_adapter import (
    _SEMANTIC_INSTRUCTION_CHAR_BUDGET,
    SemanticEngineAdapter,
)


def _large_adapter() -> SemanticEngineAdapter:
    models: list[dict[str, object]] = []
    relationships: dict[str, dict[str, object]] = {}
    for model_index in range(220):
        columns: list[dict[str, object]] = []
        for column_index in range(3):
            key = f"ordinary_relationship_{model_index:04d}_{column_index}"
            relationships[key] = {
                "key": key,
                "state": "confirmed",
                "execution_state": "verified",
                "definition": {"business_term": f"ordinary_{model_index:04d}"},
            }
            columns.append(
                {
                    "name": f"derived_field_{model_index:04d}_{column_index}",
                    "isCalculated": True,
                    "properties": {"relationshipKey": key},
                }
            )
            columns.append(
                {
                    "name": f"logical_field_{model_index:04d}_{column_index}",
                    "properties": {
                        "physicalName": (
                            f"physical field {model_index:04d} {column_index} with spaces"
                        )
                    },
                }
            )
        models.append({"name": f"ordinary_model_{model_index:04d}", "columns": columns})

    relationships["locked_revenue_relationship"] = {
        "key": "locked_revenue_relationship",
        "state": "locked",
        "execution_state": "verified",
        "definition": {"business_term": "revenue income 营收"},
    }
    models.append(
        {
            "name": "revenue_model",
            "columns": [
                {
                    "name": "revenue_verified_total",
                    "isCalculated": True,
                    "properties": {"relationshipKey": "locked_revenue_relationship"},
                },
                {
                    "name": "revenue_logical_name",
                    "properties": {"physicalName": "revenue physical name"},
                },
            ],
        }
    )

    adapter = SemanticEngineAdapter.__new__(SemanticEngineAdapter)
    adapter.project = SimpleNamespace(executable_relationships=relationships)
    adapter._sessions = {"warehouse": object()}
    adapter._manifests = {
        "warehouse": {
            "models": models,
            "relationships": [],
            "views": [],
        }
    }
    return adapter


def test_semantic_adapter_instructions_are_bounded_and_keep_trusted_relevant_items():
    adapter = _large_adapter()

    instructions = adapter.instructions(query="revenue 营收")

    assert len(instructions) <= _SEMANTIC_INSTRUCTION_CHAR_BUDGET
    assert "warehouse: revenue_model.revenue_verified_total" in instructions
    assert (
        "warehouse: revenue_model.revenue_logical_name 对应物理字段 revenue physical name"
    ) in instructions
    assert "以上清单已按验证状态和当前问题筛选" in instructions
    assert "按需解析" in instructions
    assert "warehouse: ordinary_model_0219.derived_field_0219_2" not in instructions


def test_semantic_adapter_instruction_selection_is_deterministic():
    adapter = _large_adapter()

    first = adapter.instructions(query="revenue")
    second = adapter.instructions(query="revenue")

    assert first == second
