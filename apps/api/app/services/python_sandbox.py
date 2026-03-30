"""Python sandbox execution service module.

Extracted from gptme_engine.py for isolated Python code execution.
Per D-01 (direct module extraction): move Python execution functions, keep GptmeEngine as orchestrator.
Per D-04: Use specific exception types for security and execution errors.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    pass

logger = structlog.get_logger()


class PythonSandbox:
    """Handles Python code execution with security analysis and sandbox isolation."""

    def __init__(self, language: str = "zh"):
        """Initialize PythonSandbox.

        Args:
            language: Language for error messages ("zh" or "en")
        """
        self.language = language
        self._ipython = None  # IPython kernel, created on-demand per execution
        self._python_runtime = None  # Lazy-loaded runtime

    async def execute(
        self,
        code: str,
        sql_data: dict[str, Any] | None = None,
        timeout: int = 60,
    ) -> tuple[str | None, list[str]]:
        """Execute Python code with security analysis.

        Per D-04: Specific exception types for security and runtime errors.
        Per D-03: Concise error messages to frontend, detailed logs to structlog.

        Args:
            code: Python code to execute (must pass security analysis)
            sql_data: SQL result data to inject into execution context
            timeout: Execution timeout in seconds

        Returns:
            Tuple of (output_text, image_files)
            - output_text: Code execution output (stdout/stderr), or None on error
            - image_files: List of generated image file paths, or None on error

        Raises:
            ValueError: Security analysis failed (malicious code detected)
            RuntimeError: Code execution error or timeout
        """
        from app.services.python_runtime import (
            PythonExecutionRuntime,
            PythonSecurityAnalyzer,
        )

        try:
            # Step 1: Security analysis (prevent dangerous code execution)
            analyzer = PythonSecurityAnalyzer()
            violations = analyzer.analyze(code)

            if violations:
                reason = "; ".join(violations[:3])  # First 3 violations
                logger.warning(
                    "Code rejected by security analysis",
                    reason=reason,
                    code_preview=code[:100],
                    violation_count=len(violations),
                )
                raise ValueError(f"Security check failed: {reason}")

            # Step 2: Initialize runtime if needed
            if self._python_runtime is None:
                self._python_runtime = PythonExecutionRuntime(language=self.language)

            # Step 3: Inject SQL data if provided
            if sql_data:
                for var_name, var_value in sql_data.items():
                    self._python_runtime.inject_sql_data(var_name, var_value)

            # Step 4: Execute with timeout
            logger.info("Executing Python code", code_preview=code[:50])

            try:
                output, images = await asyncio.wait_for(
                    self._execute_with_timeout(code),
                    timeout=timeout,
                )
            except TimeoutError as exc:
                logger.error("Python execution timeout", timeout=timeout)
                raise RuntimeError(f"Code execution timeout ({timeout}s)") from exc

            logger.info(
                "Python execution completed",
                output_length=len(output or ""),
                image_count=len(images or []),
            )
            return output, images

        except ValueError as exc:
            # Security check failed
            logger.error(
                "Security validation failed",
                error_type="ValueError",
                exception_detail=str(exc),
            )
            raise

        except RuntimeError as exc:
            # Execution error or timeout
            logger.error(
                "Python execution error",
                error_type="RuntimeError",
                exception_detail=str(exc),
            )
            raise

        except Exception as exc:
            # Unexpected error
            logger.error(
                "Unexpected error in Python sandbox",
                error_type=type(exc).__name__,
                exception_detail=str(exc),
            )
            raise RuntimeError(f"Unexpected error during Python execution: {exc}") from exc

    async def _execute_with_timeout(self, code: str) -> tuple[str | None, list[str]]:
        """Execute code asynchronously with timeout support.

        This method bridges sync IPython execution to async context.
        """
        import concurrent.futures

        loop = asyncio.get_event_loop()

        def run_code():
            # Execute via runtime (handles IPython kernel, output capture, image generation)
            output, images = self._python_runtime.execute_sync(code)
            return output, images

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            return await loop.run_in_executor(executor, run_code)

    def cleanup(self) -> None:
        """Clean up IPython kernel resources after execution.

        Call this when done with the sandbox to release memory/file handles.
        """
        if self._python_runtime is not None:
            # IPython cleanup handled by PythonExecutionRuntime
            self._python_runtime = None
