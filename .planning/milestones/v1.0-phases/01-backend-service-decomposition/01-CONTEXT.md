# Phase 1: Backend Service Decomposition - Context

**Gathered:** 2026-03-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Refactor gptme_engine.py (990 lines) from a monolith into focused service modules (SQLExecutor, PythonSandbox, ResultProcessor, VisualizationEngine, GptmeEngine orchestrator). Standardize error handling across the backend. Secure encryption key configuration. Fix bugs found during refactoring.

</domain>

<decisions>
## Implementation Decisions

### Decomposition Strategy
- **D-01:** Direct module extraction — move functions by responsibility into new files, keep GptmeEngine as orchestrator that calls them. No dependency injection pattern, no API changes.
- **D-02:** Target modules: `sql_executor.py`, `python_sandbox.py`, `result_processor.py`, `visualization_engine.py`, with `gptme_engine.py` becoming a thin orchestrator.

### Error Handling Style
- **D-03:** Always concise — any environment only shows error type + user-friendly description. Detailed info (stack traces, internal paths, config values) goes to structlog only.
- **D-04:** Replace bare `except` clauses with specific exception types (SQLAlchemyError, asyncio.TimeoutError, ValueError, etc.)
- **D-05:** Remove default encryption key hardcode; non-dev environments must set ENCRYPTION_KEY explicitly (fail fast on startup if missing).

### Compatibility Approach
- **D-06:** Lightweight approach — rely on existing test suite + manual verification. No need for elaborate snapshot tests or new compatibility test infrastructure. CI is already weak, don't over-invest here.
- **D-07:** Run existing tests after refactoring; if they pass and SSE streaming works end-to-end, that's sufficient.

### Bug Fix Scope
- **D-08:** Deep dive — actively look for edge cases, race conditions, dead code, memory leaks, and logic bugs while reading through the code for refactoring. Don't just move code; improve it.
- **D-09:** Document each bug fix in separate commits with clear descriptions.

### Claude's Discretion
- Exact module boundaries (which functions go where) — decide based on actual code dependencies
- Import organization to avoid circular imports (TYPE_CHECKING guards, etc.)
- Whether to introduce shared types/interfaces between modules
- Structlog formatting improvements if encountered

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Backend service code
- `apps/api/app/services/gptme_engine.py` — The 990-line monolith to decompose
- `apps/api/app/services/execution.py` — ExecutionService that orchestrates gptme_engine
- `apps/api/app/services/execution_context.py` — Context resolution with fallback chains
- `apps/api/app/services/python_runtime.py` — Python sandbox (PythonSecurityAnalyzer)
- `apps/api/app/services/chat_runtime.py` — ActiveQueryRegistry

### Error handling targets
- `apps/api/app/db/session.py` — Generic exception handler in get_db() (lines 36-38)
- `apps/api/app/main.py` — Global exception handler (lines 112-125)
- `apps/api/app/core/config.py` — Default encryption key (line 57)

### Codebase analysis
- `.planning/codebase/ARCHITECTURE.md` — Current architecture overview
- `.planning/codebase/CONCERNS.md` — Known tech debt and issues
- `.planning/research/ARCHITECTURE.md` — Research on decomposition approach
- `.planning/research/PITFALLS.md` — Pitfalls to avoid (especially circular imports)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `structlog` already configured in `main.py` — can be used for detailed error logging
- Pydantic Settings in `config.py` — validation infrastructure for ENCRYPTION_KEY enforcement
- Existing test suite in `apps/api/tests/` — baseline for regression detection

### Established Patterns
- FastAPI dependency injection via `Depends(get_db)` for database sessions
- Async generators for SSE event streaming (EventSourceResponse)
- Pydantic models in `apps/api/app/models/` for request/response validation

### Integration Points
- `execution.py` imports from `gptme_engine.py` — this is the primary caller
- `chat.py` (API endpoint) → `execution.py` → `gptme_engine.py` — the call chain
- SSE event format is the external contract — must not change

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches. User wants pragmatic refactoring that improves code quality without over-engineering.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-backend-service-decomposition*
*Context gathered: 2026-03-29*
