"""Contracts for explicit, bounded semantic inventory jobs."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.workspace import (
    SemanticInventoryJobItemResponse,
    SemanticInventoryJobRequest,
)


def test_structure_inventory_allows_all_tables_and_normalizes_explicit_names() -> None:
    all_tables = SemanticInventoryJobRequest(
        locale="zh",
        tables=[],
        depth="structure",
    )
    assert all_tables.tables == []

    selected = SemanticInventoryJobRequest(
        locale="en",
        tables=[" public.orders ", "public.customers"],
        depth="sampled",
    )
    assert selected.tables == ["public.orders", "public.customers"]


def test_sampled_inventory_requires_an_explicit_unique_selection() -> None:
    with pytest.raises(ValidationError, match="sampled inventory requires explicit tables"):
        SemanticInventoryJobRequest(locale="zh", tables=[], depth="sampled")

    with pytest.raises(ValidationError, match="inventory tables must be unique"):
        SemanticInventoryJobRequest(
            locale="zh",
            tables=["Sales.Orders", "sales.orders"],
            depth="structure",
        )


def test_inventory_item_response_uses_public_table_name_not_storage_details() -> None:
    now = datetime.now(UTC)
    stored_item = SimpleNamespace(
        id=uuid4(),
        ordinal=0,
        table_name="public.orders",
        status="succeeded",
        phase="complete",
        attempt_count=1,
        retryable=False,
        code=None,
        message=None,
        recommendation_batch_id=uuid4(),
        candidate_count=4,
        started_at=now,
        completed_at=now,
        profile_result={"columns": [{"name": "secret_internal_name"}]},
    )

    response = SemanticInventoryJobItemResponse.model_validate(stored_item)
    payload = response.model_dump(mode="json")

    assert payload["table"] == "public.orders"
    assert "table_name" not in payload
    assert "profile_result" not in payload
