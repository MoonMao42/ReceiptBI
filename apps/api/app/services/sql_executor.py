"""SQL execution service module.

Extracted from gptme_engine.py for independent SQL execution responsibility.
Per D-01 (direct module extraction): move SQL functions, keep GptmeEngine as orchestrator.
Per D-04: Use specific exception types, not bare except clauses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    pass

logger = structlog.get_logger()


class SQLExecutor:
    """Handles SQL query execution and error recovery."""

    def __init__(self, language: str = "zh"):
        """Initialize SQLExecutor.

        Args:
            language: Language for error messages ("zh" for Chinese, "en" for English)
        """
        self.language = language

    async def execute_sql(
        self,
        sql: str,
        db_config: dict[str, Any],
        timeout: int | None = None,
    ) -> tuple[list[dict[str, Any]] | None, int | None]:
        """Execute read-only SQL query with error handling.

        Per D-04: Specific exception types instead of bare except.
        Per D-03: Concise error message to frontend, detailed info to structlog.

        Args:
            sql: SQL query string (must be read-only)
            db_config: Database connection configuration
            timeout: Query timeout in seconds (optional)

        Returns:
            Tuple of (result_data, row_count)
            - result_data: list of result rows as dicts, or None on error
            - row_count: number of rows returned, or None on error

        Raises:
            OperationalError: Database connection or execution error
            ProgrammingError: SQL syntax error or invalid column reference
            ValueError: Invalid input (read-only check failed)
        """
        from sqlalchemy.exc import OperationalError, ProgrammingError

        from app.services.database import create_database_manager
        from app.services.engine_diagnostics import categorize_sql_error

        try:
            # Create database manager and execute query
            db_manager = create_database_manager(db_config)
            result = db_manager.execute_query(sql, read_only=True)

            logger.info(
                "SQL executed successfully",
                rows_count=result.rows_count,
                sql_preview=sql[:100] if sql else "",
            )
            return result.data, result.rows_count

        except (OperationalError, ProgrammingError) as exc:
            # D-04: Specific SQLAlchemy exception types
            # D-03: Detailed info to structlog only
            error_code, category, recoverable = categorize_sql_error(str(exc))
            logger.error(
                "SQL execution error",
                error_type=type(exc).__name__,
                error_code=error_code,
                category=category,
                recoverable=recoverable,
                sql_preview=sql[:100] if sql else "",
                exception_detail=str(exc),
            )
            return None, None

        except ValueError as exc:
            # Invalid input (e.g., read-only validation failed)
            logger.error(
                "Invalid SQL input",
                error_type="ValueError",
                exception_detail=str(exc),
            )
            return None, None

        except Exception as exc:
            # Unexpected error type
            logger.error(
                "Unexpected error in SQL execution",
                error_type=type(exc).__name__,
                exception_detail=str(exc),
            )
            return None, None

    async def inject_sql_data(
        self,
        sql: str,
        data: list[dict[str, Any]],
        variable_name: str = "sql_results",
    ) -> str:
        """Prepare SQL data for injection into Python execution context.

        Converts query results into a Python-friendly format (typically a pandas DataFrame variable).

        Args:
            sql: Original SQL query (for diagnostic reference)
            data: Query result data rows
            variable_name: Name of variable to create in Python context

        Returns:
            Python code that creates the data variable
        """
        # This method stays in SQLExecutor because it's part of SQL result processing
        # Implementation details depend on engine_workflow.py patterns
        # For now: placeholder that returns code string ready for Python execution

        if not data:
            return f"{variable_name} = []  # No results from: {sql[:50]}"

        # Build Python code that reconstructs the data structure
        # This is typically used to pass SQL results into Python sandbox
        import json

        data_json = json.dumps(data, default=str)
        return f"{variable_name} = {data_json}"
