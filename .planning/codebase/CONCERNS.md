# Codebase Concerns

**Analysis Date:** 2026-03-29

## Tech Debt

**Large component files lacking proper separation:**
- Issue: Multiple React components exceed 600+ lines (`SchemaSettings.tsx`, `ImportConfigDialog.tsx`, `ChatArea.tsx`), making them difficult to maintain and test
- Files: `apps/web/src/components/settings/SchemaSettings.tsx` (618 lines), `apps/web/src/components/settings/ImportConfigDialog.tsx` (467 lines), `apps/web/src/components/chat/ChatArea.tsx` (408 lines)
- Impact: Difficult to modify features without risk of unintended side effects; hard to unit test individual functionalities
- Fix approach: Extract sub-components and custom hooks into smaller, focused modules following single responsibility principle

**Large Python service modules:**
- Issue: `gptme_engine.py` is 990 lines - a single service file that handles too many concerns (AI execution, SQL/Python repair, visualization, diagnostics)
- Files: `apps/api/app/services/gptme_engine.py` (990 lines)
- Impact: Difficult to understand flow; hard to test individual concerns; tight coupling between features
- Fix approach: Split into focused modules: `engine_core.py`, `engine_repair.py`, `engine_visualization.py`, etc.

**Generic exception handling in database session:**
- Issue: Bare exception handler in `get_db()` catches all exceptions indiscriminately, masking specific database errors
- Files: `apps/api/app/db/session.py` lines 36-38
- Impact: Makes debugging harder; specific errors like connection timeouts or constraint violations are not distinguished
- Fix approach: Catch specific exception types (`SQLAlchemyError`, `asyncio.TimeoutError`, etc.) and re-raise appropriately

**Default encryption key in production:**
- Issue: Default encryption key hardcoded as placeholder value in config
- Files: `apps/api/app/core/config.py` line 57
- Impact: Production deployments require manual key rotation; validated at startup but could fail if validation is bypassed
- Fix approach: Remove default value; require explicit ENCRYPTION_KEY in all non-development environments via validation

**Broad catch-all exception handler in API:**
- Issue: Global exception handler catches all exceptions and exposes full error messages in debug mode
- Files: `apps/api/app/main.py` lines 112-125
- Impact: Could leak sensitive information about system internals in non-production environments with DEBUG=true
- Fix approach: Implement specific exception handlers for known error types; sanitize error messages based on environment

## Security Considerations

**Python code execution sandbox limitations:**
- Risk: `PythonSecurityAnalyzer` uses AST-based blocking but execution still occurs in the same process; sophisticated attacker could craft code using legitimate libraries to cause harm
- Files: `apps/api/app/services/python_runtime.py` lines 92-144
- Current mitigation: Blocklist of dangerous modules and builtins; but no resource limits (memory, CPU, execution time)
- Recommendations:
  - Add resource limits using `resource` module or separate process with timeout
  - Implement runtime monitoring for suspicious behavior
  - Consider sandboxing with containers or subprocess isolation

**Theme storage vulnerability (minor):**
- Risk: Theme preference stored in localStorage without CSRF protection; `dangerouslySetInnerHTML` used in layout script for theme injection
- Files: `apps/web/src/app/layout.tsx` lines 26-30
- Current mitigation: Script is self-contained and JSON.parse fails safely
- Recommendations:
  - Use safer theme injection method (e.g., CSS variables or class toggling)
  - Consider storing theme in secure cookie instead of localStorage

**Database connection string handling:**
- Risk: Connection URLs with passwords stored/logged; exception handlers might expose connection details
- Files: `apps/api/app/db/session.py`, `apps/api/app/services/database_adapters.py`
- Current mitigation: Password encryption for stored credentials; connection URLs not logged by default
- Recommendations:
  - Never log DATABASE_URL with credentials
  - Implement connection string sanitization in error messages
  - Use environment variable references instead of storing connection URLs

**Cross-site scripting through markdown rendering:**
- Risk: React Markdown component renders user content; vulnerability in markdown parser could allow script injection
- Files: `apps/web/src/components/chat/AssistantMessageCard.tsx` (uses react-markdown)
- Current mitigation: React escapes HTML by default; react-markdown sanitization depends on parser
- Recommendations:
  - Audit react-markdown security policies
  - Implement server-side sanitization of content before sending to client
  - Add Content Security Policy headers

## Performance Bottlenecks

**Database connection pooling for SQLite:**
- Problem: SQLite cannot use connection pooling (single-writer limitation), but application treats all DB connections uniformly
- Files: `apps/api/app/db/session.py` lines 10-16
- Cause: SQLite's locking model doesn't support concurrent writes; application could bottleneck with concurrent requests
- Improvement path:
  - Document SQLite-only single-instance deployment requirement
  - Switch to PostgreSQL for multi-instance deployments
  - Consider WAL mode for SQLite to allow more concurrency

**Schema visualization state management:**
- Problem: `SchemaSettings.tsx` re-renders full ReactFlow graph on every node/edge change; no memoization of expensive layout calculations
- Files: `apps/web/src/components/settings/SchemaSettings.tsx` lines 64-300+
- Cause: State updates propagate through parent components; layout algorithm runs on every change
- Improvement path:
  - Memoize node/edge arrays with `useMemo` based on schema data
  - Extract graph layout logic to separate hook
  - Consider virtualizing node rendering for large schemas

**Chat message accumulation without pagination:**
- Problem: All chat messages loaded and kept in memory in Zustand store; large conversations slow down rendering
- Files: `apps/web/src/lib/stores/chat.ts`
- Cause: Simple array append; no pagination or virtual scrolling
- Improvement path:
  - Implement pagination on API level
  - Use virtual scrolling for message list
  - Archive or paginate old messages in Zustand store

**Relationship suggestion algorithm complexity:**
- Problem: O(n²) relationship detection iterating all tables and columns with substring matching
- Files: `apps/api/app/api/v1/schema.py` lines 59-94
- Cause: Nested loops with regex variant matching for each column
- Improvement path:
  - Pre-compute and cache relationship suggestions
  - Cache results keyed by schema hash
  - Limit suggestions to first N most likely matches

## Fragile Areas

**Import/Export configuration:**
- Files: `apps/api/app/api/v1/export_import.py`, `apps/web/src/components/settings/ImportConfigDialog.tsx`
- Why fragile: Complex data transformation between API and UI; relationships, semantic terms, and layouts imported sequentially without transaction rollback on partial failure
- Safe modification:
  - Write comprehensive integration tests for import/export round-trip
  - Wrap multi-step import in database transaction
  - Validate imported data schema before processing
- Test coverage: Exists (`test_export_import.py`) but should test failure scenarios

**Active query registry for multi-instance:**
- Files: `apps/api/app/services/chat_runtime.py` lines 14-40
- Why fragile: `ActiveQueryRegistry` uses in-memory dict to track query state; completely unreliable in multi-instance deployments
- Safe modification:
  - Document that this only works in single-instance mode
  - Add warning log if Redis is not available in production
  - Replace with Redis-backed registry for distributed deployments
- Test coverage: Minimal

**Encryption key rotation:**
- Files: `apps/api/app/core/encryptor.py` (implied from usage in schema.py, execution_context.py)
- Why fragile: No migration path when encryption key changes; old encrypted passwords become unreadable
- Safe modification:
  - Add encryption key version field to Connection model
  - Implement re-encryption migration task
  - Support multiple keys during transition period
- Test coverage: Assumed

**Execution context resolution with missing models/connections:**
- Files: `apps/api/app/services/execution_context.py` lines 46-93
- Why fragile: Fallback chains (model_name → default_model_id → system default) could silently select wrong model/connection if database is inconsistent
- Safe modification:
  - Add explicit validation that resolved model/connection matches requested type
  - Prefer explicit error over silent fallback
  - Add logging for all fallback decisions
- Test coverage: Some coverage in `test_execution.py`

## Test Coverage Gaps

**Web app: E2E tests are smoke-only:**
- What's not tested: Settings dialogs, schema visualization interactions, chat message retry/rerun, error states
- Files: `apps/web/e2e/settings-chat.smoke.spec.ts` (limited scope)
- Risk: UI regressions in critical flows not caught until production
- Priority: High - critical user paths need E2E coverage

**API: Database connectivity tests missing:**
- What's not tested: Connection pool exhaustion, connection timeouts, read-only replicas, SSL certificate validation
- Files: Tests exist but don't cover database infrastructure issues
- Risk: Deployment could fail silently with database configuration errors
- Priority: High - prevents production issues

**API: Python code execution edge cases:**
- What's not tested: Memory explosion from large arrays, infinite loops, fork bombs, resource exhaustion
- Files: `tests/test_gptme_engine.py` tests happy path only
- Risk: Untrusted AI model output could hang/crash API instance
- Priority: High - security/stability concern

**Web app: Chat store race conditions:**
- What's not tested: Rapid-fire messages, concurrent stop/retry, browser tab switching, network interruption during streaming
- Files: `apps/web/src/lib/stores/chat.ts` - no concurrent operation tests
- Risk: Message ordering corruption, duplicate messages, missing responses
- Priority: Medium - affects UX but recoverable

**Import/Export: Partial failure scenarios:**
- What's not tested: Import failing mid-way, malformed JSON, missing required fields, schema version mismatches
- Files: `tests/test_export_import.py` tests happy path
- Risk: Corrupted or partially imported configurations, data inconsistency
- Priority: Medium - affects data integrity

## Scaling Limits

**SQLite as primary database:**
- Current capacity: Single-instance, < 100 concurrent connections (untested)
- Limit: Write contention becomes severe above single-digit concurrent writes
- Scaling path:
  - Document single-instance-only limitation clearly
  - Migrate to PostgreSQL before scaling to multiple API instances
  - Add replica support for read-heavy workloads

**In-memory state tracking:**
- Current capacity: Works for single instance; breaks with load balancer/multiple pods
- Limit: Query state tracking in `ActiveQueryRegistry` only local to instance
- Scaling path:
  - Replace with Redis-backed session store
  - Implement cross-instance communication for stop signals
  - Move conversation state to database

**Schema visualization for large databases:**
- Current capacity: ~100 tables renders acceptably
- Limit: ReactFlow with 1000+ nodes becomes unusable
- Scaling path:
  - Implement table filtering/search in UI
  - Lazy-load related tables
  - Add clustering/grouping view
  - Consider server-side graph layout pre-computation

## Dependencies at Risk

**gptme package (0.30.0+):**
- Risk: Young package; API breaking changes likely; tightly coupled execution logic
- Impact: Updates could break AI execution pipeline; version pinning required
- Migration plan:
  - Pin version with constraint `>=0.30.0,<1.0.0` to catch major breaks
  - Maintain fallback implementations of critical functions
  - Monitor upstream changelog

**litellm package:**
- Risk: Wrapper around multiple LLM providers; provider-specific behaviors leak through
- Impact: Provider updates could change behavior; error messages inconsistent
- Migration plan:
  - Implement adapter layer to normalize provider responses
  - Add provider-specific test coverage
  - Document provider-specific limitations

**React 19.0.0:**
- Risk: Very recent major version; ecosystem packages may have incompatibilities
- Impact: Package updates could introduce regressions; some libraries not yet compatible
- Migration plan:
  - Maintain comprehensive E2E test suite for compatibility testing
  - Pin critical dependencies with `^19.0.0` constraints
  - Monitor React ecosystem for compatibility issues

## Missing Critical Features

**No audit logging for configuration changes:**
- Problem: Schema changes, relationship modifications, semantic terms - no history of who changed what or when
- Blocks: Compliance requirements; debugging user issues; detecting unauthorized changes
- Impact: Cannot diagnose why configurations changed or recover specific versions

**No soft-delete for connections:**
- Problem: Deleting connection cascades to messages/conversations; data loss is permanent
- Blocks: Archiving historical data; compliance with data retention policies
- Impact: Cannot keep conversation history when connection is removed; GDPR compliance risk

**No batch query execution:**
- Problem: Users can only execute one query at a time; no bulk operations or scheduled queries
- Blocks: Advanced analytics workflows; bulk data loading
- Impact: Limited use cases for large-scale data operations

**No query result caching:**
- Problem: Same query executed multiple times hits database; no memo-ization of results
- Blocks: Performance optimization; cost reduction for expensive queries
- Impact: Slow performance for repeated queries; higher database load

---

*Concerns audit: 2026-03-29*
