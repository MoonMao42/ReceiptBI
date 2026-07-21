from pathlib import Path
from uuid import uuid4

import pytest

from app.services.data_preflight import run_preflight
from app.services.sanitation_contract import (
    SANITATION_CONTRACT_VERSION,
    SanitationContractError,
    canonicalize_sanitation_operations,
    executable_sanitation_operations,
)


def _legacy_recipe() -> list[dict]:
    source_id = str(uuid4())
    recipe_id = str(uuid4())
    return [
        {
            "operation": "replay_prior_recipe",
            "source_id": source_id,
            "recipe_id": recipe_id,
        },
        {"operation": "replay_imported_recipe", "template": "月度订单整理"},
        {"operation": "reapply_recipe", "recipe_id": recipe_id},
        {"operation": "select_sheet", "sheet": "订单明细"},
        {"operation": "select_header", "row": 3},
        {
            "operation": "normalize_column_names",
            "columns": ["order_id", "amount"],
        },
        {"operation": "drop_empty", "rows": 2, "columns": 1},
        {"operation": "exclude_summary_rows", "count": 1},
        {"operation": "drop_exact_duplicates", "count": 4},
        {"operation": "trim_text", "column": "order_id"},
        {"operation": "normalize_currency", "column": "amount"},
        {"operation": "normalize_datetime", "column": "order_date"},
    ]


def test_legacy_recipe_is_upgraded_to_explicit_v1_contract() -> None:
    canonical = canonicalize_sanitation_operations(_legacy_recipe())

    assert all(
        operation["contract_version"] == SANITATION_CONTRACT_VERSION
        for operation in canonical
    )
    by_name = {operation["operation"]: operation for operation in canonical}
    assert by_name["trim_text"]["error_policy"] == "preserve_original"
    assert by_name["normalize_currency"]["error_policy"] == "set_null"
    assert by_name["normalize_datetime"]["error_policy"] == "set_null"


@pytest.mark.parametrize("value", [False, True, 1, -1, "未知", 0.0])
def test_regular_sanitation_contract_keeps_bounded_scalar_fill_values(value) -> None:
    canonical = canonicalize_sanitation_operations(
        [{"operation": "fill_missing", "column": "amount", "value": value}]
    )

    assert canonical[0]["value"] == value


def test_provenance_is_validated_but_never_returned_to_executor() -> None:
    executable = executable_sanitation_operations(_legacy_recipe())

    names = {operation["operation"] for operation in executable}
    assert "replay_prior_recipe" not in names
    assert "replay_imported_recipe" not in names
    assert "reapply_recipe" not in names
    assert names == {
        "select_sheet",
        "select_header",
        "normalize_column_names",
        "drop_empty",
        "exclude_summary_rows",
        "drop_exact_duplicates",
        "trim_text",
        "normalize_currency",
        "normalize_datetime",
    }


@pytest.mark.parametrize(
    "operation",
    [
        {"operation": "python", "code": "open('/tmp/x', 'w')"},
        {"operation": "drop_rows", "expression": "amount < 0"},
        {
            "operation": "normalize_currency",
            "column": "amount",
            "sql": "DROP TABLE orders",
        },
        {
            "operation": "normalize_datetime",
            "column": "order_date",
            "contract_version": 2,
        },
        {
            "operation": "trim_text",
            "column": "name",
            "error_policy": "execute_expression",
        },
    ],
)
def test_unknown_operations_future_versions_and_extra_code_fail_closed(
    operation: dict,
) -> None:
    with pytest.raises(SanitationContractError):
        canonicalize_sanitation_operations([operation])


@pytest.mark.parametrize(
    "operation",
    [
        {"operation": "select_sheet", "sheet": "   "},
        {"operation": "select_header", "row": 0},
        {"operation": "drop_empty", "rows": -1, "columns": 0},
        {"operation": "normalize_currency", "column": ""},
        {"operation": "normalize_column_names", "columns": ["id", "id"]},
        {"operation": "reapply_recipe", "recipe_id": "not-a-uuid"},
    ],
)
def test_invalid_operation_parameters_fail_closed(operation: dict) -> None:
    with pytest.raises(SanitationContractError):
        canonicalize_sanitation_operations([operation])


def test_preflight_rejects_invalid_recipe_before_touching_source_or_output(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "working"

    with pytest.raises(SanitationContractError, match="未知操作"):
        run_preflight(
            tmp_path / "missing.csv",
            output_dir,
            recipe_operations=[{"operation": "run_python", "code": "pass"}],
        )

    assert not output_dir.exists()


def test_preflight_persists_only_canonical_versioned_operations(tmp_path: Path) -> None:
    source = tmp_path / "orders.csv"
    source.write_text(
        "order_id,amount,order_date\n"
        " 001 , ￥12.50 ,2026-07-01\n"
        " 002 , ￥10.00 ,2026-07-02\n",
        encoding="utf-8",
    )

    result = run_preflight(source, tmp_path / "working")

    assert result.operations
    assert all(operation["contract_version"] == 1 for operation in result.operations)
    field_operations = {
        (operation["operation"], operation.get("column")): operation
        for operation in result.operations
        if operation["operation"]
        in {"trim_text", "normalize_currency", "normalize_datetime"}
    }
    assert field_operations[("normalize_currency", "amount")]["error_policy"] == "set_null"
    assert field_operations[("normalize_datetime", "order_date")]["error_policy"] == "set_null"
    assert field_operations[("trim_text", "amount")]["error_policy"] == "preserve_original"
