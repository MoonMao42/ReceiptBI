"""Visualization engine service module.

Extracted from gptme_engine.py for independent chart generation and formatting.
Per D-01 (direct module extraction): move visualization functions.
Per D-04: Specific exception handling for chart config errors.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    pass

logger = structlog.get_logger()


class VisualizationEngine:
    """Handles chart generation and visualization configuration."""

    def __init__(self, language: str = "zh"):
        """Initialize VisualizationEngine.

        Args:
            language: Language for chart labels and messages
        """
        self.language = language

    async def generate_chart(
        self,
        chart_config: dict[str, Any],
        data: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Generate chart payload from configuration and data.

        Per D-04: Specific exception handling for chart config errors.
        Per D-03: Log details to structlog, return None for client if invalid.

        Args:
            chart_config: Chart configuration (type, xKey, yKeys, etc.)
            data: Result data for charting

        Returns:
            Chart payload dict (type, xKey, yKeys, data) or None if generation failed

        Raises:
            ValueError: Invalid chart configuration
        """
        from app.services.engine_visualization import (
            build_chart_from_config,
            validate_chart_config,
        )

        try:
            # Validate chart configuration
            if not validate_chart_config(chart_config):
                raise ValueError("Chart configuration validation failed")

            # Build chart from config and data
            chart_payload = build_chart_from_config(chart_config, data)

            logger.info(
                "Chart generated successfully",
                chart_type=chart_config.get("type"),
                rows_included=len(data),
            )
            return chart_payload

        except ValueError as exc:
            logger.warning(
                "Invalid chart configuration",
                error=str(exc),
                config=chart_config,
            )
            return None

        except Exception as exc:
            logger.error(
                "Unexpected error in chart generation",
                error_type=type(exc).__name__,
                error=str(exc),
            )
            return None

    async def auto_detect_chart_type(
        self,
        data: list[dict[str, Any]],
    ) -> str:
        """Auto-detect appropriate chart type based on data structure.

        Args:
            data: Result data to analyze

        Returns:
            Chart type string ("bar", "line", "scatter", etc.)
        """
        if not data:
            return "table"

        # Simple heuristic: check first row
        sample = data[0]
        num_columns = len(sample)

        # More than 2 numeric columns → scatter or multi-line
        if num_columns > 2:
            return "bar"
        elif num_columns == 2:
            return "line"
        else:
            return "table"

    def emit_visualization_event(
        self,
        chart_config: dict[str, Any],
    ) -> dict[str, str]:
        """Format chart config for SSE event emission.

        Returns:
            Dict ready to be serialized as SSE event
        """
        # Per existing pattern: SSE event format must match frontend parser
        # Format: { "type": "visualization", "data": {...chart_config} }
        return {
            "type": "visualization",
            "data": chart_config,
        }
