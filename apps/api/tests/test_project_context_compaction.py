"""Runtime prompt context keeps value guidance without leaking raw source samples."""

from __future__ import annotations

import json

from app.services.project_context import ProjectRuntimeContext


def test_public_summary_compacts_database_profiles_and_omits_raw_sample_rows() -> None:
    candidate_roles = [
        {
            "table": "orders",
            "column": f"column_{index}",
            "role": "dimension",
            "missing": 0,
            "sample_unique": 2,
            "top_values": [
                {"value": f"known-{value_index}", "count": 1} for value_index in range(20)
            ],
        }
        for index in range(300)
    ]
    context = ProjectRuntimeContext(
        name="数据库画像",
        sources=[
            {
                "id": "source-1",
                "name": "订单库",
                "kind": "connection",
                "format": "sqlite",
                "status": "ready",
                "connection_name": "订单库",
                "profile": {
                    "summary": "已完成只读画像",
                    "sample": [
                        {"customer_email": "raw-person@example.test", "secret": "raw-secret"}
                    ],
                    "tables": [
                        {
                            "name": f"table_{table_index}",
                            "schema": "main",
                            "kind": "table",
                            "column_metadata_status": "available",
                            "constraint_metadata_status": "available",
                            "primary_key": {
                                "name": "pk_orders",
                                "columns": ["field_0"],
                            },
                            "unique_constraints": [],
                            "foreign_keys": (
                                [
                                    {
                                        "name": "fk_store",
                                        "columns": ["field_1"],
                                        "referenced_table": "stores",
                                        "referenced_columns": ["id"],
                                    }
                                ]
                                if table_index == 0
                                else []
                            ),
                            "columns": [
                                {"name": f"field_{column_index}", "type": "TEXT"}
                                for column_index in range(100)
                            ],
                        }
                        for table_index in range(30)
                    ],
                    "preanalysis": {
                        "read_only": True,
                        "shape": {"tables": 30, "profiled_tables": 24},
                        "candidate_roles": candidate_roles,
                        "relationship_evidence": [
                            {
                                "kind": "declared_foreign_key",
                                "state": "evidence_only",
                                "validity": "unverified",
                                "catalog_verified": True,
                                "binding_complete": True,
                                "automatic_confirmation": False,
                                "requires_value_validation": True,
                                "constraint_name": "fk_store",
                                "source": {
                                    "schema": "main",
                                    "table": "orders",
                                    "columns": ["store_id"],
                                },
                                "target": {
                                    "schema": "main",
                                    "table": "stores",
                                    "columns": ["id"],
                                },
                            }
                        ],
                        "tables": [
                            {
                                "table": "orders",
                                "candidate_roles": candidate_roles,
                                "sample": {
                                    "rows_profiled": 256,
                                    "truncated": True,
                                },
                            }
                        ],
                    },
                },
            }
        ],
    )

    public_source = context.public_summary()["sources"][0]
    serialized = json.dumps(public_source, ensure_ascii=False)

    assert "raw-person@example.test" not in serialized
    assert "raw-secret" not in serialized
    assert len(public_source["preanalysis"]["candidate_roles"]) == 240
    assert len(public_source["preanalysis"]["candidate_roles"][0]["top_values"]) == 12
    assert len(public_source["profile"]["tables"]) == 24
    assert len(public_source["profile"]["tables"][0]["columns"]) == 80
    assert public_source["profile"]["tables"][0]["primary_key"]["columns"] == ["field_0"]
    assert public_source["profile"]["tables"][0]["foreign_keys"][0]["name"] == "fk_store"
    relationship = public_source["preanalysis"]["relationship_evidence"][0]
    assert relationship["state"] == "evidence_only"
    assert relationship["automatic_confirmation"] is False
    assert relationship["requires_value_validation"] is True
    assert public_source["preanalysis"]["tables"][0]["sample"] == {
        "rows_profiled": 256,
        "truncated": True,
    }


def _relationship(index: int, *, target: bool = False) -> dict[str, object]:
    table = "priority_stores" if target else f"table_{index:04d}"
    return {
        "id": f"relationship-{index}",
        "key": f"relationship_candidate:{index:04d}",
        "value": "可能的关联字段",
        "state": "candidate",
        "confidence": 0.55,
        "validity": "unverified",
        "execution_state": "definition_only",
        "definition": {
            "left": {
                "source_logical_name": "订单库",
                "table_or_view": "orders",
                "column": "store_id",
            },
            "right": {
                "source_logical_name": "门店库",
                "table_or_view": table,
                "column": "id",
            },
        },
    }


def test_public_summary_budgets_large_semantic_collections_and_ranks_query_match() -> None:
    relationships = [_relationship(index, target=index == 791) for index in range(792)]
    context = ProjectRuntimeContext(
        confirmed_knowledge=[
            {
                "id": f"confirmed-{index}",
                "key": f"metric:{index:03d}",
                "value": f"已确认指标 {index}",
                "state": "confirmed",
                "validity": "active",
                "confidence": 1,
            }
            for index in range(80)
        ],
        candidate_knowledge=[
            {
                "id": f"candidate-{index}",
                "key": f"dimension:{index:03d}",
                "value": f"候选维度 {index}",
                "state": "candidate",
                "validity": "active",
                "confidence": 0.7,
            }
            for index in range(80)
        ],
        executable_relationships={
            f"verified:{index:03d}": {
                **_relationship(index),
                "state": "confirmed",
                "validity": "active",
                "execution_state": "verified",
            }
            for index in range(80)
        },
        candidate_relationships=relationships,
    )

    summary = context.public_summary(query="priority stores")

    assert len(summary["candidate_relationships"]) == 12
    assert summary["candidate_relationships"][0]["key"] == "relationship_candidate:0791"
    assert len(summary["confirmed_knowledge"]) == 48
    assert len(summary["candidate_knowledge"]) == 24
    assert len(summary["confirmed_relationships"]) == 32
    assert summary["semantic_context"] == {
        "query_scoped": True,
        "confirmed_knowledge": {"total": 80, "included": 48, "truncated": True},
        "candidate_knowledge": {"total": 80, "included": 24, "truncated": True},
        "confirmed_relationships": {"total": 80, "included": 32, "truncated": True},
        "candidate_relationships": {"total": 792, "included": 12, "truncated": True},
    }


def test_public_summary_never_crops_explicit_relationship_validation_contract() -> None:
    required = [
        {
            "semantic_entry_id": f"semantic-{index}",
            "expected_active_revision_id": f"revision-{index}",
            "relationship_key": f"required:{index}",
            "definition_hash": f"hash-{index}",
            "value": f"必须验证 {index}",
            "definition": {"left": {"column": "id"}, "right": {"column": "id"}},
        }
        for index in range(25)
    ]
    context = ProjectRuntimeContext(
        candidate_relationships=[_relationship(index) for index in range(792)],
        required_relationship_validations=required,
    )

    summary = context.public_summary(query="没有命中的问题")

    assert len(summary["candidate_relationships"]) == 12
    assert len(summary["required_relationship_validations"]) == 25
    assert [item["semantic_entry_id"] for item in summary["required_relationship_validations"]] == [
        item["semantic_entry_id"] for item in required
    ]
    assert (
        summary["required_relationship_validations"][-1]["definition"] == required[-1]["definition"]
    )
