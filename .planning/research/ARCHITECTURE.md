# Refactoring Architecture Strategy

**Domain:** AI Database Assistant (Next.js + FastAPI)
**Researched:** 2026-03-29
**Focus:** Decomposing monolithic services and components into focused, testable modules while maintaining API compatibility

## Executive Summary

QueryGPT's architecture is fundamentally sound with clear separation between frontend (Next.js/React), backend API (FastAPI), and business logic layers. However, two critical files have grown beyond maintainability thresholds:

1. **Backend:** `gptme_engine.py` (990 lines) — Monolithic execution engine combining AI orchestration, code extraction, diagnostics, and visualization
2. **Frontend:** `SchemaSettings.tsx` (618 lines) + `ChatArea.tsx` (408 lines) — Large components mixing state management, UI rendering, and complex logic

The refactoring strategy focuses on **modular decomposition without breaking API contracts**, preserving the working SSE streaming architecture and async patterns while making code easier to test, maintain, and extend.

**Key Principle:** Refactor internally, preserve external contracts. The `/api/v1/chat/stream` endpoint and frontend component APIs remain unchanged; internal module boundaries shift to enforce single responsibility.

## Current Architecture Constraints & Opportunities

### Backend Constraint: The `gptme_engine.py` Monolith

**What it does (990 lines):**
- AI model invocation (LiteLLM wrapper) with streaming
- SQL generation, execution, and error recovery (auto-repair)
- Python code extraction, validation (AST-based security), and execution
- Result visualization (chart config generation)
- Diagnostic data collection (error categorization)
- Message accumulation (streaming event batching)

**Why it's monolithic:**
- Single class `GptmeEngine` with 20+ methods handling disparate concerns
- Tight coupling: code extraction → validation → execution → visualization in one linear path
- Hard to test individual stages without running full pipeline
- Difficult to swap implementations (e.g., test different execution strategies)

**Refactoring Target:**
```
gptme_engine.py (990 lines)
├── core orchestrator (200 lines) — keeps public API
├── sql_executor.py — SQL generation + execution + repair (250 lines)
├── python_sandbox.py — Validation + execution + security (150 lines)
├── result_processor.py — Extraction + cleaning + diagnostics (200 lines)
└── visualization.py — Chart generation (moved from engine_visualization) (100 lines)
```

### Frontend Constraints: Component Sprawl

#### ChatArea (408 lines)
**Mixes:**
- UI state (dropdowns, input focus)
- Data fetching (connections, models, conversations)
- Business logic (selection persistence, initialization)
- Rendering (header, input form, message display)

**Refactoring Target:**
```
ChatArea.tsx (408 lines)
├── ChatArea.tsx (120 lines) — Container/layout only
├── hooks/
│   ├── useChatSelector.ts — Connection/model selection logic
│   ├── useChatInitialization.ts — Initialization effects
│   └── useChatData.ts — Data fetching (connections, models)
├── components/
│   ├── ChatHeader.tsx — Header UI
│   ├── ChatToolbar.tsx — Connection/model selectors
│   └── ChatInput.tsx — Message input form
```

#### SchemaSettings (618 lines)
**Mixes:**
- Draggable graph UI (ReactFlow state)
- Relationship management (CRUD operations)
- Layout persistence (save/restore viewport)
- Table filtering and search

**Refactoring Target:**
```
SchemaSettings.tsx (618 lines)
├── SchemaSettings.tsx (150 lines) — Container only
├── components/
│   ├── SchemaGraph.tsx — ReactFlow UI wrapper (200 lines)
│   ├── RelationshipPanel.tsx — Relationship CRUD (150 lines)
│   └── LayoutManager.tsx — Layout save/restore (100 lines)
├── hooks/
│   ├── useSchemaGraph.ts — Node/edge state management
│   ├── useRelationshipManager.ts — Relationship operations
│   └── useLayoutManager.ts — Layout persistence
```

## Recommended Refactoring Architecture

### Phase 1: Backend Service Decomposition (Lower Risk)

**Order:** Backend first because it's less visible to users, easier to refactor incrementally.

#### 1.1 Extract SQL Execution Module

**File:** `apps/api/app/services/sql_executor.py`

**Responsibility:**
- SQL query generation via LLM
- SQL execution against database
- Error detection and auto-repair (retry with error feedback)

**Interface:**
```python
class SQLExecutor:
    async def generate_sql(
        self,
        query: str,
        context: QueryContext
    ) -> str:
        """Returns SQL text or raises GenerationError"""

    async def execute(
        self,
        sql: str,
        connection: DatabaseConnection
    ) -> tuple[list[dict], bool]:
        """Returns (results, success) or raises ExecutionError"""

    async def repair_and_retry(
        self,
        sql: str,
        error: str,
        context: QueryContext
    ) -> str:
        """Returns repaired SQL or raises RepairError"""
```

**Current Home:** Scattered across `GptmeEngine` lines 400-650
**Why Extract:** SQL concerns are independent; can be tested in isolation; reusable by other modules

#### 1.2 Extract Python Sandbox Module

**File:** `apps/api/app/services/python_sandbox.py`

**Responsibility:**
- Python code validation (AST security analysis)
- Dependency checking (verify required libraries available)
- Safe execution with resource limits
- Injection of SQL data into execution context

**Interface:**
```python
class PythonSandbox:
    def validate_code(self, code: str) -> ValidationResult:
        """Returns OK or list of security violations"""

    def validate_dependencies(self, code: str) -> DependencyCheck:
        """Checks if imports are available"""

    async def execute(
        self,
        code: str,
        sql_data: dict[str, DataFrame],
        timeout: int = 30
    ) -> ExecutionResult:
        """Executes in isolated IPython environment"""

    def inject_sql_results(self, name: str, data: list[dict]):
        """Makes SQL results available as variable"""
```

**Current Home:** `python_runtime.py` (10 KB) + validation in `GptmeEngine`
**Why Extract:** Keep Python runtime isolated from engine orchestration; reusable for testing; clear security boundary

#### 1.3 Extract Result Processor Module

**File:** `apps/api/app/services/result_processor.py`

**Responsibility:**
- Extract SQL/Python code blocks from LLM output
- Parse structured data (JSON, thinking markers)
- Categorize and format error information
- Prepare diagnostic metadata

**Interface:**
```python
class ResultProcessor:
    def extract_sql_block(self, content: str) -> str | None:
        """Extracts SQL code from LLM response"""

    def extract_python_block(self, content: str) -> str | None:
        """Extracts Python code from LLM response"""

    def parse_diagnostics(
        self,
        error: Exception,
        stage: str
    ) -> DiagnosticEntry:
        """Categorizes error for UI display"""

    def clean_for_display(self, content: str) -> str:
        """Removes thinking markers, formats for frontend"""
```

**Current Home:** `engine_content.py` (2.3 KB, basic) + `engine_diagnostics.py` (4.3 KB) + inline in `GptmeEngine`
**Why Extract:** Consolidates all content parsing in one place; testable independently; reusable by multiple code paths

#### 1.4 Extract Visualization Module

**File:** `apps/api/app/services/visualization_engine.py`

**Responsibility:**
- Chart specification generation from Python output
- Validate chart config format
- Handle unsupported chart types gracefully

**Interface:**
```python
class VisualizationEngine:
    async def generate_from_python(
        self,
        python_output: str,
        execution_context: dict
    ) -> VisualizationSpec | None:
        """Extracts chart from Python output"""

    def validate_spec(self, spec: dict) -> bool:
        """Checks chart config is valid"""

    def fallback_spec(self, data: dict) -> VisualizationSpec:
        """Generates basic table when chart generation fails"""
```

**Current Home:** `engine_visualization.py` (2.7 KB, incomplete)
**Why Extract:** Visualization is independent of execution; can be tested separately; allows A/B testing different visualization strategies

#### 1.5 Refactored GptmeEngine (Orchestrator)

**File:** `apps/api/app/services/gptme_engine.py` (refactored)

**What It Keeps:**
- Public API unchanged: `async def chat_generator()` returning `AsyncGenerator[SSEEvent]`
- Configuration/initialization interface
- Model resolution and parameter passing
- Error handling at orchestration level

**What It Delegates:**
- SQL concerns → `SQLExecutor`
- Python concerns → `PythonSandbox`
- Content extraction → `ResultProcessor`
- Visualization → `VisualizationEngine`

**New Structure:**
```python
class GptmeEngine:
    """Orchestrates multi-step execution pipeline"""

    def __init__(self, ...config...):
        self.sql_executor = SQLExecutor(...)
        self.python_sandbox = PythonSandbox(...)
        self.result_processor = ResultProcessor(...)
        self.visualizer = VisualizationEngine(...)

    async def chat_generator(
        self,
        query: str,
        context: QueryContext
    ) -> AsyncGenerator[SSEEvent, None]:
        """Pipeline orchestrator — calls components in sequence"""

        # Stage 1: SQL generation
        sql = await self.sql_executor.generate_sql(query, context)
        yield SSEEvent.progress("sql_generated", sql)

        # Stage 2: SQL execution
        try:
            results, success = await self.sql_executor.execute(sql, context.connection)
        except SQLError as e:
            sql = await self.sql_executor.repair_and_retry(sql, str(e), context)
            yield SSEEvent.progress("sql_repaired", sql)
            results, success = await self.sql_executor.execute(sql, context.connection)

        # Stage 3: Python analysis
        if self.python_sandbox.validate_code(python_code).ok:
            self.python_sandbox.inject_sql_results("results", results)
            py_output = await self.python_sandbox.execute(python_code)
            yield SSEEvent.progress("python_done", py_output)

        # Stage 4: Visualization
        chart = await self.visualizer.generate_from_python(py_output, context)
        if chart:
            yield SSEEvent.visualization(chart)

        # Stage 5: Done
        yield SSEEvent.done()
```

**Reduced from 990 → ~200 lines** (core logic only; detail moves to modules)

**Build Order Dependency:**
```
SQLExecutor
PythonSandbox
ResultProcessor
VisualizationEngine
     ↓
GptmeEngine (imports all above)
     ↓
ExecutionService (unchanged, imports GptmeEngine)
     ↓
chat_stream() endpoint (unchanged)
```

---

### Phase 2: Frontend Component Decomposition (Higher Risk, Do After Backend Stabilizes)

**Rationale:** Frontend changes affect UX more directly. Decompose only after backend is stable and tested.

#### 2.1 ChatArea Refactoring

**Current:** One 408-line component handling selection, data fetching, input, and rendering.

**Target Structure:**

```
ChatArea/
├── ChatArea.tsx (120 lines)
│   └── Container: fetches initial data, manages conversation ID
├── hooks/
│   ├── useChatSelector.ts (80 lines)
│   │   └── Selection logic: connection/model persistence, defaults
│   ├── useChatInitialization.ts (60 lines)
│   │   └── Init effects: load saved selections, validate against available options
│   └── useChatData.ts (40 lines)
│       └── Query definitions: connections, models, app settings
├── components/
│   ├── ChatHeader.tsx (60 lines)
│   │   └── Header bar: title, settings link
│   ├── ChatToolbar.tsx (120 lines)
│   │   └── Connection/Model dropdowns with search
│   ├── ChatInput.tsx (60 lines)
│   │   └── Text input + Send button
│   └── MessageList.tsx (80 lines)
│       └── Scrollable message container
```

**Benefits:**
- Each component <120 lines (single responsibility)
- Hooks are independently testable
- Easier to add features (e.g., quick-switch favorite connections)
- Can memoize components to prevent unnecessary re-renders

#### 2.2 SchemaSettings Refactoring

**Current:** One 618-line component mixing ReactFlow UI, CRUD operations, layout persistence.

**Target Structure:**

```
SchemaSettings/
├── SchemaSettings.tsx (100 lines)
│   └── Container: loads schema, manages selected layout
├── components/
│   ├── SchemaGraph.tsx (200 lines)
│   │   └── ReactFlow wrapper with draggable nodes/edges
│   ├── RelationshipPanel.tsx (120 lines)
│   │   └── CRUD: add/edit/delete relationships, suggestions
│   ├── LayoutManager.tsx (90 lines)
│   │   └── Save/Load/Delete layouts, layout selector
│   └── TableSearch.tsx (50 lines)
│       └── Search input + filter by name/visibility
├── hooks/
│   ├── useSchemaGraph.ts (80 lines)
│   │   └── ReactFlow state: nodes, edges, layout
│   ├── useRelationshipManager.ts (100 lines)
│   │   └── Mutations: add, update, delete relationships
│   └── useLayoutManager.ts (80 lines)
│       └── Layout CRUD operations + persistence
└── lib/
    ├── schema-graph.ts (100 lines)
    │   └── Utilities: build nodes, build edges, calculate positions
    └── relationships.ts (50 lines)
        └── Utilities: validate relationship, suggest relationships
```

**Benefits:**
- Graph UI isolated from relationship logic
- Layout persistence separated from data fetching
- Each component testable in isolation
- Easier to add features (e.g., relationship templates, auto-layout)

#### 2.3 AssistantMessageCard Refactoring

**Current:** One 288-line component rendering SQL, results, charts, Python output, diagnostics.

**Target Structure:**

```
AssistantMessageCard/
├── AssistantMessageCard.tsx (120 lines)
│   └── Tab container + dispatcher to sub-components
├── components/
│   ├── MessageSummaryTab.tsx (60 lines)
│   │   └── Friendly summary of execution
│   ├── MessageSQLTab.tsx (40 lines)
│   │   └── SQL code with syntax highlighting
│   ├── MessageDataTab.tsx (50 lines)
│   │   └── Data table with pagination
│   ├── MessageChartTab.tsx (40 lines)
│   │   └── Chart renderer (delegated to ChartDisplay)
│   ├── MessagePythonTab.tsx (50 lines)
│   │   └── Python code + execution output
│   └── MessageDiagnosticsTab.tsx (60 lines)
│       └── Error details + recovery suggestions
```

**Benefits:**
- Each tab is independent and testable
- Easier to lazy-load expensive tabs (charts, diagnostics)
- Can add tab caching to reduce re-renders
- Easier to add new tabs (e.g., JSON export, alternative visualizations)

---

### Phase 3: Data Layer Optimization (Parallel with Phase 2)

#### 3.1 Chat Message Pagination

**Current State:**
- Backend: `history.py` has pagination (limit/offset) for conversations, but **not for individual messages**
- Frontend: Loads all messages for a conversation at once

**Problem:** Large conversations (100+ messages) cause:
- Slow initial load
- Large JSON payloads
- Memory bloat in React state

**Solution: Lazy-Load Messages**

**Backend Changes:**
```python
# apps/api/app/api/v1/history.py — ADD new endpoint
@router.get("/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[PaginatedResponse[MessageResponse]]:
    """Paginated message retrieval"""
    query = select(Message).where(Message.conversation_id == conversation_id)
    total = await db.scalar(select(func.count()).select_from(query.subquery()))

    messages = await db.execute(
        query.order_by(Message.created_at.asc())
        .offset(offset)
        .limit(limit)
    )
    return APIResponse.ok(
        data=PaginatedResponse.create(
            items=[MessageResponse.model_validate(m) for m in messages],
            total=total,
            page=(offset // limit) + 1,
            page_size=limit,
        )
    )
```

**Frontend Changes:**
- Use TanStack Query with infinite scroll
- Load initial 20 messages
- Load older messages as user scrolls up
- Load newer messages automatically when new message arrives

**Benefits:**
- First paint 50% faster (20 messages vs. all)
- Memory usage scales with visible messages, not conversation size
- Supports large conversations (1000+ messages)

#### 3.2 Query Result Caching

**Current State:**
- No caching layer for query results
- Same SQL query re-executed if user retries same query in conversation

**Problem:**
- Repeated queries hit database unnecessarily
- Large result sets sent multiple times

**Solution: Result Cache with TTL**

**Where to Add:**
```python
# apps/api/app/services/result_cache.py
class QueryResultCache:
    """In-memory cache for SQL execution results with TTL"""

    def __init__(self, ttl_seconds: int = 300):  # 5 min default
        self.cache: dict[str, tuple[list[dict], float]] = {}
        self.ttl = ttl_seconds

    def cache_key(self, connection_id: UUID, sql: str) -> str:
        return hashlib.sha256(f"{connection_id}:{sql}".encode()).hexdigest()

    def get(self, key: str) -> list[dict] | None:
        if key in self.cache:
            results, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl:
                return results
            del self.cache[key]
        return None

    def set(self, key: str, results: list[dict]) -> None:
        self.cache[key] = (results, time.time())

# Usage in SQLExecutor
class SQLExecutor:
    async def execute(self, sql: str, connection: DatabaseConnection) -> tuple[list[dict], bool]:
        cache_key = self.cache.cache_key(connection.id, sql)
        cached = self.cache.get(cache_key)
        if cached:
            return cached, True  # served from cache

        results = await self._execute_db(sql, connection)
        self.cache.set(cache_key, results)
        return results, True
```

**Benefits:**
- Repeated queries hit cache (network + DB time saved)
- TTL prevents stale data
- Easy to add persistent cache (Redis) later
- No API changes required

---

## Data Flow After Refactoring

### Chat Streaming Flow (Unchanged)
```
ChatArea.tsx
  ↓
useChatStore.sendMessage()
  ↓
GET /api/v1/chat/stream (SSE)
  ↓
chat_stream() endpoint
  ↓
ExecutionService
  ↓
GptmeEngine (NEW ORCHESTRATOR)
  ├── SQLExecutor.generate_sql()
  ├── SQLExecutor.execute() [WITH CACHE]
  ├── PythonSandbox.execute()
  ├── VisualizationEngine.generate()
  ↓
SSE events → Frontend (UNCHANGED)
  ↓
useChatStore updates messages
  ↓
AssistantMessageCard renders tabs
```

**Key:** All changes are internal to services. SSE events and frontend subscriptions remain identical.

### Message Loading Flow (NEW)

```
Sidebar → Click conversation
  ↓
useChatStore.loadConversation(id)
  ↓
GET /api/v1/history/{conversation_id}  [EXISTING]
  ↓
Load initial 20 messages
  ↓
Render message list with "Load older" button
  ↓
User scrolls up → Load more
  ↓
GET /api/v1/history/{conversation_id}/messages?offset=20&limit=20
  ↓
Append to message list
```

---

## Component Boundaries & Communication

### Backend Services

| Module | Responsibility | Inputs | Outputs | Talks To |
|--------|---|---|---|---|
| `SQLExecutor` | SQL generation, execution, repair | Query text, DB connection | SQL text, Results | LLM API, Database |
| `PythonSandbox` | Code validation, safe execution | Python code, SQL data | Execution output | IPython kernel |
| `ResultProcessor` | Content extraction, diagnostics | LLM response, errors | Extracted code, diagnostic data | Analyzers (AST, categorizers) |
| `VisualizationEngine` | Chart generation | Python output, context | Chart spec | Chart libraries |
| `GptmeEngine` | Pipeline orchestration | Query, context | SSE events | All four above |

### Frontend Components

| Component | Responsibility | Uses | Provides |
|-----------|---|---|---|
| `ChatArea` | Container, data loading | hooks (selector, init, data) | Input + Message display |
| `ChatToolbar` | Connection/model dropdowns | useChatSelector | Selected connection/model |
| `ChatInput` | Text input, send button | useChatStore | Submitted queries |
| `MessageList` | Scrollable messages | usePaginatedMessages | Visible messages, pagination |
| `AssistantMessageCard` | Tab-based message display | components (tabs) | Formatted message content |
| `SchemaSettings` | Container | hooks (graph, layout, relationships) | Graph UI + panels |
| `SchemaGraph` | Draggable node/edge rendering | useSchemaGraph | Visual relationships |

---

## Build Order & Testing Strategy

### Phase 1: Backend (Lower Risk)

**Order:**
1. **Extract `ResultProcessor`** (safest, no side effects)
   - Move parsing logic from `gptme_engine.py` and `engine_*.py` files
   - Test: Unit tests for extraction, diagnostics, cleaning

2. **Extract `PythonSandbox`** (independent, already somewhat isolated)
   - Move from `python_runtime.py` + `GptmeEngine` validation logic
   - Test: Unit tests for validation, security checks, execution

3. **Extract `SQLExecutor`** (depends on Result Processor)
   - Move SQL generation, execution, repair from `GptmeEngine`
   - Integrate `ResultProcessor` for error handling
   - Test: Unit tests with mocked DB and LLM

4. **Extract `VisualizationEngine`** (independent)
   - Move from `engine_visualization.py`, integrate with `ResultProcessor`
   - Test: Unit tests for chart generation and fallbacks

5. **Refactor `GptmeEngine`** (ties everything together)
   - Remove 800 lines of detail, keep orchestration
   - Orchestrate calls to four modules above
   - Test: Integration tests for full pipeline, E2E tests via API

**Testing approach:**
- Unit tests for each new module (3-5 tests per module)
- Mock external dependencies (LLM, DB)
- Integration test: Full execution pipeline with fixtures
- E2E test: Chat endpoint with real model/connection (optional, slow)

### Phase 2: Frontend (Higher Risk, After Phase 1 Stabilizes)

**Order (one component at a time):**
1. **Decompose `AssistantMessageCard`** (lowest risk, can be done in parallel with Phase 1)
   - Split tabs into separate components
   - Keep parent component identical
   - Test: Component snapshot tests, tab switching

2. **Decompose `ChatArea`** (medium risk)
   - Extract hooks, component tree
   - No API changes, just state management
   - Test: Hook tests, component render tests

3. **Decompose `SchemaSettings`** (highest risk, most complex)
   - Extract graph, layout, relationship panels
   - ReactFlow state management crucial
   - Test: Graph manipulation tests, CRUD operation tests

---

## Pitfalls & Mitigations

### Backend Pitfalls

| Pitfall | Consequence | Mitigation |
|---------|-------------|-----------|
| **Breaking ExecutionService contract** | Chat endpoint fails for all users | Keep public `GptmeEngine` interface identical; only move internal implementation |
| **Circular imports** (e.g., ResultProcessor imports SQLExecutor, vice versa) | Import errors at runtime | Keep modules independent; use dependency injection instead of direct imports |
| **Losing error recovery** during refactoring | User queries fail silently | Add detailed logging at module boundaries; test error paths explicitly |
| **Cache invalidation bugs** | Stale results served to users | Use short TTL (5 min default); add cache bypass parameter for testing |
| **Python sandbox escape** via new code paths | Security regression | All Python execution must go through PythonSandbox; AST validation non-negotiable |

### Frontend Pitfalls

| Pitfall | Consequence | Mitigation |
|---------|-------------|-----------|
| **Breaking message pagination** in middle of conversation | Message loss or duplication | Test with conversations 50+ messages; verify offset/limit logic |
| **Unnecessary re-renders** after component split | Performance degradation | Use React.memo on leaf components; memoize hook results with useMemo |
| **State sync issues** between hooks | Inconsistent UI state | Test hook interactions; use single source of truth (Zustand store) |
| **SchemaSettings graph resets** during refactoring | User loses viewport/layout | Preserve ReactFlow state in separate hook; test viewport restoration |
| **Breaking SSE event handling** during ChatArea refactoring | Messages not displayed | Keep SSE event handling in top-level store; test event dispatch separately |

---

## Suggested Phase Sequencing for Roadmap

Based on risk and dependencies:

### Phase N (Before Refactoring Starts)
- Establish baseline tests (3-5 integration tests per major component)
- Document current behavior (especially error paths)
- Set up feature flag for gradual rollout (optional but recommended)

### Phase N+1 (Backend Services)
**Objective:** Decompose backend without changing API surface
- Week 1-2: ResultProcessor extraction + tests
- Week 2-3: PythonSandbox extraction + tests
- Week 3-4: SQLExecutor extraction + tests
- Week 4-5: VisualizationEngine extraction + tests
- Week 5-6: GptmeEngine orchestration refactoring + integration tests
- Week 6: Regression testing (E2E with real model/connection)

### Phase N+2 (Frontend Components + Data Layer)
**Objective:** Improve component maintainability and message loading
- Week 1-2: ChatArea decomposition (hooks + components)
- Week 2-3: AssistantMessageCard tab split (low risk, can parallel phase N+1 week 5+)
- Week 3-4: SchemaSettings decomposition (graph, layout, panels)
- Week 4-5: Message pagination implementation + tests
- Week 5-6: Query result caching implementation + integration
- Week 6: Regression testing + E2E scenarios

### Phase N+3 (Hardening)
- Performance profiling (message load time, component render time)
- Security audit of refactored code
- Documentation updates

---

## Quality Gates for Refactoring

**Before Merging Each Phase:**

- [ ] No API contract changes (same request/response shapes)
- [ ] All existing tests pass + new tests added for refactored modules
- [ ] Code coverage maintained or improved (ideally 70%+ for services)
- [ ] Error handling paths verified (manual test of error scenarios)
- [ ] Performance not degraded (response times within 5% of baseline)
- [ ] Frontend: no additional DOM nodes / CSS changes
- [ ] Documentation updated (docstrings, README)

**After Phase Completion:**
- [ ] E2E test suite passes (chat flow, schema editing, message history)
- [ ] User-facing behavior unchanged (visual/functional)
- [ ] Security audit complete (especially Python sandbox)
- [ ] Performance baseline established for next phase

---

## Source Files Affected

### Python Backend
- **To Decompose:** `apps/api/app/services/gptme_engine.py` (990 lines)
- **To Extract From:** `engine_content.py`, `engine_diagnostics.py`, `engine_prompts.py`, `engine_visualization.py`, `python_runtime.py`
- **To Create:** `sql_executor.py`, `python_sandbox.py`, `result_processor.py`, `visualization_engine.py`, `result_cache.py`
- **Unchanged:** `chat.py` (endpoint), `execution.py` (service), `execution_context.py` (resolver)

### React Frontend
- **To Decompose:** `ChatArea.tsx` (408 lines), `SchemaSettings.tsx` (618 lines)
- **To Split:** `AssistantMessageCard.tsx` (288 lines)
- **To Create:** Hooks directory, sub-components, utilities
- **Unchanged:** `chat-helpers.ts`, `stores/chat.ts` (Zustand), API client

### API Endpoints
- **To Add:** `GET /api/v1/history/{conversation_id}/messages` (pagination)
- **Unchanged:** `GET /api/v1/chat/stream` (SSE), all config/schema endpoints

