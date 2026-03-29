# Architecture

**Analysis Date:** 2026-03-29

## Pattern Overview

**Overall:** Layered request-driven architecture with streaming SSE (Server-Sent Events) for real-time chat, built on Next.js/React frontend and FastAPI backend.

**Key Characteristics:**
- Frontend and backend are fully decoupled microservices communicating via HTTP/SSE
- SSE streaming for real-time chat event propagation (query progress, SQL generation, execution, Python analysis)
- Zustand-based client state management with optimistic updates
- Execution engine wraps a multi-step AI workflow (gptme-based) with auto-repair capabilities
- Single-workspace model (not multi-tenant) for configuration and settings
- Server-side session/conversation persistence with SQLAlchemy ORM

## Layers

**Presentation Layer (Frontend):**
- Purpose: User-facing chat, settings, schema visualization interfaces
- Location: `apps/web/src`
- Contains: React components, pages, Zustand stores, API client
- Depends on: axios client for HTTP/SSE communication
- Used by: Browser/Electron desktop client

**API Gateway Layer (Backend):**
- Purpose: RESTful API endpoints for chat, configuration, history
- Location: `apps/api/app/api/v1`
- Contains: FastAPI route handlers, request validation, SSE response formatting
- Depends on: Database session, execution services
- Used by: Frontend chat interface, settings panel

**Execution/Business Logic Layer (Backend):**
- Purpose: Query execution workflow (SQL generation → Python analysis → visualization)
- Location: `apps/api/app/services/execution.py`, `gptme_engine.py`, `python_runtime.py`
- Contains: ExecutionService orchestrates multi-step LLM calls with streaming
- Depends on: Model runtime (LiteLLM), database adapter, Python sandbox
- Used by: Chat API handler

**Data Access Layer (Backend):**
- Purpose: Database connection pooling, ORM models, query builders
- Location: `apps/api/app/db`, `app/models`
- Contains: SQLAlchemy table definitions, session management, encryption utilities
- Depends on: SQLAlchemy async engine
- Used by: All service layers

**Cross-Service Communication:**
- HTTP/REST: Frontend ↔ Backend API endpoints
- SSE: Backend → Frontend event streaming for chat progress

## Data Flow

**Chat Message Flow:**

1. User types query in ChatArea component (`apps/web/src/components/chat/ChatArea.tsx`)
2. Frontend calls `useChatStore.sendMessage()` which makes GET request to `/api/v1/chat/stream`
3. Zustand store manages local message state optimistically while awaiting server response
4. Client-side SSE reader (`createSecureEventStream`) opens event stream to backend
5. Backend `chat_stream` endpoint:
   - Gets or creates conversation record
   - Creates user message in database
   - Initializes ExecutionService with resolved model/connection
   - Starts streaming events to client via EventSourceResponse
6. Backend execution pipeline emits SSE events for each stage:
   - `progress` event: workflow stage (start, context_ready, sql_generated, executing, etc.)
   - `sql_execute` event: generated SQL query
   - `sql_result` event: query results as JSON
   - `python_run` event: Python code to execute
   - `python_output` event: Python execution results
   - `visualization` event: Chart specification
   - `error` event: failure with code and message
   - `done` event: final assistant message ID
7. Frontend's SSE event handler updates Zustand store, which triggers re-renders
8. AssistantMessageCard displays accumulated response (SQL, results, charts, Python output)

**Configuration Sync Flow:**

1. User edits model/connection settings in Settings page
2. Frontend posts to `/api/v1/config/models` or `/api/v1/config/connections`
3. Backend validates, encrypts secrets, persists to database
4. Frontend invalidates TanStack Query cache for connections/models
5. Next chat uses updated configuration via `resolve_chat_request()`

**Schema Relationship Definition Flow:**

1. User drags/connects tables in SchemaSettings component
2. POST to `/api/v1/schema/relationships`
3. Backend persists to `table_relationships` table
4. ExecutionService includes relationship graph in system prompt for SQL generation

## State Management

**Client-Side (Frontend):**
- Zustand store `useChatStore` holds: current messages, conversation ID, loading state, abort controller
- Local storage caches: selected connection ID, selected model ID
- TanStack Query caches: connections list, models list, conversation history
- React component state: dropdown toggles, form inputs, selected settings

**Server-Side (Backend):**
- SQLAlchemy ORM persists: conversations, messages, models, connections, semantic terms, table relationships
- In-memory `ActiveQueryRegistry` tracks running queries for stop/cancellation
- No session-scoped state beyond single request lifecycle
- Optional Redis (not enabled by default) for caching

## Key Abstractions

**ExecutionService:**
- Purpose: Orchestrates multi-step LLM execution with streaming
- Examples: `apps/api/app/services/execution.py`
- Pattern: Async generator yielding SSE events, manages context resolution and error handling

**ExecutionContextResolver:**
- Purpose: Resolves configuration (model ID, connection ID, context rounds) at request time
- Examples: `apps/api/app/services/execution_context.py`
- Pattern: Dependency injection of database session, lazy-loads model/connection records

**gptme_engine (ChatEventAccumulator):**
- Purpose: Internal workflow engine wrapping gptme library calls for SQL generation, Python analysis, visualization
- Examples: `apps/api/app/services/gptme_engine.py`, `chat_runtime.py`
- Pattern: Iterative LLM calls with error recovery, streaming events back through API

**ChatMessage (Frontend):**
- Purpose: Union type representing all possible message states
- Examples: `apps/web/src/lib/types/chat.ts`
- Pattern: Discriminated union on `role` + optional fields for SQL, Python, charts, errors

**Conversation (Backend ORM):**
- Purpose: Groups related messages into a conversation session
- Examples: `apps/api/app/db/tables.py`
- Pattern: One-to-many relationship with Message table, tracks selected model/connection/context

## Entry Points

**Frontend Entry:**
- Location: `apps/web/src/app/page.tsx`
- Triggers: Browser load of http://localhost:3000
- Responsibilities: Renders main layout with Sidebar and ChatArea, manages sidebar toggle state

**Backend Entry:**
- Location: `apps/api/app/main.py`
- Triggers: uvicorn server startup
- Responsibilities: FastAPI app initialization, middleware setup, database migration, demo DB initialization

**Chat Streaming Endpoint:**
- Location: `apps/api/app/api/v1/chat.py:chat_stream()`
- Triggers: Frontend GET /api/v1/chat/stream with query parameter
- Responsibilities: Creates conversation, streams execution events via SSE

**Desktop Entry:**
- Location: `apps/desktop/electron/main.ts`
- Triggers: `npm start` or packaged executable
- Responsibilities: Launches ProcessManager to start backend/frontend, embeds web app in Electron

## Error Handling

**Strategy:** Multi-layer error recovery with client retry capability

**Patterns:**

1. **SQL/Python Auto-Repair (Backend):**
   - If SQL execution fails, gptme_engine retries with error message as feedback
   - If Python analysis fails, auto-repair enabled in AppSettings triggers retry
   - Accumulated errors flow to frontend as `error` SSE event with code and message

2. **Client Error Recovery:**
   - Frontend stores original query and execution context in message payload
   - User can click retry to re-run with same or different parameters
   - Frontend catches AbortError (user stop) vs. actual failures
   - Network errors display user-friendly message in AssistantMessageCard

3. **Validation Errors:**
   - FastAPI endpoint validation (Query parameters, body schema) returns 422
   - Backend service layer raises ValueError caught by global exception handler
   - Returns JSON response with error code and localized message

4. **Database Errors:**
   - AsyncSession rollback on exception
   - Constraint violations handled by SQLAlchemy, logged to structlog
   - Not exposed to frontend; mapped to generic INTERNAL_ERROR

## Cross-Cutting Concerns

**Logging:**
- Backend: structlog with JSON or console formatting based on LOG_FORMAT
- Frontend: console.error in try-catch blocks, minimal logging to avoid noise
- Structured logging in ExecutionService tracks progress through pipeline

**Validation:**
- Frontend: React form validation in Settings components using HTML5 + custom handlers
- Backend: Pydantic models in `apps/api/app/models`, FastAPI auto-validation
- Database URLs, encryption keys validated at app startup

**Authentication:**
- Not implemented (single-workspace, local-first design)
- API secrets (model API keys, database passwords) encrypted at rest via Fernet
- No user login/session tokens

**Localization (i18n):**
- Frontend: next-intl library, translation files in `apps/web/src/i18n`
- Backend: i18n module in `apps/api/app/i18n` provides `t()` function for progress/error messages
- Language parameter passed through chat API for per-request translation

---

*Architecture analysis: 2026-03-29*
