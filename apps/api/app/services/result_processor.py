"""Result processing service module.

Extracted from gptme_engine.py for parsing AI output and extracting executable artifacts.
Per D-01 (direct module extraction): move content parsing functions.
Per D-04: Specific exception handling for malformed responses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    pass

logger = structlog.get_logger()


class ResultProcessor:
    """Parses AI-generated content and extracts executable artifacts (code, charts)."""

    def __init__(self, language: str = "zh"):
        """Initialize ResultProcessor.

        Args:
            language: Language for processing ("zh" or "en")
        """
        self.language = language

    async def extract_results(
        self,
        ai_content: str,
        sql_data: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Extract SQL, Python code, and visualization config from AI output.

        Per D-04: Specific exception types for parse errors.
        Per D-03: Detailed logging for diagnostic purposes.

        Args:
            ai_content: Full AI-generated response text
            sql_data: Optional SQL results for validation

        Returns:
            Dictionary with extracted artifacts:
            {
                "sql_code": str | None,
                "python_code": str | None,
                "chart_config": dict | None,
                "thinking": list[str],
                "errors": list[str]
            }

        Raises:
            ValueError: Content parsing failed (malformed response)
        """
        from app.services.engine_content import (
            extract_chart_config,
            extract_python_block,
            extract_sql_block,
            parse_thinking_markers,
        )

        try:
            result = {
                "sql_code": None,
                "python_code": None,
                "chart_config": None,
                "thinking": [],
                "errors": [],
            }

            # Step 1: Extract thinking markers
            try:
                thinking_list = parse_thinking_markers(ai_content)
                result["thinking"] = thinking_list
                if thinking_list:
                    logger.info("Extracted thinking markers", count=len(thinking_list))
            except Exception as exc:
                logger.warning("Failed to extract thinking markers", error=str(exc))
                result["errors"].append(f"Thinking extraction: {exc}")

            # Step 2: Extract SQL code block
            try:
                sql_code = extract_sql_block(ai_content)
                if sql_code:
                    result["sql_code"] = sql_code
                    logger.info("Extracted SQL code", sql_lines=len(sql_code.split("\n")))
            except Exception as exc:
                logger.warning("Failed to extract SQL code", error=str(exc))
                result["errors"].append(f"SQL extraction: {exc}")

            # Step 3: Extract Python code block
            try:
                python_code = extract_python_block(ai_content)
                if python_code:
                    result["python_code"] = python_code
                    logger.info("Extracted Python code", py_lines=len(python_code.split("\n")))
            except Exception as exc:
                logger.warning("Failed to extract Python code", error=str(exc))
                result["errors"].append(f"Python extraction: {exc}")

            # Step 4: Extract chart configuration
            try:
                chart_config = extract_chart_config(ai_content)
                if chart_config:
                    result["chart_config"] = chart_config
                    logger.info("Extracted chart configuration", chart_type=chart_config.get("type"))
            except Exception as exc:
                logger.warning("Failed to extract chart config", error=str(exc))
                result["errors"].append(f"Chart extraction: {exc}")

            artifact_count = sum(
                1
                for k, v in result.items()
                if k != "errors" and k != "thinking" and v is not None
            )
            logger.info(
                "Result extraction completed",
                artifacts_found=artifact_count,
                error_count=len(result["errors"]),
            )
            return result

        except Exception as exc:
            logger.error("Unexpected error in result extraction", error=str(exc))
            raise ValueError(f"Failed to extract results from AI output: {exc}") from exc

    def extract_chart_config(
        self,
        content: str,
        sql_data: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        """Extract visualization configuration from AI output.

        Args:
            content: AI-generated content
            sql_data: SQL result data for validation

        Returns:
            Chart config dict or None if no visualization requested
        """
        from app.services.engine_content import extract_chart_config

        try:
            chart_config = extract_chart_config(content)
            if not chart_config:
                return None

            # Validate configuration
            if sql_data and len(sql_data) > 0:
                sample_row = sql_data[0]
                if not chart_config.get("xKey") and sample_row:
                    # Auto-select first column as xKey if not specified
                    chart_config["xKey"] = list(sample_row.keys())[0]

            logger.debug(
                "Chart config extracted and validated",
                chart_type=chart_config.get("type"),
            )
            return chart_config

        except Exception as exc:
            logger.debug("Chart config extraction/validation failed", error=str(exc))
            return None

    def build_chart_payload(
        self,
        chart_config: dict[str, Any] | None,
        data: list[dict[str, Any]] | None,
    ) -> dict[str, Any] | None:
        """Build a complete chart payload from config and data.

        Args:
            chart_config: Chart configuration (from extract_chart_config)
            data: SQL result data to render in chart

        Returns:
            Complete chart payload ready for frontend, or None if cannot build
        """
        from app.services.engine_visualization import build_chart_from_config

        if not chart_config or not data:
            return None

        try:
            payload = build_chart_from_config(chart_config, data)
            if payload:
                logger.info("Chart payload built", chart_type=payload.get("type"))
            return payload
        except Exception as exc:
            logger.warning("Failed to build chart payload", error=str(exc))
            return None
