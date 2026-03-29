# Codebase Structure

**Analysis Date:** 2026-03-29

## Directory Layout

```
QueryGPT/
├── apps/                           # Three independent applications
│   ├── web/                        # Next.js frontend (React 19)
│   ├── api/                        # FastAPI backend (Python 3.11+)
│   └── desktop/                    # Electron wrapper for desktop
├── docs/                           # Project documentation and diagrams
├── scripts/                        # Utility scripts (setup, linting, testing)
├── docker/                         # Docker build scripts
├── .github/workflows/              # GitHub Actions CI/CD
├── .planning/                      # GSD planning documents
├── docker-compose.yml              # Development stack definition
├── start.sh                        # Main startup script (host mode)
└── README.md                       # Project overview
```

## Directory Purposes

**apps/web:**
- Purpose: User-facing chat interface, settings panels, schema visualization
- Contains: Next.js pages, React components, Zustand stores, API client
- Key files: `src/app/page.tsx` (chat), `src/app/settings/page.tsx` (configuration)

**apps/api:**
- Purpose: RESTful API server handling chat execution, configuration, persistence
- Contains: FastAPI routes, SQLAlchemy models, LLM execution engine
- Key files: `app/main.py` (server entry), `app/api/v1/chat.py` (streaming endpoint)

**apps/desktop:**
- Purpose: Electron wrapper bundling frontend + backend into desktop app
- Contains: Electron main process, IPC handlers, process manager for starting services
- Key files: `electron/main.ts` (app initialization), `electron/process-manager.ts` (service launcher)

**docs:**
- Purpose: Architecture diagrams, API documentation, setup guides
- Contains: Architecture diagrams, API specs, images
- Subdirs: `api/`, `architecture/`, `images/`

**scripts:**
- Purpose: Development and deployment helper scripts
- Contains: Shell scripts for setup, linting, testing, Docker operations
- Key file: `start.sh` is main entry point (wrapper for host-mode startup)

**docker:**
- Purpose: Docker container build context
- Contains: Dockerfiles for api and web services
- Key files: `docker/Dockerfile.api`, `docker/Dockerfile.web`

**.github/workflows:**
- Purpose: CI/CD pipeline definitions
- Contains: GitHub Actions workflows for linting, testing, Docker builds
- Key files: Build validation, test execution, Docker image publication

**.planning:**
- Purpose: GSD (Guided Software Development) codebase analysis documents
- Contains: ARCHITECTURE.md, STRUCTURE.md, TESTING.md, CONVENTIONS.md, CONCERNS.md

## Key File Locations

**Frontend Entry Points:**
- `apps/web/src/app/page.tsx`: Main chat page (SSR via Next.js App Router)
- `apps/web/src/app/layout.tsx`: Root layout with providers setup
- `apps/web/src/app/settings/page.tsx`: Configuration page

**Frontend Components (by domain):**
- Chat: `apps/web/src/components/chat/` - ChatArea, AssistantMessageCard, Sidebar, DataTable, ChartDisplay
- Settings: `apps/web/src/components/settings/` - ModelSettingsForm, ConnectionSettingsForm, SchemaSettings, SemanticSettings
- Schema: `apps/web/src/components/schema/` - TableNode (schema visualization)

**Frontend State & API:**
- Zustand store: `apps/web/src/lib/stores/chat.ts` (message state, chat actions)
- API client: `apps/web/src/lib/api/client.ts` (axios + SSE event stream reader)
- Type definitions: `apps/web/src/lib/types/` - api.ts, chat.ts, schema.ts, export.ts
- Utilities: `apps/web/src/lib/utils.ts` (helper functions)

**Frontend Configuration:**
- `apps/web/package.json`: Dependencies, build scripts
- `apps/web/tsconfig.json`: TypeScript config with path aliases
- `apps/web/next.config.js`: Next.js config (experimental features, rewrites)
- `apps/web/.env.local`: Runtime env vars (NEXT_PUBLIC_API_URL)

**Backend Entry Points:**
- `apps/api/app/main.py`: FastAPI app initialization, middleware, lifespan
- `apps/api/__main__.py`: Command-line entry point

**Backend Routes (by domain):**
- Chat: `apps/api/app/api/v1/chat.py` - /stream, /stop endpoints
- Configuration: `apps/api/app/api/v1/models.py`, `connections.py` - CRUD endpoints
- History: `apps/api/app/api/v1/history.py` - /conversations endpoints
- Schema: `apps/api/app/api/v1/schema.py` - table metadata, relationships
- Semantic: `apps/api/app/api/v1/semantic.py` - business term definitions

**Backend Services (by layer):**
- Execution: `apps/api/app/services/execution.py` (main orchestrator)
- Workflow: `apps/api/app/services/gptme_engine.py` (LLM calls), `python_runtime.py` (sandbox execution)
- Database: `apps/api/app/services/database.py` (connection management)
- Model runtime: `apps/api/app/services/model_runtime.py` (LiteLLM wrapper)
- Context resolution: `apps/api/app/services/execution_context.py` (config lookup)

**Backend Database:**
- ORM models: `apps/api/app/db/tables.py` (Connection, Model, Conversation, Message, SemanticTerm, TableRelationship, Prompt, AppSettings)
- Session setup: `apps/api/app/db/session.py` (AsyncSession factory)
- Migrations: `apps/api/alembic/` (SQLAlchemy migration scripts)
- Metadata DB: `apps/api/app/db/metadata.py` (separate SQLite for schema introspection)

**Backend Models (Data Transfer Objects):**
- Chat: `apps/api/app/models/chat.py` (SSEEvent, ChatStopRequest)
- Config: `apps/api/app/models/config.py` (ModelConfig, ConnectionConfig)
- History: `apps/api/app/models/history.py` (ConversationDetail, MessageDetail)
- Common: `apps/api/app/models/common.py` (APIResponse, error schemas)

**Backend Configuration:**
- Settings: `apps/api/app/core/config.py` (Pydantic Settings, env var validation)
- Demo database: `apps/api/app/core/demo_db.py` (sample SQLite setup)
- Security: `apps/api/app/core/security.py` (encryption utilities)

**Desktop Entry:**
- `apps/desktop/electron/main.ts`: Electron app lifecycle, window creation, service startup
- `apps/desktop/electron/process-manager.ts`: Launches backend/frontend, manages lifecycle
- `apps/desktop/electron/ipc-handlers.ts`: IPC communication with renderer
- `apps/desktop/electron/preload.ts`: Electron security bridge

**Desktop Configuration:**
- `apps/desktop/package.json`: Electron + build dependencies
- `apps/desktop/electron-builder.yml`: App packaging/signing config
- `apps/desktop/tsconfig.electron.json`: TypeScript for Electron context

**Test Locations:**
- Frontend: `apps/web/tests/` (unit), `apps/web/e2e/` (playwright)
- Backend: `apps/api/tests/` (pytest + fixtures)
- CI: `.github/workflows/` includes test execution

**Environment & Deployment:**
- Docker: `docker-compose.yml` (dev stack), `docker-compose.ci.yml` (CI additions)
- Deployment: `render.yaml` (Render deployment blueprint)
- GitHub: `.github/workflows/` (CI automation)

## Naming Conventions

**Files:**
- Components: PascalCase (e.g., `ChatArea.tsx`, `ModelSettingsForm.tsx`)
- Pages: lowercase (e.g., `page.tsx` per Next.js routing)
- Utilities: camelCase (e.g., `utils.ts`, `client.ts`)
- Stores: camelCase with `Store` suffix (e.g., `chat.ts` as `useChatStore`)
- Services (backend): snake_case (e.g., `execution.py`, `model_runtime.py`)
- Models/Tables: PascalCase (e.g., `Conversation`, `Connection`)

**Directories:**
- Components: PascalCase by feature domain (e.g., `chat/`, `settings/`, `schema/`)
- Services: lowercase (e.g., `services/`, `api/`)
- Types: lowercase (e.g., `lib/types/`, `lib/stores/`)
- Routes (backend): lowercase (e.g., `app/api/v1/`)

**Functions:**
- React hooks: camelCase with `use` prefix (e.g., `useChatStore`, `useModelSettingsResource`)
- API routes: kebab-case path segments (e.g., `/chat/stream`, `/config/models`)
- Python functions: snake_case (e.g., `get_or_create_conversation`, `build_system_prompt`)

**Variables & Constants:**
- Frontend: camelCase for variables, UPPER_CASE for constants (e.g., `STORAGE_KEY_CONNECTION`)
- Backend: snake_case for all (e.g., `default_model_id`, `RATE_LIMIT_REQUESTS`)

**Type Names:**
- TypeScript: PascalCase interfaces/types (e.g., `ChatMessage`, `Conversation`)
- Python: PascalCase for Pydantic models (e.g., `ChatRequest`, `APIResponse`)

## Where to Add New Code

**New Chat Feature (e.g., streaming enhancement):**
- Primary code: `apps/web/src/components/chat/` (component), `apps/api/app/services/` (backend logic)
- State: `apps/web/src/lib/stores/chat.ts` if affects global chat state
- Types: `apps/web/src/lib/types/api.ts`, `apps/api/app/models/chat.py`
- Tests: `apps/web/tests/` (unit), `apps/api/tests/` (integration)

**New Settings Panel (e.g., advanced options):**
- Component: `apps/web/src/components/settings/AdvancedSettings.tsx`
- API endpoint: `apps/api/app/api/v1/settings.py`
- Database: Add to `AppSettings` table in `apps/api/app/db/tables.py` if persistent
- Types: `apps/api/app/models/config.py`

**New Database Feature (e.g., caching):**
- ORM model: `apps/api/app/db/tables.py`
- Migration: `apps/api/alembic/versions/` (auto-generated by Alembic)
- API endpoint: `apps/api/app/api/v1/` (new file or extend existing)
- Service: `apps/api/app/services/` if complex logic

**New Execution Stage (e.g., custom analysis):**
- Engine logic: `apps/api/app/services/gptme_engine.py` (add stage to workflow)
- Streaming event: Update `SSEEvent` model in `apps/api/app/models/chat.py`
- Frontend handler: `apps/web/src/lib/stores/chat-helpers.ts` (update event accumulator)
- Display: `apps/web/src/components/chat/AssistantMessageCard.tsx` (render new stage)

**Shared Utilities:**
- Frontend: `apps/web/src/lib/utils.ts` (small helpers), or new file in `lib/`
- Backend: `apps/api/app/core/` (general utilities), or new service file

**Internationalization:**
- Frontend: `apps/web/src/i18n/` (translation JSON files)
- Backend: `apps/api/app/i18n/` (Python translation module)

## Special Directories

**node_modules/ (Frontend):**
- Purpose: npm dependencies (Next.js, React, Zustand, TanStack Query, etc.)
- Generated: Yes (via `npm install`)
- Committed: No (.gitignored)

**apps/api/.venv/ (Backend virtual environment):**
- Purpose: Python package cache (FastAPI, SQLAlchemy, LiteLLM, pytest, etc.)
- Generated: Yes (via `python -m venv` or `pip install`)
- Committed: No (.gitignored)

**apps/api/alembic/ (Database migrations):**
- Purpose: SQLAlchemy schema version control
- Generated: Partially (migration files auto-created by `alembic revision --autogenerate`)
- Committed: Yes (tracked in git for reproducibility)

**apps/api/data/ (Runtime data):**
- Purpose: SQLite demo database, workspace database files
- Generated: Yes (at startup or build time)
- Committed: No (demo.db pre-generated in build, runtime DB excluded)

**.next/ (Frontend build cache):**
- Purpose: Next.js compiled output and cache
- Generated: Yes (via `npm run build` or `npm run dev`)
- Committed: No (.gitignored)

**.serena/ (Serena memory/state):**
- Purpose: Serena AI agent context persistence (if enabled)
- Generated: Yes (by Serena automation)
- Committed: Unlikely (project-specific)

**.planning/ (GSD documentation):**
- Purpose: Codebase analysis artifacts for Guided Software Development
- Generated: Yes (by GSD mappers and planners)
- Committed: Yes (tracked for project continuity)

---

*Structure analysis: 2026-03-29*
