# Domain Pitfalls: Refactoring Existing AI Database Assistant

**Project:** QueryGPT 精进
**Researched:** 2026-03-29
**Context:** Refactoring mature Python/React codebase; splitting large modules, adding caching, optimizing error handling, synchronizing Chinese documentation.

---

## Critical Pitfalls (Rewrite Risk)

### Pitfall 1: Circular Import Explosion During Python Module Decomposition

**What goes wrong:** When splitting `gptme_engine.py` (990 lines) into smaller service modules (`engine_core.py`, `engine_repair.py`, `engine_visualization.py`), new module interdependencies form circular import chains. For example:
- `engine_core.py` imports from `engine_repair.py` for error handling utilities
- `engine_repair.py` imports from `engine_core.py` for execution context
- `engine_visualization.py` needs both for result transformation

The circular imports don't cause immediate failure—they silently break at import time or cause AttributeError at runtime when one module loads before the other completes initialization.

**Why it happens:** The original 990-line monolith had no import boundaries; logic was linear within one file. Naive extraction treats existing functional dependencies as circular dependencies in the new architecture. Decomposition without architectural planning results in "accidental" tight coupling.

**Consequences:**
- Application fails to start with cryptic `ImportError` or `AttributeError` that points to wrong module
- Circular dependencies hide architectural problems (tight coupling, mixed concerns)
- Debugging is slow: error appears in Consumer module, actual root is in Producer module
- Refactoring becomes painful: can't split further without more circular dependencies

**Prevention:**
- Before splitting, map existing dependencies in the monolith explicitly (what calls what)
- Design module boundaries top-down: identify core abstractions first (execution, repair, visualization), then define interfaces each module exposes
- Use `TYPE_CHECKING` guards in Python for forward references that would cause circular imports:
  ```python
  from typing import TYPE_CHECKING
  if TYPE_CHECKING:
    from engine_core import ExecutionResult
  ```
- Extract shared concerns to a third module early: if both `engine_core` and `engine_repair` need `ExecutionContext`, move `ExecutionContext` to a separate `engine_types.py`
- Enforce one-directional dependencies: core → repair → visualization (no reverse imports)
- Use automated detection: `pycycle` in CI to catch circular imports before merge

**Detection:**
- CI pre-commit hook fails with circular import error
- `python -c "import app.services.engine_core"` fails in isolation
- Inconsistent import behavior between test and production (one import order works, another fails)
- Weird "undefined name" errors at runtime despite name being defined (late binding issue from circular import)

**Which phase addresses it:** Phase 1 (Module Decomposition) — must resolve before proceeding. Unresolved circular imports block testing and deployment.

---

### Pitfall 2: Cache Invalidation Bugs Leading to Silent Data Stale-ness

**What goes wrong:** When adding query result caching layer to existing code, cache invalidation logic doesn't fully account for all data mutation paths. For example:
- User caches query result for `SELECT * FROM users`
- User modifies a connection (changes schema, updates semantic terms, adds relationships)
- Query re-execution should invalidate cache, but invalidation logic only watches direct query mutations, not upstream schema changes
- User sees stale cached results even though underlying data changed

The bug is insidious: **it appears as intermittent data inconsistency** (sometimes fresh, sometimes stale), hard to reproduce, and users don't immediately recognize the problem.

**Why it happens:** Cache invalidation is famously hard. When retrofitting caching to existing code:
- Multiple code paths can trigger mutations (direct SQL edit, schema changes, relationship modifications, semantic term updates)
- Original code had no cache-awareness; new cache code can't anticipate all invalidation points
- Race conditions: write operation and cache-population execute concurrently in wrong order, leaving stale data

**Consequences:**
- Users see different results for same query at different times
- Data inconsistency difficult to trace: users can't reproduce it consistently
- Trust erosion: "I don't trust the results from this tool"
- Debugging nightmare: cache invalidation logs aren't comprehensive

**Prevention:**
- Inventory all mutation paths in code before adding cache:
  - Direct query modification
  - Schema changes
  - Connection updates
  - Semantic term changes
  - Relationship modifications
- Implement cache-key strategy that includes all upstream dependencies. Example for query cache:
  ```python
  cache_key = hash((query, schema_hash, semantic_terms_hash, relationships_hash))
  # Not just: cache_key = hash(query)
  ```
- Add instrumentation: log every invalidation operation (what key, when, what triggered it)
- Implement TTL-based expiry as fallback for cases where invalidation is missed
- Test cache invalidation explicitly:
  - Modify schema → run query → verify cache invalidated
  - Change semantic term → run query → verify cache invalidated
  - Update relationship → run query → verify cache invalidated
- Use idempotent invalidation: invalidating same key twice should be safe

**Detection:**
- User reports: "I ran this query before, got X results; now same query, got Y results"
- Timestamp checking: "Result looks 10 minutes old"
- Manual comparison: clear cache with API endpoint, run query again, see different results
- Inconsistent results across browser tabs or instances

**Which phase addresses it:** Phase 4 (Query Result Caching) — must have comprehensive test coverage before production deploy. Incomplete coverage = silent correctness bugs.

---

### Pitfall 3: Breaking Error Handling Changes in Production API

**What goes wrong:** Refactoring error handling in existing FastAPI application changes the error response structure or HTTP status codes. Clients that relied on old error format break silently or fail unexpectedly. For example:
- Old behavior: `GET /api/query` with bad connection returns `500 {"error": "Connection failed"}`
- New behavior: returns `400 {"type": "ConnectionError", "message": "...", "details": {...}}`
- Frontend error handler expects `error` field, doesn't find it, crashes on `.split()`
- Or: status code changes from 500 to 400, frontend logging expects ≥500 for "critical" errors, now silently treats as recoverable

**Why it happens:** When centralizing error handling in FastAPI (extracting from scattered try/except blocks):
- Different endpoints previously caught exceptions differently (inconsistent)
- New centralized handler enforces consistency (good), but changes response format (breaking)
- Backward compatibility not considered: only current version code is tested

**Consequences:**
- Frontend breaks in hard-to-diagnose ways (expected field missing, error swallowed)
- Error tracking system stops working (unexpected status codes)
- Client retry logic breaks (was based on old status codes)
- Production deployment causes immediate incidents

**Prevention:**
- Never change error response structure without API versioning. Maintain old format alongside new:
  ```python
  # During transition period, support both
  error_response = {
    "error": exception.message,  # Old format for backward compatibility
    "type": exception.__class__.__name__,  # New format
    "message": exception.message,  # Duplicate, but explicit
    "details": {...}  # New format
  }
  ```
- Test against old client code: create tests using old error handling logic, verify they still work
- Document error format changes explicitly with migration guide
- Use semantic versioning: major version bump (e.g., v2.0.0) for breaking changes
- Deprecation period: support old format for 2-3 releases before removing
- For status code changes: test both that new code returns correct code AND old code still works with old code

**Detection:**
- Frontend error handler throws unexpected error (e.g., `.message is undefined`)
- Sentry/monitoring shows sudden spike in error handling crashes
- Client retry logic stops working
- Load balancer health checks fail (unexpected status code from `/health`)

**Which phase addresses it:** Phase 5 (Error Handling Optimization) — must include backward compatibility tests. Any error response change needs careful phasing.

---

## Moderate Pitfalls (Architectural Debt)

### Pitfall 4: React Component Decomposition Creating Props Hell

**What goes wrong:** When splitting large React components like `ChatArea.tsx` (408 lines) into smaller components, the boundary is chosen poorly. Extracted components need so many props that they become harder to understand than the original:

```typescript
// Original large component
<ChatArea>
  // Internal state and logic

// After naive split
<ChatMessages messages={messages} onRetry={onRetry} ... 20 more props />
<ChatInput onSend={onSend} onStop={onStop} isStreaming={isStreaming} ... />
<ChatAnalytics results={results} onAnalyticsChange={onAnalyticsChange} ... />
```

Each prop is necessary, but now the component API is confusing. New developers don't know which props are required, which are internal implementation details, which trigger side effects.

**Why it happens:** Decomposition without identifying state ownership. Original component has all state; extracted components need access to all of it, so everything becomes a prop. Alternatively, components are split by visual layout, not by logical responsibility.

**Consequences:**
- Component API is harder to understand than original monolith
- Props drilling: passing unrelated props through 3+ levels of components
- Component reusability is limited: props list is too specific
- Testing is harder: need to mock many props
- Refactoring is painful: can't change internal state without updating 10 component APIs

**Prevention:**
- Before extracting, identify state ownership:
  - What state is needed by only this component?
  - What state is shared with sibling components?
  - What state is truly global (belongs in Zustand store)?
- Use custom hooks to encapsulate related state, not sub-components
- Prefer composition with children over props drilling:
  ```typescript
  <ChatArea>
    <ChatMessages />  {/* Can access parent context, no props needed */}
    <ChatInput />
  </ChatArea>
  ```
- Implement context or Zustand for frequently-drilled props
- Define explicit component API: document which props are public, which are private/deprecated
- Limit prop count: if > 8 props, reconsider the decomposition

**Detection:**
- Component has > 15 required props
- Props are unrelated (string + callback + boolean + array)
- Documentation says "just pass whatever the parent has"
- PR review: "Wait, what's this prop for?"

**Which phase addresses it:** Phase 2 (Front-end Component Decomposition) — test component APIs early, refactor boundaries if props become unwieldy.

---

### Pitfall 5: Refactoring Without Adequate Test Coverage (Untested Code Paths)

**What goes wrong:** Large files like `gptme_engine.py` have complex logic branches that aren't fully tested. Refactoring extracts this untested code into new modules without adding test coverage. Tests pass because they only covered happy path; edge cases silently break in production.

Example: `engine_repair.py` handles SQL error repair with heuristics:
```python
# Edge case: SQL contains both syntax error AND constraint violation
# Original code had 2 branches, untested branch combining both errors
# After split, refactored code in `engine_repair.py` might handle them differently
# Tests don't catch it: only tested single errors, not combination
```

**Why it happens:** Original code works (passing happy-path tests), so it seems "safe" to refactor. But refactoring reveals untested branches; moving code to new module changes execution context (imports, initialization order), exposing bugs that were latent.

**Consequences:**
- Production failures in edge cases not covered by tests
- Difficult to debug: "This branch worked before!"
- Regressions in features that seemed unrelated
- Rollback becomes necessary

**Prevention:**
- Before refactoring, audit test coverage of target module:
  ```bash
  pytest --cov=app.services.gptme_engine --cov-report=term-missing
  ```
- Identify untested branches; add test cases before refactoring
- Use Approval Tests for complex logic:
  ```python
  # Capture current behavior before refactoring
  approval_snapshot = capture_all_outputs(gptme_engine.execute, test_cases)
  ```
  After refactoring, behavior must match snapshot exactly
- Run tests frequently during refactoring (every micro-commit)
- Add integration tests for cross-module interactions (test both modules together, not in isolation)

**Detection:**
- `pytest --cov` shows < 80% coverage for module being refactored
- PR adds refactoring without adding new tests
- Post-deploy: unexpected errors in error handling or retry logic

**Which phase addresses it:** Phases 1-2 (Module Decomposition) — don't start refactoring until test coverage ≥ 80% for target module.

---

### Pitfall 6: Chinese Documentation Falling Out of Sync with English

**What goes wrong:** A Chinese README is added, but no process exists to keep it synchronized with English version. Three weeks later:
- English README documents new feature X
- Chinese README still mentions old behavior Y
- Users following Chinese docs get confused or misled
- It's unclear which documentation is authoritative

After six months: Chinese docs are 3-4 releases behind, completely untrustworthy.

**Why it happens:** Translation is treated as one-time task, not as ongoing maintenance. No version control integration; changes to English aren't automatically flagged for translation. Manual synchronization is tedious and easy to forget.

**Consequences:**
- Users trust Chinese docs less (they learn they're outdated)
- Support burden increases: "Why doesn't X work as documented?"
- Maintenance cost: someone must manually keep docs in sync
- Translation quality degrades over time (translated by different people, no consistency)

**Prevention:**
- Implement version control integration:
  - English docs live in `/docs/README.md`
  - Chinese docs live in `/docs/README.zh.md`
  - Single source of truth for both (same file, not separate files)
  - Mark sections that need translation explicitly
- Enforce process: any English docs change triggers TODO in PR for translation update
  ```markdown
  # Change: Added section on "Advanced Caching"
  - [ ] TODO: Translate new section to Chinese (docs/README.zh.md)
  ```
- Use translation memory (TM) tool like Crowdin or Transifex to:
  - Track what's been translated
  - Highlight new/changed strings needing translation
  - Prevent stale translations from being reused
- Set translation SLA: all English changes must be translated within 1 sprint
- Version documentation: include doc version number in README
  ```
  English: v2.1.0 (2026-03-29)
  Chinese: v2.0.5 (2026-02-14) — 1 release behind
  ```
- Automated check in CI: flag if Chinese docs haven't been updated in N releases

**Detection:**
- Users report outdated/incorrect Chinese documentation
- Chinese docs don't mention features from English v2.1
- Translation inconsistency: same term translated differently in different places
- No record of who translated what or when

**Which phase addresses it:** Phase 6 (Documentation) — don't publish Chinese docs without version control process in place. Otherwise maintenance burden explodes.

---

## Minor Pitfalls (Quality Degradation)

### Pitfall 7: State Management Bloat After Component Extraction

**What goes wrong:** After extracting smaller components from `SchemaSettings.tsx` (618 lines), state management balloons because each new component needs its own `useState` calls. Three `useState` calls per component × 10 extracted components = 30 scattered state variables, each with different semantics.

**Why it happens:** Naive component extraction preserves all internal state as-is. Doesn't consolidate or restructure state. Each extracted component gets its own mini-state management instead of centralizing.

**Consequences:**
- Hard to understand component interactions (state is scattered)
- Race conditions: multiple components updating related state
- Performance: excessive re-renders from state changes in unrelated components
- Maintenance nightmare: state flow is implicit and hard to trace

**Prevention:**
- After extracting components, audit state usage: do extracted components share state?
- If yes, consolidate into `useReducer` or move to Zustand store
- Rule of thumb: if component has 3+ `useState` calls, use `useReducer`
- Prefer custom hooks over multiple `useState` calls:
  ```typescript
  // Instead of: const [isOpen, setIsOpen] = useState(false); const [selectedTab, setSelectedTab] = useState(0);
  const { isOpen, selectedTab, toggle, selectTab } = useSchemaSettings();
  ```
- Test state updates: verify that unrelated state changes don't trigger unexpected re-renders

**Detection:**
- Component has > 3 `useState` calls
- State names are unrelated (no clear pattern)
- Component renders frequently on unrelated updates
- Props debugging shows unnecessary re-renders

**Which phase addresses it:** Phase 2 (Front-end Component Decomposition) — structure state correctly during initial decomposition.

---

### Pitfall 8: Performance Regression from Naive Memoization Removal

**What goes wrong:** During component decomposition, memoization (useMemo, memo) is removed from extracted components because "it's simpler without it." Now the component graph in SchemaSettings re-renders frequently on irrelevant state changes.

Before: `useMemo` prevented recalculation of node/edge arrays
After: arrays recalculated on every render, ReactFlow re-lays out entire graph

Users with large schemas (100+ tables) notice UI slowness.

**Why it happens:** Memoization seems like micro-optimization, not critical. When refactoring, developers often remove it to "simplify," assuming performance is fine.

**Consequences:**
- 200-500ms slowdown in schema visualization on large databases
- ReactFlow struggling to layout 100+ nodes repeatedly
- User perception of app being "slow"

**Prevention:**
- Profile before refactoring: `Performance` tab in DevTools to establish baseline
- After extraction, profile again: verify no performance regression
- Identify expensive operations in extracted components (layout calculations, data transformations)
- Memoize selectively:
  ```typescript
  const nodes = useMemo(() => computeNodes(schema), [schema]);
  ```
- Use React DevTools Profiler to identify unnecessary re-renders

**Detection:**
- Performance tab shows component rendering every frame (60fps → 30fps)
- Schema visualization is sluggish on 100+ table databases
- Flame graph shows ReactFlow layout algorithm running repeatedly

**Which phase addresses it:** Phase 2 (Front-end Component Decomposition) — measure performance before and after; reintroduce memoization if regression detected.

---

### Pitfall 9: Incomplete Migration from Global Exception Handler

**What goes wrong:** Refactoring the global exception handler in `main.py` (lines 112-125) to specific exception handlers for different error types isn't complete. One error type is missed:
- `SQLAlchemyError` has specific handler
- `asyncio.TimeoutError` has specific handler
- But `ValueError` still falls through to generic handler, exposing full error message in debug mode

**Why it happens:** Large exception handler with many cases; during refactoring, one case is missed or forgotten. The handler still "works," but one error type leaks sensitive information.

**Consequences:**
- One specific error type leaks internal details in DEBUG mode
- Hard to find: error handling seems consistent but isn't
- Security concern: if DEBUG=true in production (misconfiguration), one error type exposes internals

**Prevention:**
- Enumerate all exception types caught by generic handler before refactoring:
  ```python
  # Map current exceptions to specific handlers
  exc_type_to_handler = {
    SQLAlchemyError: handle_db_error,
    asyncio.TimeoutError: handle_timeout,
    ValueError: handle_value_error,
    # ... exhaustive list
  }
  ```
- Add test for each exception type, verify response format is safe:
  ```python
  def test_sqlalchemy_error_response():
    # Should NOT include stack trace
    response = simulate_db_error()
    assert "Traceback" not in response.body
    assert response.status_code == 400
  ```
- Use linter rule: flag `except Exception:` in code (only allow in specific whitelisted locations)
- PR review: ensure all exception types are accounted for

**Detection:**
- DEBUG mode shows full traceback for one error type, not others
- PR review: new exception type added but no handler
- Error logging shows unhandled exception in prod

**Which phase addresses it:** Phase 5 (Error Handling Optimization) — test all exception paths exhaustively.

---

## Phase-Specific Warnings

| Phase | Topic | Likely Pitfall | Mitigation |
|-------|-------|----------------|-----------|
| Phase 1 | Python module decomposition | Circular imports from tight coupling | Design module boundaries top-down; use TYPE_CHECKING guards; enforce one-directional dependencies |
| Phase 2 | React component extraction | Props drilling / component API bloat | Identify state ownership before extraction; use context/hooks for shared state |
| Phase 2 | Performance during refactoring | Memoization removal causing regression | Profile before/after; preserve useMemo/memo for expensive operations |
| Phase 3 | Import/export functionality (existing feature, not refactored) | Partial failure without transaction rollback | Already documented in CONCERNS.md; maintain existing transaction wrapper |
| Phase 4 | Query result caching | Stale cache from incomplete invalidation | Inventory all mutation paths; implement comprehensive cache invalidation; test all invalidation triggers |
| Phase 4 | Chat pagination/virtualization | Lost messages or ordering from incomplete migration | Add integration tests for concurrent message handling; test pagination edge cases |
| Phase 5 | Error handling refactoring | Breaking changes in error response format | Maintain backward compatibility; test against old client code; use deprecation period |
| Phase 5 | Python execution sandbox refactoring | Accidentally expanding attack surface | Maintain security constraints; don't remove resource limits; add regression tests for security |
| Phase 6 | Chinese documentation | Docs falling out of sync with English | Establish translation process before launch; version both; use translation memory tool |
| Phase 6 | Documentation | Wrong information in docs after refactoring | Update docs during refactoring, not after; link code changes to doc PRs |

---

## Cross-Cutting Concerns

### Test Coverage as Foundation
**Critical:** Do not refactor code with < 80% test coverage. Refactoring untested code is blind work; you can't verify correctness. For QueryGPT specifically:
- `gptme_engine.py` coverage status must be verified before Phase 1 decomposition
- Any split module must maintain ≥ 80% coverage
- Approval Tests are recommended for complex logic (capture pre-refactor behavior, verify post-refactor)

### Incremental Refactoring Discipline
Refactoring in small steps is critical:
1. Make one small change (extract one function)
2. Run full test suite
3. Commit if green
4. Repeat

Never bundle refactoring with feature additions or bug fixes. If refactoring breaks something, the cause is clear.

### Backward Compatibility as Design Constraint
Any change to public API (error response format, endpoint behavior, module imports) must maintain backward compatibility for at least one release. Use API versioning if breaking changes are necessary.

---

## Sources

- [Organizing Python Code into Modules for Better Organization and Reusability - llego.dev](https://llego.dev/posts/organizing-python-code-modules-better-organization-reusability/)
- [How to Refactor Complex Codebases – A Practical Guide for Devs](https://www.freecodecamp.org/news/how-to-refactor-complex-codebases/)
- [Python Circular Import: Causes, Fixes, and Best Practices | DataCamp](https://datacamp.com/tutorial/python-circular-import)
- [Circular Imports in Python: The Architecture Killer That Breaks Production - DEV Community](https://dev.to/vivekjami/circular-imports-in-python-the-architecture-killer-that-breaks-production-539f)
- [React components composition: how to get it right](https://www.developerway.com/posts/components-composition-how-to-get-it-right)
- [When to break up a component into multiple components](https://kentcdodds.com/blog/when-to-break-up-a-component-into-multiple-components)
- [Cache Invalidation - Redis](https://redis.io/glossary/cache-invalidation/)
- [Why Your UI Won't Update: Debugging Stale Data and Caching in React Apps](https://www.freecodecamp.org/news/why-your-ui-wont-update-debugging-stale-data-and-caching-in-react-apps/)
- [10 Common Mistakes in API Error Handling & How to Fix Them - DEV Community](https://dev.to/codanyks/10-common-mistakes-in-api-error-handling-how-to-fix-them-1m44)
- [Error Handling in APIs: Crafting Meaningful Responses - API7.ai](https://api7.ai/learning-center/api-101/error-handling-apis)
- [Building Production-Ready FastAPI Applications with Service Layer Architecture in 2025 | by Abhinav Dobhal | Medium](https://medium.com/@abhinav.dobhal/building-production-ready-fastapi-applications-with-service-layer-architecture-in-2025-f3af8a6ac563)
- [Would You Refactor Without Tests? This Is Why You Have Trust Issues - CodeToDeploy | Medium](https://medium.com/codetodeploy/would-you-refactor-without-tests-this-is-why-you-have-trust-issues-7ce54fbcec2c)
- [Do You Refactor Without Tests? It's Time for Safety | Quality Coding](https://qualitycoding.org/dont-refactor-without-tests/)
- [Chinese Technical Translations: Best Practices for Accuracy - Chinese Translation Services](https://chinesetranslationservices.com/chinese-technical-translations-best-practices-for-accuracy/)
- [Translation Versioning System: Content Control & Management - Translated](https://translated.com/resources/translation-versioning-system-content-control-management/)
- [React Hooks — Common pitfalls and Best Practices | by Harsh Maheshwari | Medium](https://hrshdg8.medium.com/react-hooks-common-pitfalls-and-best-practices-96079a40870c/)
- [The Hidden Dangers of Custom Hooks in React: Optimizing Performance and State Management | Muvon](https://blog.muvon.io/frontend/hidden-costs-of-custom-hooks-in-react)
