"""Visualization helpers for SQL result rendering."""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger()


def validate_chart_config(config: dict[str, Any]) -> bool:
    """Validates chart configuration structure.

    Args:
        config: Chart configuration dict to validate

    Returns:
        True if config is valid, False otherwise
    """
    if not isinstance(config, dict):
        return False

    # Check required fields
    chart_type = config.get("type")
    if not chart_type or not isinstance(chart_type, str):
        return False

    # Valid chart types
    valid_types = {"bar", "line", "pie", "scatter", "area", "table"}
    if chart_type not in valid_types:
        return False

    return True


def build_chart_from_config(
    config: dict[str, Any],
    data: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Build a chart payload from an explicit model-provided config."""
    if not data:
        return None

    chart_type = config.get("type", "bar")
    title = config.get("title", "")
    x_key = config.get("xKey")
    y_keys = list(config.get("yKeys", []))

    columns = list(data[0].keys())
    if not x_key or x_key not in columns:
        x_key = columns[0]

    if not y_keys:
        for column in columns:
            if column == x_key:
                continue
            try:
                float(data[0][column])
            except (TypeError, ValueError):
                continue
            y_keys.append(column)

    if not y_keys:
        return None

    chart_data = []
    for row in data[:50]:
        item = {"name": str(row.get(x_key, ""))}
        for y_key in y_keys:
            try:
                item[y_key] = float(row.get(y_key, 0))
            except (TypeError, ValueError):
                item[y_key] = 0
        chart_data.append(item)

    return {
        "type": chart_type,
        "title": title,
        "data": chart_data,
        "xKey": "name",
        "yKeys": y_keys,
    }


def generate_visualization(
    data: list[dict[str, Any]],
    query: str,
) -> dict[str, Any] | None:
    """Generate a fallback chart config from query semantics and result data."""
    if not data:
        return None

    columns = list(data[0].keys())
    if len(columns) < 2:
        return None

    x_column = columns[0]
    y_columns: list[str] = []
    for column in columns[1:]:
        try:
            float(data[0][column])
        except (TypeError, ValueError):
            continue
        y_columns.append(column)

    if not y_columns:
        return None

    query_lower = query.lower()
    if any(token in query_lower for token in ("趋势", "trend", "变化", "时间", "time")):
        chart_type = "line"
    elif any(token in query_lower for token in ("占比", "比例", "percentage", "pie")):
        chart_type = "pie"
    else:
        chart_type = "bar"

    chart_data = []
    for row in data[:50]:
        item = {"name": str(row[x_column])}
        for y_column in y_columns:
            try:
                item[y_column] = float(row[y_column])
            except (TypeError, ValueError):
                item[y_column] = 0
        chart_data.append(item)

    return {
        "type": chart_type,
        "data": chart_data,
        "xKey": "name",
        "yKeys": y_columns,
    }


class VisualizationEngine:
    """Orchestrator for chart generation and visualization configuration.

    Wraps the helper functions for use in service-based architecture.
    Per D-01: Extract visualization concerns into a service module.
    """

    def __init__(self, language: str = "zh"):
        """Initialize VisualizationEngine.

        Args:
            language: Language for error messages ("zh" or "en")
        """
        self.language = language

    async def auto_detect_chart_type(
        self,
        data: list[dict[str, Any]],
        query: str = "",
    ) -> str:
        """Auto-detect appropriate chart type for given data.

        Args:
            data: Query result data
            query: Original query string for semantic analysis

        Returns:
            Chart type: "bar", "line", "pie", "scatter", "area", or "table"
        """
        if not data:
            return "table"

        columns = list(data[0].keys())
        if len(columns) < 2:
            return "table"

        # Check for numeric columns
        numeric_cols = []
        for col in columns[1:]:
            try:
                float(data[0][col])
                numeric_cols.append(col)
            except (TypeError, ValueError):
                continue

        if not numeric_cols:
            return "table"

        # Detect chart type based on query semantics
        query_lower = query.lower()
        if any(token in query_lower for token in ("趋势", "trend", "变化", "时间", "time")):
            return "line"
        elif any(token in query_lower for token in ("占比", "比例", "percentage", "pie")):
            return "pie"
        else:
            return "bar"

    async def generate_chart(
        self,
        config: dict[str, Any],
        data: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Generate chart from explicit configuration.

        Per D-04: Return None on invalid config, don't raise.

        Args:
            config: Chart configuration with type, xKey, yKeys
            data: Chart data rows

        Returns:
            Chart payload or None if validation fails
        """
        if not validate_chart_config(config):
            logger.warning("Invalid chart configuration", config=config)
            return None

        result = build_chart_from_config(config, data)
        if result:
            logger.info("Chart generated", chart_type=result.get("type"))
        return result

    def emit_visualization_event(
        self,
        chart_type: str,
        data: list[dict[str, Any]],
        title: str = "",
    ) -> dict[str, Any]:
        """Emit a visualization event for streaming response.

        Args:
            chart_type: Type of chart to generate
            data: Chart data
            title: Optional chart title

        Returns:
            SSE event payload
        """
        if not data:
            return {
                "type": "visualization",
                "chart_type": "table",
                "data": [],
            }

        return {
            "type": "visualization",
            "chart_type": chart_type,
            "title": title,
            "data": data,
        }
