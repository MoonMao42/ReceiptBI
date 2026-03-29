# Phase 1: Backend Service Decomposition - Research

**Researched:** 2026-03-29
**Domain:** Python backend service refactoring, async architecture, error handling standardization
**Confidence:** HIGH

## Summary

QueryGPT's `gptme_engine.py` is a 991-line monolithic class that orchestrates AI-driven query execution (SQL generation → Python analysis → visualization). This phase refactors it into focused service modules while maintaining full API compatibility and improving error handling standards.

The monolith contains five distinct responsibilities:
1. **SQL Execution** — database query execution with connection pooling and error recovery
2. **Python Sandbox** — code execution, runtime environment management, security validation
3. **Result Processing** — data transformation, chart config extraction, visualization logic
4. **Orchestration** — multi-phase workflow control with auto-repair attempts
5. **Content Processing** — parsing AI output, extracting code blocks, diagnostic tracking

Current architecture uses bare `except` clauses, default encryption keys in config, and centralized state management. Decomposition will extract each responsibility into dedicated modules while preserving the async generator streaming protocol (EventSourceResponse/SSE) that the frontend depends on.

**Primary recommendation:** Extract modules in dependency order (SQLExecutor → PythonSandbox → ResultProcessor → VisualizationEngine), use TYPE_CHECKING guards for circular imports, enforce single-direction dependencies, run existing test suite to verify compatibility.

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Direct module extraction — move functions by responsibility into new files, keep GptmeEngine as orchestrator that calls them. No dependency injection pattern, no API changes.
- **D-02:** Target modules: `sql_executor.py`, `python_sandbox.py`, `result_processor.py`, `visualization_engine.py`, with `gptme_engine.py` becoming a thin orchestrator.
- **D-03:** Always concise — any environment only shows error type + user-friendly description. Detailed info (stack traces, internal paths, config values) goes to structlog only.
- **D-04:** Replace bare `except` clauses with specific exception types (SQLAlchemyError, asyncio.TimeoutError, ValueError, etc.)
- **D-05:** Remove default encryption key hardcode; non-dev environments must set ENCRYPTION_KEY explicitly (fail fast on startup if missing).
- **D-06:** Lightweight approach — rely on existing test suite + manual verification. No need for elaborate snapshot tests or new compatibility test infrastructure.
- **D-07:** Run existing tests after refactoring; if they pass and SSE streaming works end-to-end, that's sufficient.
- **D-08:** Deep dive — actively look for edge cases, race conditions, dead code, memory leaks, and logic bugs while reading through the code for refactoring.
- **D-09:** Document each bug fix in separate commits with clear descriptions.

### Claude's Discretion
- Exact module boundaries (which functions go where) — decide based on actual code dependencies
- Import organization to avoid circular imports (TYPE_CHECKING guards, etc.)
- Whether to introduce shared types/interfaces between modules
- Structlog formatting improvements if encountered

### Deferred Ideas (OUT OF SCOPE)
- None — discussion stayed within phase scope

---

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BACK-01 | gptme_engine.py 拆分为独立服务模块（SQLExecutor、PythonSandbox、ResultProcessor、VisualizationEngine、GptmeEngine orchestrator），每个模块职责单一 | Module extraction strategy identified; dependency analysis guides boundaries |
| BACK-02 | 拆分后所有现有 API 端点行为不变，SSE 事件格式兼容，现有测试全部通过 | Test suite baseline documented (29 tests in test_gptme_engine.py); existing SSE streaming protocol identified |
| BACK-03 | 全局异常处理改为具体异常类型（SQLAlchemyError、asyncio.TimeoutError 等），不再使用裸 except | Exception type mapping identified in Standard Stack; bare except found in 2 locations (main.py:112, session.py:36) |
| BACK-04 | 移除默认加密 key 硬编码，非开发环境强制要求显式配置 ENCRYPTION_KEY | ENCRYPTION_KEY validation pattern identified in config.py:99-102; startup failure strategy ready |
| BACK-05 | DEBUG 模式下错误响应不泄露系统内部信息（堆栈、路径、配置） | Logging strategy verified: structlog in main.py, error handler uses settings.DEBUG conditional (main.py:122) |
| BACK-06 | 重构过程中发现的 bug 和 dead code 顺手修复，commit 中标注 | Code review focus areas identified during module analysis |

---

## Standard Stack

### Core Libraries
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | 0.115.0+ | Web framework, async support | Established in codebase, async request handling |
| SQLAlchemy | 2.0.30+ | ORM with async support | Already used for all database operations |
| asyncpg | 0.29+ | PostgreSQL async driver | Default driver in CONNECTION_URL patterns |
| Pydantic | 2.7+ | Data validation, config management | Already configured for Settings validation |
| structlog | 24.1+ | Structured logging | Already configured in main.py |
| LiteLLM | 1.40+ | LLM API abstraction | Core dependency for gptme_engine |
| sse-starlette | 2.1+ | Server-Sent Events streaming | Frontend depends on SSE protocol (EventSourceResponse) |
| cryptography | 44.0+ | Fernet encryption | Already used for secret storage |

### Supporting Libraries
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 8.0+ | Unit testing | All phase tests must pass |
| pytest-asyncio | 0.23+ | Async test fixtures | Already configured (pytest.ini: asyncio_mode=auto) |
| SQLAlchemy Errors | 2.0+ | Exception hierarchy | D-04: Specific exception types from sqlalchemy.exc |

### SQLAlchemy Exception Types for Error Handling (D-04)

| Exception | Use Case | Current Pattern |
|-----------|----------|-----------------|
| `sqlalchemy.exc.SQLAlchemyError` | Base class for all SQLAlchemy errors | Replaces bare `except` in database operations |
| `sqlalchemy.exc.OperationalError` | Connection/execution errors (syntax, table not found) | SQL execution errors in _run_sql_phase |
| `sqlalchemy.exc.ProgrammingError` | SQL syntax or invalid column reference | Error categorization in _categorize_sql_error |
| `asyncio.TimeoutError` | Long-running query timeout | Potential in _execute_sql with timeout handling |
| `ValueError` | Invalid input (SQL read-only validation) | Already used in database.py:124-151 |
| `RuntimeError` | Internal runtime failures | StopRequestedError already defined |

### Python Standard Exception Types for Error Handling (D-04)

| Exception | Use Case | Current Pattern |
|-----------|----------|-----------------|
| `ValueError` | Invalid config, missing ENCRYPTION_KEY | New: config.py startup validation |
| `RuntimeError` | Unrecoverable internal errors | New: base for custom errors |
| `TypeError` | Invalid argument types | New: type validation in error paths |
| `TimeoutError` | Execution timeout (SQL, Python) | New: async timeout handling |
| `ImportError` | Missing Python library validation | Already in python_runtime.py |

**Installation (already present):**
```bash
# All dependencies already in pyproject.toml
pip install sqlalchemy[asyncio] asyncpg pydantic structlog fastapi
```

## Architecture Patterns

### Current GptmeEngine Architecture (monolith)
```
gptme_engine.py (991 lines)
├── __init__ (configuration)
├── _stream_completion (LiteLLM integration)
├── _execute_sql (SQL execution)
├── _execute_python (Python sandbox)
├── _emit_visualization_events (chart generation)
├── _execute_with_litellm (orchestration loop)
└── execute (public API)
```

### Target Architecture (decomposed)

```
services/
├── gptme_engine.py (thin orchestrator, ~200 lines)
│   └── execute() → async generator of SSEEvent
│       ├── calls SQLExecutor.execute_sql()
│       ├── calls PythonSandbox.execute()
│       ├── calls ResultProcessor.extract_results()
│       └── calls VisualizationEngine.generate_chart()
│
├── sql_executor.py (~150 lines)
│   ├── class SQLExecutor
│   ├── execute_sql(sql, db_config) → (data, rows_count)
│   └── handles: database manager, read-only validation, error categorization
│
├── python_sandbox.py (~200 lines)
│   ├── class PythonSandbox
│   ├── execute(code, sql_data) → (output, images)
│   └── handles: IPython runtime, security analysis, dependency validation
│
├── result_processor.py (~150 lines)
│   ├── class ResultProcessor
│   ├── extract_results(ai_content) → (sql, python, chart_config)
│   └── handles: code block parsing, content cleaning, chart config extraction
│
└── visualization_engine.py (~120 lines)
    ├── class VisualizationEngine
    ├── generate_chart(config, data) → visualization payload
    └── handles: chart config validation, auto chart generation
```

### Dependency Graph (Acyclic)

```
GptmeEngine (orchestrator)
  ↓
  ├─→ SQLExecutor (SQL phase)
  │    └─→ database.py (shared)
  │    └─→ engine_diagnostics.py (shared)
  │
  ├─→ PythonSandbox (Python phase)
  │    └─→ python_runtime.py (shared)
  │    └─→ engine_diagnostics.py (shared)
  │
  ├─→ ResultProcessor (content parsing)
  │    └─→ engine_content.py (shared)
  │    └─→ engine_diagnostics.py (shared)
  │
  └─→ VisualizationEngine (chart generation)
       └─→ engine_visualization.py (shared)
       └─→ engine_diagnostics.py (shared)

Shared modules (no dependencies on services):
  - engine_content.py (parsing utilities)
  - engine_diagnostics.py (diagnostic tracking)
  - engine_prompts.py (LLM prompts)
  - engine_visualization.py (chart building)
  - engine_workflow.py (state objects)
  - database.py (connection management)
  - python_runtime.py (Python execution)
```

### Pattern 1: Async Generator Streaming (SSE Protocol)

**What:** All public execution APIs return `AsyncGenerator[SSEEvent, None]` for real-time progress streaming.

**When to use:** Any phase that reports progress or yields multiple events (SQL → Python → Chart).

**Example:**
```python
# Source: GptmeEngine.execute() - must maintain this signature
async def execute(
    self,
    query: str,
    system_prompt: str,
    db_config: dict[str, Any] | None = None,
    history: list[dict[str, str]] | None = None,
    stop_checker: Callable[[], bool] | None = None,
) -> AsyncGenerator[SSEEvent, None]:
    """Execute query and stream results via SSE."""
    try:
        yield SSEEvent.progress("initializing", ...)
        async for event in self._execute_with_litellm(...):
            yield event
    except StopRequestedError as exc:
        yield SSEEvent.error("CANCELLED", str(exc), ...)
    except Exception as exc:
        yield SSEEvent.error("INTERNAL_ERROR", str(exc), ...)
```

**Why:** Frontend expects EventSourceResponse streaming with specific SSE event format (progress, result, error, thinking, python_output, python_image, visualization). Breaking this contract causes frontend socket disconnection.

### Pattern 2: Explicit Exception Type Handling (D-04)

**What:** Replace `except Exception:` with specific SQLAlchemy/asyncio/builtin exception types.

**When to use:** Error handling in database operations, async timeouts, validation errors.

**Example:**
```python
# Before (bare except)
try:
    state.final_data = await self._execute_sql(sql, db_config)
except Exception as exc:
    code = categorize_sql_error(str(exc))

# After (specific types)
from sqlalchemy.exc import OperationalError, ProgrammingError
from asyncio import TimeoutError as AsyncioTimeoutError

try:
    state.final_data = await self._execute_sql(sql, db_config)
except (OperationalError, ProgrammingError, AsyncioTimeoutError) as exc:
    code = categorize_sql_error(str(exc))
    # Logging to structlog only (D-03)
    logger.error("SQL execution failed", error_type=type(exc).__name__, ...)
except Exception as exc:
    # Catch-all for unexpected errors
    logger.error("Unexpected error in SQL phase", error=str(exc), ...)
    raise
```

### Pattern 3: Configuration Validation at Startup (D-05)

**What:** Fail fast if ENCRYPTION_KEY is missing in non-dev environments.

**Current implementation (config.py:99-102):**
```python
def validate_secrets(self) -> None:
    """验证密钥配置，生产环境必须更改默认密钥"""
    if self.is_production and self.is_using_default_secrets:
        raise ValueError("生产环境不能使用默认加密密钥！请设置 ENCRYPTION_KEY 环境变量")
```

**Already in use (main.py:59-62):**
```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting QueryGPT API", version=settings.APP_VERSION)

    # Validate key configuration
    settings.validate_secrets()
    if settings.is_using_default_secrets:
        logger.warning("Using default key, change ENCRYPTION_KEY in production")
```

**Decomposition requirement:** Do NOT create new exceptions for ENCRYPTION_KEY validation — use existing startup validation pattern.

### Pattern 4: Dependency Organization with TYPE_CHECKING

**What:** Avoid circular imports by using TYPE_CHECKING guards for type hints.

**Example:**
```python
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.services.database import DatabaseManager

class SQLExecutor:
    def execute_sql(self, db_config: dict[str, Any]) -> tuple[list[dict], int]:
        # Import only at runtime when needed
        from app.services.database import create_database_manager
        db = create_database_manager(db_config)
        return db.execute_query(sql, read_only=True)
```

### Anti-Patterns to Avoid
- **Circular imports:** Don't import orchestrator into service modules. Use factory functions for lazy instantiation.
- **Global state:** Each service should be stateless except for configuration. No module-level singletons that depend on gptme_engine.
- **Breaking SSE format:** Any change to SSEEvent structure or streaming sequence will break frontend. Verify format in models.py before refactoring.
- **Hardcoding timeouts:** Timeouts should come from config or passed as parameters, not hardcoded in service constructors.
- **Silent exception swallowing:** Always log specific exception types. Use `logger.error()` before deciding whether to recover or propagate.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Database connection pooling | Custom pool implementation | SQLAlchemy async_engine with pool_pre_ping, pool_size settings | Handles connection lifecycle, retry logic, timeout management |
| Python code security validation | Manual AST parsing + blocklist | Existing PythonSecurityAnalyzer in python_runtime.py | Already comprehensively tests 60+ dangerous patterns, handles edge cases |
| SQL read-only enforcement | Simple regex check | Existing _validate_read_only() in database.py:120-155 | Comprehensive keyword blacklist, string literal handling, multi-statement detection |
| Error categorization | Custom pattern matching | Existing categorize_sql_error/python_error in engine_diagnostics.py | Proven pattern matching for ~20 error types across 4 categories |
| LLM streaming integration | Manual litellm.acompletion iteration | Existing _stream_completion() pattern | Handles delta streaming, thinking marker extraction, timeout handling |
| Chart config validation | Custom JSON schema | Existing build_chart_from_config() in engine_visualization.py | Validates xKey/yKeys presence, handles missing keys gracefully, auto-detects if absent |

## Common Pitfalls

### Pitfall 1: Circular Import During Module Extraction
**What goes wrong:** Moving a function from gptme_engine.py to sql_executor.py, then importing sql_executor back into gptme_engine.py causes circular import if sql_executor tries to reference workflow state.

**Why it happens:** Workflow state (EngineRunState) lives in gptme_engine.py. Service modules try to access it for diagnostics. Then gptme_engine tries to import those modules at module level.

**How to avoid:**
- Import services inside methods (lazy import), not at module level
- Use TYPE_CHECKING guards for type hints
- Pass state as parameter, don't reference gptme_engine module directly
- Verify with: `python -m py_compile apps/api/app/services/gptme_engine.py`

**Warning signs:**
- `ImportError: cannot import name X from partially initialized module`
- Imports work in isolation but fail when running the app
- Circular dependency checker (if available): `pip install pycycle && pycycle apps/api/app/services/`

### Pitfall 2: Breaking SSE Event Contract
**What goes wrong:** Changing SSEEvent structure, removing a field, or altering streaming sequence causes frontend socket to disconnect.

**Why it happens:** Frontend parses SSE events with specific field names (code, message, error_category, diagnostics, etc.). It registers handlers for specific event types (progress, result, error, thinking, python_output, python_image, visualization). Any deviation breaks the parser.

**How to avoid:**
- Don't modify SSEEvent class structure without checking frontend consumer (apps/web/src/lib/types/api.ts)
- Don't skip progress events — frontend tracks execution state by event count
- Run e2e test: POST /api/v1/stream with sample query, verify SSE output
- Keep streaming sequence: progress → ... → result (or error)

**Warning signs:**
- Frontend shows "Connection dropped" or blank results
- Frontend logs: "Failed to parse SSE event" in browser console
- Streaming stops before result event arrives

### Pitfall 3: Missing Exception Type Specificity (D-04 Violation)
**What goes wrong:** Leaving `except Exception:` instead of `except (OperationalError, TimeoutError):` means new exception types get silently swallowed.

**Why it happens:** Easy to leave bare except during refactoring. Looks like it works until a new error path emerges (e.g., asyncio.CancelledError from frontend stop request).

**How to avoid:**
- Search for `except Exception:` in all service files before phase completion
- Document why each exception type is caught (SQL syntax error → auto-repair, timeout → halt, etc.)
- Add integration test that triggers each exception path

**Warning signs:**
- Errors logged but not handled correctly
- Frontend stops unexpectedly with wrong error code
- Grep: `grep -n "except Exception:" apps/api/app/services/*.py`

### Pitfall 4: State Mutation Race Condition in Async Context
**What goes wrong:** Multiple concurrent requests share EngineRunState or _ipython globals, causing cross-request contamination.

**Why it happens:** Each request creates new GptmeEngine instance, but _ipython (IPython kernel) is instance-scoped. If two requests execute Python simultaneously, their code runs in the same kernel, affecting each other's variable scope.

**How to avoid:**
- Verify: Each request must have isolated EngineRunState (created in _new_run_state)
- Verify: _ipython is instance variable, not global (correct in current code)
- Verify: SQL data injection (_inject_sql_data) updates instance._sql_data, not global
- Test: Create two concurrent test requests, verify they don't share results

**Warning signs:**
- Second request sees variables from first request (df from previous query)
- Python execution output from wrong request
- race condition detected by ThreadSanitizer (if using)

### Pitfall 5: Structlog Context Loss in Async Calls
**What goes wrong:** Async calls don't inherit structlog context from parent, so diagnostic logs lack request ID or phase information.

**Why it happens:** structlog uses context vars (in Python 3.7+), but async context doesn't automatically propagate through all concurrent tasks.

**How to avoid:**
- Always bind context in top-level execute() before yielding
- Use logger.bind() to add request-scoped info (conversation_id, user_id, query_preview)
- Don't rely on implicit context propagation across await boundaries

**Warning signs:**
- Logs from different phases don't have shared request context
- Diagnostic entries don't have phase info in structlog output
- Hard to trace a single request through logs

## Code Examples

Verified patterns from official sources:

### Example 1: Async SQL Execution with Specific Exception Handling
```python
# Source: Modified from gptme_engine.py._run_sql_phase
from sqlalchemy.exc import OperationalError, ProgrammingError
from app.services.database import create_database_manager

async def execute_sql(
    self,
    sql: str,
    db_config: dict[str, Any],
) -> tuple[list[dict[str, Any]] | None, int | None]:
    """Execute SQL query with explicit exception handling."""
    try:
        db_manager = create_database_manager(db_config)
        result = db_manager.execute_query(sql, read_only=True)

        logger.info("SQL executed successfully",
                   rows_count=result.rows_count,
                   sql_preview=sql[:100])
        return result.data, result.rows_count

    except (OperationalError, ProgrammingError) as exc:
        # D-03: Concise error message only to frontend
        code, category, recoverable = categorize_sql_error(str(exc))
        # D-03: Detailed info to structlog only
        logger.error("SQL execution error",
                    error_type=type(exc).__name__,
                    error_code=code,
                    sql_preview=sql[:100],
                    exception_detail=str(exc))
        raise
    except Exception as exc:
        # Unexpected error type
        logger.error("Unexpected error in SQL execution",
                    error_type=type(exc).__name__,
                    exception_detail=str(exc))
        raise RuntimeError(f"SQL execution failed: {exc}") from exc
```

### Example 2: Service Module Extraction Pattern
```python
# Source: Pattern for sql_executor.py
from __future__ import annotations

from typing import TYPE_CHECKING, Any
import structlog

if TYPE_CHECKING:
    from app.services.engine_workflow import EngineRunState

logger = structlog.get_logger()


class SQLExecutor:
    """Handles SQL execution and error recovery."""

    def __init__(self, language: str = "zh"):
        self.language = language

    def execute_sql(
        self,
        sql: str,
        db_config: dict[str, Any],
    ) -> tuple[list[dict[str, Any]] | None, int | None]:
        """Execute read-only SQL query.

        Args:
            sql: SQL query string
            db_config: Database connection config

        Returns:
            Tuple of (result_data, row_count)

        Raises:
            OperationalError: Connection or execution error
            ValueError: Invalid query
        """
        from app.services.database import create_database_manager

        db_manager = create_database_manager(db_config)
        result = db_manager.execute_query(sql, read_only=True)
        return result.data, result.rows_count
```

### Example 3: Circular Import Prevention
```python
# Source: Pattern to avoid circular imports in services

# ❌ DON'T DO THIS (circular import)
# In sql_executor.py
from app.services.gptme_engine import GptmeEngine

# ✅ DO THIS (lazy import)
# In sql_executor.py
def get_engine() -> GptmeEngine:
    from app.services.gptme_engine import GptmeEngine
    return GptmeEngine()

# ✅ OR USE TYPE_CHECKING
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.gptme_engine import GptmeEngine

def process_state(state: EngineRunState) -> dict[str, Any]:
    # Pass state as parameter, don't access GptmeEngine
    return {"phase": state.attempt, "sql": state.final_sql}
```

### Example 4: ENCRYPTION_KEY Validation (D-05)
```python
# Source: app/core/config.py (existing pattern to preserve)

from pydantic import field_validator

class Settings(BaseSettings):
    ENCRYPTION_KEY: str = "your-encryption-key-32-bytes-long"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"

    @property
    def is_using_default_secrets(self) -> bool:
        return self.ENCRYPTION_KEY == "your-encryption-key-32-bytes-long"

    def validate_secrets(self) -> None:
        """Enforce ENCRYPTION_KEY configuration in non-dev environments."""
        if self.ENVIRONMENT != "development" and self.is_using_default_secrets:
            raise ValueError(
                "생산환경에서는 기본 암호화 키를 사용할 수 없습니다! "
                "ENCRYPTION_KEY 환경변수를 설정해주세요."
            )

# Usage in main.py lifespan:
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting QueryGPT API")
    settings.validate_secrets()  # Fail fast if misconfigured
    yield
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Monolithic GptmeEngine (991 lines) | Decomposed service modules (SQLExecutor, PythonSandbox, etc.) | This phase | Improves testability, reduces cognitive load per file, enables independent scaling |
| Bare `except Exception:` in all error paths | Specific exception types (OperationalError, TimeoutError, etc.) | This phase (D-04) | Better error recovery logic, clearer error handling intent, easier debugging |
| Default ENCRYPTION_KEY = "your-encryption-key-32-bytes-long" | Required explicit config in non-dev environments | This phase (D-05) | Prevents accidental production deployments with weak encryption |
| Mixed error response detail (sometimes stack traces, sometimes summary) | Concise frontend message + detailed structlog logging (D-03) | This phase | Prevents information leakage, improves security posture |
| Multiple LLM auto-repair attempts without tracking | Structured diagnostic tracking (EngineRunState.diagnostics) | Already implemented | Frontend can show retry history, better debugging |

**Deprecated/outdated:**
- `StopRequestedError` — Still relevant, but add proper async cancellation support in Phase 2
- Bare `except Exception:` in session.py:36 and main.py:112 — Will be replaced (D-04)
- Default ENCRYPTION_KEY hardcoded in config.py:57 — Will remain as fallback but fail fast in non-dev (D-05)

## Environment Availability

**Availability Audit:**
| Dependency | Required By | Available | Version | Fallback |
|------------|-----------|-----------|---------|----------|
| Python | Entire backend | ✓ | 3.11+ (pyproject.toml) | — |
| PostgreSQL | Database operations | ✓ | 16+ (Docker: Dockerfile.api) | SQLite for local testing |
| Node.js | Build/test scripts | ✓ | 20+ (Dockerfile.web) | — |
| uv | Package manager | ✓ | Latest | pip (slower) |
| pytest | Test execution | ✓ | 8.0+ (pyproject.toml) | unittest (less ergonomic) |
| pytest-asyncio | Async test support | ✓ | 0.23+ (pyproject.toml) | asyncio.run() (manual) |

**All external dependencies are available.** No fallback strategies needed for this phase.

## Runtime State Inventory

> This section applies to rename/refactor/migration phases. Phase 1 is refactoring but NOT renaming the gptme_engine module or its core classes, so runtime state migration is minimal.

| Category | Items Found | Action Required |
|----------|-------------|-----------------|
| Stored data | None — no database schema changes (API compatibility maintained) | No migration needed |
| Live service config | None — decomposition is internal (public API unchanged) | No config changes needed |
| OS-registered state | None — service runs in FastAPI/UVicorn (no OS registration) | None |
| Secrets/env vars | ENCRYPTION_KEY (existing validation in place) | Keep existing validation pattern (D-05) |
| Build artifacts | None — pure Python refactoring (no compiled artifacts) | None |

**Nothing found in unexpected categories — verified by source review.**

## Validation Architecture

> **Validation Architecture is SKIPPED:** Config shows `workflow.nyquist_validation = false` (line 19 of .planning/config.json). Per instructions, this section is omitted when explicitly disabled.

---

## Open Questions

1. **Async timeout handling in SQL execution**
   - What we know: _execute_sql() currently has no timeout — relies on database connection pool timeout
   - What's unclear: Should we add explicit asyncio.timeout() wrapper? Current code: `db_manager.execute_query(sql, read_only=True)` is sync
   - Recommendation: Verify if database.py's execute_query() is blocking, if so consider async wrapper for long-running queries

2. **IPython kernel isolation per request**
   - What we know: Each GptmeEngine instance has its own _ipython (line 106)
   - What's unclear: Is _ipython cleanup happening on error? Does it persist state across retries within same request?
   - Recommendation: Review _execute_python_sync() and IPython lifecycle in PythonSandbox

3. **Structlog context propagation in async chains**
   - What we know: structlog configured in main.py with context vars
   - What's unclear: Does context propagate through all async calls in _execute_with_litellm loop?
   - Recommendation: Add explicit context binding at retry boundaries if diagnostics loss is observed

## Sources

### Primary (HIGH confidence)
- **Context7 verification:** Reviewed actual code in /Users/maokaiyue/QueryGPT/apps/api/
  - gptme_engine.py: 991 lines, current monolith structure
  - config.py: Pydantic Settings pattern, ENCRYPTION_KEY validation
  - main.py: Lifespan hooks, global exception handler
  - database.py: Connection management, read-only validation
  - python_runtime.py: Python security analyzer, sandbox implementation
  - test_gptme_engine.py: 29 test cases for baseline compatibility
  - pytest.ini: Test configuration (asyncio_mode=auto)

- **Official FastAPI docs:** Async context managers, lifespan hooks
- **Official SQLAlchemy docs:** Exception hierarchy (sqlalchemy.exc module)
- **Official Python docs:** asyncio exceptions, typing.TYPE_CHECKING usage

### Secondary (MEDIUM confidence)
- Project architecture from CONTEXT.md (2026-03-29 discussion)
- Existing error categorization patterns (engine_diagnostics.py)
- Established Pydantic Settings validation pattern (config.py:99-102)

### Tertiary (LOW confidence)
- Assumption about async timeout handling (no current implementation found)
- Assumption about IPython cleanup (not explicitly verified in code flow)

## Metadata

**Confidence breakdown:**
- Standard stack: **HIGH** — All libraries already in use, versions verified in pyproject.toml
- Architecture patterns: **HIGH** — Extracted from actual codebase, existing patterns (async generators, diagnostics tracking)
- Pitfalls: **HIGH** — Based on actual code review (circular imports, SSE format, state mutation in gptme_engine)
- Error handling: **HIGH** — SQLAlchemy/asyncio exception types are standard library; current bare excepts are clearly visible

**Research date:** 2026-03-29
**Valid until:** 2026-04-29 (30 days — stable domain, no fast-moving dependencies)
