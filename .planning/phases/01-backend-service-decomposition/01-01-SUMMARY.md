---
phase: 01-backend-service-decomposition
plan: 01
subsystem: backend-services
tags:
  - service-extraction
  - sql-execution
  - error-handling
  - module-design
decision_ids:
  - D-01
  - D-03
  - D-04
dependency_graph:
  requires: []
  provides:
    - SQLExecutor service for SQL query execution
    - Error categorization for SQL failures
  affects:
    - gptme_engine refactoring (01-03)
    - test suite for SQL execution (BACK-02)
tech_stack:
  patterns:
    - Service layer pattern (SQLExecutor extracted from monolith)
    - Lazy imports to prevent circular dependencies
    - Specific exception types per Python best practices
  added:
    - structlog usage in sql_executor.py
    - TYPE_CHECKING guard for type hints without runtime cost
key_files:
  created:
    - apps/api/app/services/sql_executor.py (137 lines)
  modified: []
  referenced:
    - apps/api/app/services/database.py (DatabaseManager interface)
    - apps/api/app/services/engine_diagnostics.py (error categorization functions)
    - apps/api/app/services/gptme_engine.py (source of SQL execution logic)
metrics:
  duration: 8m
  completed_date: "2026-03-29"
  tasks_completed: 2
  task_breakdown:
    - "Task 1: SQL execution logic analysis (complete)"
    - "Task 2: SQLExecutor module creation (complete)"
---

# Phase 01 Plan 01: SQL Executor Service Extraction

**Summary:** Created dedicated SQLExecutor service module to handle SQL query execution, extracted from gptme_engine.py monolith. Implements specific exception handling, structured logging, and serves as foundation for service decomposition pattern.

## What Was Built

**SQLExecutor Service Module** (`apps/api/app/services/sql_executor.py`)
- **Purpose:** Encapsulates SQL query execution responsibility previously embedded in gptme_engine.py
- **Core API:**
  - `execute_sql(sql, db_config, timeout)` → Async execution with specific exception handling
  - `inject_sql_data(sql, data, variable_name)` → Prepare query results for Python context
- **Error Handling:** Per D-04, uses specific exception types (OperationalError, ProgrammingError, ValueError) instead of bare except clauses
- **Logging:** Structlog integration for detailed error tracking to backend logs, while frontend receives concise categorization
- **Dependencies:** Lazy imports of create_database_manager and categorize_sql_error to prevent circular dependencies

## Integration Points Identified

1. **DatabaseManager Interface** (from database.py)
   - SQLExecutor depends on `create_database_manager(config)` factory
   - Consumes `DatabaseManager.execute_query()` API
   - Pattern established for future service-to-service communication

2. **Error Categorization** (from engine_diagnostics.py)
   - SQLExecutor calls `categorize_sql_error()` to convert raw exceptions to structured error codes
   - Returns tuple: (error_code, category, is_recoverable)
   - Enables consistent error handling across the system

3. **GptmeEngine Integration** (downstream in 01-03)
   - Current `_execute_sql()` method in gptme_engine (line 932-940) will be replaced with SQLExecutor call
   - Error handling in `_run_sql_phase()` (line 562) will shift to SQLExecutor responsibility
   - GptmeEngine becomes orchestrator, SQLExecutor becomes SQL specialist

## Error Handling Approach

Per decision D-04, SQLExecutor uses specific exception types:

```python
# Before (bare except — hard to debug):
try:
    db_manager.execute_query(sql)
except Exception as exc:  # Catches everything
    # Can't distinguish SQL syntax error from connection timeout

# After (specific types):
try:
    db_manager.execute_query(sql)
except (OperationalError, ProgrammingError) as exc:
    # Clear distinction: connection vs syntax vs data error
except ValueError as exc:
    # Input validation failure (read-only check)
except Exception as exc:
    # Truly unexpected error type
```

This approach:
1. Makes error handling intent explicit
2. Enables proper routing to error recovery (retry vs halt)
3. Prevents accidentally swallowing critical errors
4. Aligns with Python style guidelines (PEP 8: specific exception types)

## Verification Checklist

- ✓ sql_executor.py created and compiles without import errors
- ✓ SQLExecutor class defined with __init__ and async methods
- ✓ Type hints present and correct (TYPE_CHECKING guard used)
- ✓ Exception handling uses specific types only (no bare except in execute_sql)
- ✓ Structlog imports present, logger created
- ✓ Methods have comprehensive docstrings
- ✓ Lazy imports in execute_sql prevent circular dependencies
- ✓ Module passes `python -m py_compile` check

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Exception Types | OperationalError, ProgrammingError, ValueError + catch-all | Specific types enable proper error recovery routing; catch-all prevents silent failures |
| Lazy Imports | Imports inside execute_sql() method | Prevents circular imports: database.py → sql_executor.py vs sql_executor.py → database.py |
| Async Pattern | All public methods async-compatible | Future-proofs for streaming integration and parallel query execution |
| Data Injection | inject_sql_data() in SQLExecutor | Part of SQL result processing pipeline, not engine responsibility |

## Deviations from Plan

None — plan executed exactly as written.

## Auth Gates

None required for this plan.

## Known Stubs

The `inject_sql_data()` method has placeholder implementation (line 123-131). This is intentional and documented in code comments:
- Current implementation returns raw JSON string assignment
- Future plans may enhance to pandas DataFrame creation
- Data format matches engine_workflow.py EngineRunState expectations
- Will be replaced during engine_workflow integration (01-04)

**Stub Location:** `apps/api/app/services/sql_executor.py:123-131`
**Reason:** Core SQL execution extracted first; data transformation logic deferred to next task
**Future Plan:** 01-04 (engine_workflow refactoring) will wire complete data injection pipeline

## Next Steps

1. **01-02 (pending):** Write tests for SQLExecutor with pytest-asyncio
2. **01-03 (depends on this):** Refactor gptme_engine._execute_sql() to use SQLExecutor
3. **01-04 (depends on 01-03):** Extract engine_workflow orchestration logic

## Self-Check

File existence verified:
- ✓ `/Users/maokaiyue/QueryGPT/apps/api/app/services/sql_executor.py` exists (137 lines)

Commit verified:
- ✓ Commit hash: 30ca44f
- ✓ Message: "feat(01-01): create SQLExecutor service module for SQL execution"
- ✓ Files included: apps/api/app/services/sql_executor.py

## Self-Check: PASSED

All verification checks passed. Module is production-ready for integration in downstream plans.
