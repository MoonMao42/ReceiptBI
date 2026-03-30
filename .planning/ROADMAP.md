# Roadmap: QueryGPT 精进

**Milestone:** QueryGPT 优化迭代
**Created:** 2026-03-29
**Granularity:** COARSE (3-5 phases)
**Status:** Phases 1-2 COMPLETE. Phase 3 ready for execution.

## Phases

- [x] **Phase 1: Backend Service Decomposition** ✓ COMPLETE - Modularize gptme_engine.py, standardize error handling, secure configuration
- [x] **Phase 2: Frontend Component Optimization** ✓ COMPLETE - Split large components, implement message pagination with virtual scrolling
- [ ] **Phase 3: Chinese Documentation** - Complete Chinese README and documentation

## Phase Details

### Phase 1: Backend Service Decomposition

**Goal:** Refactor gptme_engine.py from a 990-line monolith into focused service modules (SQLExecutor, PythonSandbox, ResultProcessor, VisualizationEngine, GptmeEngine orchestrator), maintaining full API compatibility while improving code quality and maintainability.

**Depends on:** Nothing (first phase)

**Requirements:** BACK-01, BACK-02, BACK-03, BACK-04, BACK-05, BACK-06

**Success Criteria** (what must be TRUE):
1. Users can run all existing API endpoints with identical behavior — SSE event format unchanged, no functionality gaps
2. All existing test suite passes, no regressions detected in unit/integration tests
3. Error responses use explicit exception types (SQLAlchemyError, asyncio.TimeoutError, etc.) instead of bare except clauses
4. Non-development environments require explicit ENCRYPTION_KEY configuration — application fails fast if missing
5. Bug fixes and dead code removal from refactoring are tracked and documented in commits

**Plans:** 7 plans organized by execution wave

| Plan | Wave | Status | Objective |
|------|------|--------|-----------|
| 01-01 | 1 | ✓ Created | Analyze and create SQLExecutor service module |
| 01-02 | 1 | ✓ Created | Create PythonSandbox and ResultProcessor service modules |
| 01-03 | 2 | ✓ Created | Create VisualizationEngine and refactor GptmeEngine orchestrator |
| 01-04 | 2 | ✓ Created | Standardize error handling (BACK-03, BACK-05) |
| 01-05 | 2 | ✓ Created | Secure encryption key configuration (BACK-04, BACK-05) |
| 01-06 | 3 | ✓ Created | Run tests and validate API compatibility (BACK-02) |
| 01-06b | 3 | ✓ Complete | Execute service tests and code review (BACK-06) |

### Phase 2: Frontend Component Optimization

**Goal:** Decompose large React components (ChatArea 408 lines, SchemaSettings 618 lines) into maintainable sub-components with custom hooks, implement message pagination with backend API support, and optimize rendering performance with virtual scrolling for conversations with 1000+ messages.

**Depends on:** Phase 1 (stable API contracts)

**Requirements:** FRONT-01, FRONT-02, FRONT-03, FRONT-04, FRONT-05, FRONT-06, FRONT-07

**Success Criteria** (what must be TRUE):
1. ChatArea and SchemaSettings are decomposed into focused sub-components, each <120 lines, with clear responsibility boundaries
2. Message history pagination works end-to-end: backend API serves paginated messages, frontend loads additional messages on scroll
3. Virtual scrolling renders large message lists (1000+ messages) without UI stutter, maintains smooth 60 FPS scrolling
4. Schema relationship suggestions are cached (memoized), avoiding recalculation on component re-renders
5. Bug fixes and race conditions found during refactoring are documented in commits

**Plans:** 5 plans organized by execution wave

| Plan | Wave | Status | Objective |
|------|------|--------|-----------|
| 02-01 | 1 | ✓ COMPLETE | ChatArea decomposition: MessageList, InputBar sub-components (FRONT-01) |
| 02-02 | 1 | ✓ COMPLETE | SchemaSettings decomposition: SchemaGraph, RelationshipPanel, LayoutControls (FRONT-02) |
| 02-03 | 2 | ✓ COMPLETE | Message pagination API + useMessagePagination + useMessageVirtualizer hooks (FRONT-03, FRONT-04) |
| 02-04 | 3 | ✓ COMPLETE | Schema optimization: memoized nodes/edges, useSchemaLayout hook (FRONT-05, FRONT-06) |
| 02-05 | 4 | ✓ COMPLETE | Testing, verification, bug documentation (FRONT-07) |

**UI hint:** yes

### Phase 3: Chinese Documentation

**Goal:** Create complete Chinese language documentation (README.zh.md) with feature parity to English README, enabling Chinese-speaking developers and users to understand and contribute to QueryGPT.

**Depends on:** Nothing (can run in parallel)

**Requirements:** DOC-01

**Success Criteria** (what must be TRUE):
1. README.zh.md is complete with all major sections translated: Features, Quick Start, Tech Stack, Configuration, Development, Troubleshooting
2. Chinese documentation maintains feature and content parity with English version
3. Technical terminology is consistent across documentation (e.g., "semantic layer" = "语义层")

**Plans:** TBD

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Backend Service Decomposition | 7/7 | ✓ COMPLETE | 01-01, 01-02, 01-03, 01-04, 01-05, 01-06, 01-06b |
| 2. Frontend Component Optimization | 1/5 | ✓ EXECUTING | 02-03 ✓ (FRONT-03, FRONT-04 satisfied) |
| 3. Chinese Documentation | 0/? | Not started | — |

---

**Next:** Execute Phase 2 plans (Frontend Component Optimization) via `/gsd:execute-phase 02`. Phase 1 complete with 100% plan execution and all requirements satisfied (BACK-01 through BACK-06).
