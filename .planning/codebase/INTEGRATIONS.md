# External Integrations

**Analysis Date:** 2026-03-29

## APIs & External Services

**LLM Providers:**
- OpenAI (GPT-4o default) - SQL generation and analysis
  - SDK/Client: litellm 1.40+
  - Auth: `OPENAI_API_KEY` env var
  - Base URL: `OPENAI_BASE_URL` (defaults to https://api.openai.com/v1)
  - Config: `/apps/api/app/core/config.py`

- Anthropic - Alternative LLM provider
  - SDK/Client: litellm 1.40+
  - Auth: `ANTHROPIC_API_KEY` env var

- DeepSeek - Alternative LLM provider
  - SDK/Client: litellm 1.40+
  - Supports OpenAI-compatible API format

- Ollama - Local LLM support
  - SDK/Client: litellm 1.40+
  - Base URL: User-configured
  - API Format: ollama_local

- Custom Providers - Generic OpenAI-compatible endpoints
  - SDK/Client: litellm 1.40+
  - Config: User provides base_url and api_key

**LLM Model Configuration:**
- Default model: `gpt-4o` (via `DEFAULT_MODEL` and `GPTME_MODEL` env vars)
- Model selection: User can select per conversation via `/api/v1/stream` query param
- Timeout: `GPTME_TIMEOUT` (default 300 seconds)
- Provider resolution: `app/services/model_runtime.py` normalizes provider names and API formats
- Model execution: `app/services/gptme_engine.py` wraps litellm calls with retry and repair logic

## Data Storage

**Databases:**
- PostgreSQL 16 (Production)
  - Connection: `DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/querygpt`
  - Client: SQLAlchemy 2.0.30+ with asyncpg driver
  - Tables: `/apps/api/app/db/tables.py`
    - connections (database connection configs)
    - models (LLM model configs)
    - conversations (chat sessions)
    - messages (chat message history)
    - app_settings (workspace settings)
    - semantic_terms (business term definitions)
    - table_relationships (schema relationship definitions)
    - prompts (system prompt templates)

- SQLite (Development/Testing)
  - Connection: `sqlite:///:memory:` or `sqlite+aiosqlite:///path/to/db.sqlite`
  - Client: SQLAlchemy with aiosqlite driver
  - Demo database: Pre-packaged at build time, metadata persisted in separate SQLite instance

- MySQL (Supported Target)
  - Connection: `mysql+aiomysql://user:password@host:port/database`
  - Driver: pymysql or aiomysql

**File Storage:**
- Local filesystem only
- Schema metadata: SQLite database at `app/db/metadata.py`
- Font files: `app/assets/` for matplotlib rendering

**Caching:**
- None configured (Redis optional via `REDIS_URL` env var, not currently used)

## Authentication & Identity

**Auth Provider:**
- Custom/None - Single workspace mode
  - No user authentication implemented
  - JWT-based infrastructure in place but unused
  - JWT config: `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`, `JWT_REFRESH_TOKEN_EXPIRE_DAYS` in `/apps/api/app/core/config.py`

## Encryption

**Sensitive Data Encryption:**
- Fernet-based encryption (cryptography 44.0+)
- Encrypted fields: Database connection passwords, API keys stored in `password_encrypted` and `api_key_encrypted` columns
- Encryption key: `ENCRYPTION_KEY` env var (Fernet key format)
- Decryption: `app/services/` handles encryption/decryption on model load/save

## Monitoring & Observability

**Error Tracking:**
- None configured (application errors logged, not sent to external service)

**Logs:**
- Structured logging via structlog 24.1+ (`/apps/api/app/main.py`)
- Format: Console (readable) or JSON (machine-parseable)
- Format selection: `LOG_FORMAT` env var (console|json)
- Level: `LOG_LEVEL` env var (default INFO)
- File output: None (logs to stdout)

**Rate Limiting:**
- slowapi 0.1.9+ middleware
- Default: `RATE_LIMIT_REQUESTS=60` per `RATE_LIMIT_WINDOW=60` seconds
- Configurable via env vars

## CI/CD & Deployment

**Hosting:**
- Docker Compose (local development)
  - Services: PostgreSQL, FastAPI backend, Next.js frontend
  - Config: `/docker-compose.yml`
- Docker containers (production-ready)
  - Backend: `docker/Dockerfile.api` (Python 3.11 slim)
  - Frontend: `docker/Dockerfile.web` (Node.js 20)
- Render.yaml (Render platform support)
  - Config: `/render.yaml`

**CI Pipeline:**
- GitHub Actions (workflows in `.github/workflows/`)
- Docker Compose CI config: `docker-compose.ci.yml`

## Environment Configuration

**Required env vars:**

**Backend (API):**
- `DATABASE_URL` - PostgreSQL connection string (required)
- `OPENAI_API_KEY` - OpenAI API key (required for default setup)
- `ENCRYPTION_KEY` - Fernet encryption key (required for production)
- `JWT_SECRET_KEY` - JWT signing key (required for production)
- `HOST` - Server bind address (default: 0.0.0.0)
- `PORT` - Server port (default: 8000)
- `ENVIRONMENT` - development|staging|production (default: development)
- `DEBUG` - Enable debug mode (default: false)
- `LOG_LEVEL` - Log verbosity (default: INFO)
- `LOG_FORMAT` - console|json (default: console)
- `CORS_ORIGINS_STR` - Comma-separated allowed origins (default: http://localhost:3000,http://127.0.0.1:3000)
- `RATE_LIMIT_REQUESTS` - Requests per window (default: 60)
- `RATE_LIMIT_WINDOW` - Rate limit window in seconds (default: 60)

**Frontend:**
- `NEXT_PUBLIC_API_URL` - Public API endpoint (client-side, default: http://localhost:8000)
- `INTERNAL_API_URL` - Internal API endpoint (server-side, default: matches NEXT_PUBLIC_API_URL)

**Secrets location:**
- `.env` file in project root or container working directory
- `.env.example` provided at `/apps/api/.env.example` as template
- Environment variables (recommended for containerized deployments)

## Webhooks & Callbacks

**Incoming:**
- None - Application is request-response based, no webhook ingestion

**Outgoing:**
- None - No external webhook callbacks

**Internal SSE Streaming:**
- Chat query execution streams events via Server-Sent Events (SSE)
- Endpoint: `GET /api/v1/stream` (connection-based, model-based, language-based)
- Event types: progress, sql_execution, python_execution, chart_generation, done, error
- Stop signal: `POST /api/v1/stop` to cancel in-flight queries

## API Endpoints Summary

**Chat Operations:**
- `GET /api/v1/stream` - Streaming query execution (SSE)
- `POST /api/v1/stop` - Stop active query

**Configuration (Models & Connections):**
- `GET/POST /api/v1/models` - List and create LLM model configs
- `PUT/DELETE /api/v1/models/{id}` - Update or delete model config
- `POST /api/v1/models/test` - Health check LLM provider
- `GET/POST /api/v1/connections` - List and create database connections
- `PUT/DELETE /api/v1/connections/{id}` - Update or delete connection
- `POST /api/v1/connections/test` - Test database connection

**Schema & Metadata:**
- `GET /api/v1/schema/{connection_id}` - Fetch database schema
- `GET/POST /api/v1/semantic` - Manage semantic term definitions
- `GET/POST /api/v1/table-relationships` - Define table JOIN relationships

**Chat History:**
- `GET /api/v1/history` - List conversations
- `GET /api/v1/history/{conversation_id}` - Get conversation messages

**System:**
- `GET /health` - Health check endpoint
- `GET /` - Root info endpoint

---

*Integration audit: 2026-03-29*
