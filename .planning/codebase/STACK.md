# Technology Stack

**Analysis Date:** 2026-03-29

## Languages

**Primary:**
- Python 3.11+ - Backend API (`/apps/api`)
- TypeScript 5.6+ - Frontend web application (`/apps/web`)
- TypeScript 5.7+ - Desktop application (`/apps/desktop`)

**Secondary:**
- JavaScript - Configuration and build scripts
- Shell - Deployment and startup scripts

## Runtime

**Environment:**
- Node.js 20 (docker/Dockerfile.web)
- Python 3.11+ (docker/Dockerfile.api)
- Package Manager: npm (Node.js), uv (Python)

**Lockfile:**
- Frontend: package-lock.json (implied in `npm ci`)
- Backend: uv.lock (workspace-based)

## Frameworks

**Core:**
- FastAPI 0.115.0+ - Web framework for backend API (`/apps/api/app/main.py`)
- Next.js 15.0+ - Frontend web framework (`/apps/web`)
- Electron 33.3+ - Desktop application runtime (`/apps/desktop`)

**Testing:**
- Vitest 4.0+ - Frontend unit and component testing (`/apps/web`)
- Pytest 8.0+ - Backend unit and integration testing (`/apps/api/tests`)
- Pytest-asyncio 0.23+ - Async test support for backend

**Build/Dev:**
- TypeScript 5.6+ - Type checking (web), 5.7+ (desktop)
- ESLint 9.0+ - Frontend linting
- Ruff 0.4+ - Python linting and formatting
- MyPy 1.10+ - Python type checking
- Tailwind CSS 3.4+ - Frontend styling
- PostCSS 8.4+ - CSS processing
- Electron-builder 25.1+ - Desktop app packaging
- UVicorn 0.30+ - ASGI server for FastAPI

## Key Dependencies

**Critical - Backend:**
- sqlalchemy[asyncio] 2.0.30+ - ORM and async database support (`/apps/api/app/db/`)
- asyncpg 0.29+ - PostgreSQL async driver
- pydantic[email] 2.7+ - Data validation and settings management
- pydantic-settings 2.2+ - Environment configuration (`/apps/api/app/core/config.py`)
- uvicorn[standard] 0.30+ - ASGI server
- gptme 0.30+ - LLM execution and code generation engine
- litellm 1.40+ - Universal LLM API abstraction (supports OpenAI, Anthropic, Ollama, DeepSeek, custom)
- sse-starlette 2.1+ - Server-Sent Events for streaming responses
- structlog 24.1+ - Structured logging (`/apps/api/app/main.py`)
- slowapi 0.1.9+ - Rate limiting middleware
- cryptography 44.0+ - Encryption for sensitive data (Fernet key-based)
- alembic 1.13+ - Database migration management
- pandas 2.2+, numpy 1.26+ - Data processing and analysis
- matplotlib 3.8+ - Visualization support (Agg backend for headless environments)

**Analytics (Optional):**
- scikit-learn 1.4+
- scipy 1.12+
- seaborn 0.13+

**Critical - Frontend:**
- react 19.0+ - UI library
- react-dom 19.0+ - DOM rendering
- @tanstack/react-query 5.50+ - Server state management and data fetching
- axios 1.7+ - HTTP client
- zustand 5.0+ - Client state management
- @xyflow/react 12.10+ - Graph visualization for schema relationships
- react-markdown 9.0+ - Markdown rendering
- react-syntax-highlighter 15.6+ - Code syntax highlighting
- recharts 2.13+ - Chart components
- next-intl 3.20+ - Internationalization/i18n
- lucide-react 0.460+ - Icon library
- tailwind-merge 2.5+, clsx 2.1+ - CSS utility combination
- @testing-library/react 16.3+ - React component testing utilities

**Desktop:**
- dotenv 16.4.5 - Environment variable loading
- electron-log 5.2.4 - Electron logging

## Configuration

**Environment:**
- Backend: `.env` file or environment variables, validated via Pydantic Settings (`/apps/api/app/core/config.py`)
- Frontend: `NEXT_PUBLIC_API_URL` (client-side), `INTERNAL_API_URL` (server-side during SSR)
- Desktop: `.env` support via dotenv package

**Build:**
- Backend: `pyproject.toml` with uv workspace (`/pyproject.toml`, `/apps/api/pyproject.toml`)
- Frontend: `next.config.ts` with API rewrites for proxy to backend
- Desktop: `electron-builder.yml` for packaging configuration
- Web: `tailwind.config.ts` for styling, `tsconfig.json` for TypeScript, `vitest.config.ts` for testing, `eslint.config.mjs` for linting

## Database

**Primary (Production):**
- PostgreSQL 16+ with asyncpg driver
- Connection string: `postgresql+asyncpg://user:password@host:port/database`

**Supported Alternatives:**
- MySQL 5.7+ via pymysql driver
- SQLite 3.x via aiosqlite driver for development/testing

**ORM:**
- SQLAlchemy 2.0.30+ with async support
- Alembic for schema migrations
- Tables defined in `/apps/api/app/db/tables.py`

## Platform Requirements

**Development:**
- macOS, Linux, or Windows (with Docker Desktop recommended)
- Node.js 20 or higher
- Python 3.11 or higher
- PostgreSQL 16 (via Docker)
- Docker & Docker Compose (optional but recommended)

**Production:**
- Deployment target: Docker containers (FastAPI on port 8000, Next.js on port 3000)
- Kubernetes-ready with docker-compose.yml as base
- Standalone deployment: Python 3.11+ server with FastAPI + UVicorn, Node.js 20+ server with Next.js

## API & Streaming

**WebSocket/SSE:**
- Server-Sent Events (SSE) for real-time query streaming (`/apps/api/app/api/v1/chat.py`)
- EventSourceResponse via sse_starlette
- Streaming endpoint: `GET /api/v1/stream` with query parameters

**CORS:**
- Configurable via `CORS_ORIGINS_STR` environment variable
- Default: `http://localhost:3000,http://127.0.0.1:3000`

---

*Stack analysis: 2026-03-29*
