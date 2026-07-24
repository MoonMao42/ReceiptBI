# ReceiptBI Development

This guide covers the maintained `apps/` and `crates/` workspace. It is intentionally separate from the product-facing README.

## Repository Layout

```text
apps/web       Next.js 15 / React workspace
apps/api       FastAPI service and PydanticAI analysis runtime
apps/desktop   Electron host and desktop packaging scripts
crates         Rust SQLite executor core and packaged sidecar
docs           Current product, privacy, status, and development facts
```

Maintained package names, environment variables, headers, and runtime paths use the ReceiptBI identity. A small, isolated compatibility layer migrates browser-storage keys and the separate TypeScript model configuration exactly once. Legacy process-token and environment-file aliases are no longer accepted. Fresh desktop installs use `~/.receiptbi-desktop`. Runtime startup never renames a legacy data root or `querygpt.db`; a layout that still needs either physical move fails closed and requires an explicit, backed-up cold migration. Independently existing old and new roots are never merged or overwritten. The model importer creates its authoritative copy through SQLite's online backup API, validates the standalone snapshot, and records a committed acknowledgement, but deliberately preserves the old SQLite source: automatic deletion cannot safely exclude a concurrently running historical app, so physical retirement is a separate cold-maintenance step.

Inspect a historical desktop layout without changing it from `apps/desktop`:

```bash
npm run migrate:legacy-data
```

After QueryGPT is closed and the printed paths have been checked, run the explicit migration with `--execute --acknowledge-legacy-app-closed`. The command copies into a staging location, verifies the SQLite database and sidecars byte for byte, publishes the ReceiptBI root atomically, and keeps both the historical source and a separate backup. It never merges two independently populated roots.

## Prerequisites

- Python 3.11 or newer
- Node.js LTS
- npm or pnpm
- `uv` is optional but makes Python environment setup faster
- Docker is optional and only needed for the container workflow or a local PostgreSQL service

The host startup script supports macOS and Linux directly and detects WSL. Native Windows source development is not the primary documented path; use WSL or Docker unless the Windows workflow is separately verified.

## Start the Source Workspace

From the repository root:

```bash
./start.sh
```

On first start the script:

1. selects Python 3.11 or newer;
2. creates `apps/api/.venv`;
3. installs the API and web dependencies when their fingerprints change;
4. creates local environment files when missing;
5. starts FastAPI on port `8000` and Next.js on port `3000`;
6. opens the local web workspace unless `RECEIPTBI_NO_BROWSER=1` is set.

Useful commands:

```bash
./start.sh setup              # install core dependencies
./start.sh backend            # start only FastAPI
./start.sh frontend           # start only Next.js
./start.sh status             # show owned processes and ports
./start.sh logs               # view host-mode logs
./start.sh doctor             # inspect environment and capabilities
./start.sh restart            # restart the workspace
./start.sh stop               # stop owned services
./start.sh cleanup            # remove stale PID state and owned port processes
./start.sh install analytics  # install optional analytics extras
./start.sh install dev        # install API development dependencies
```

The maintained startup variables are `RECEIPTBI_BACKEND_HOST`, `RECEIPTBI_BACKEND_RELOAD`, and `RECEIPTBI_NO_BROWSER`.

## Configuration

The startup script creates these files when needed:

```text
apps/api/.env
apps/web/.env.local
```

The web workspace normally uses:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

The API application database can be SQLite or PostgreSQL. `./start.sh` falls back to a local SQLite application database when the configured PostgreSQL service is unavailable. This application database is separate from customer databases attached as read-only project sources.

Model services and customer database connections should normally be configured through the ReceiptBI Settings UI. Never commit API keys, database passwords, generated encryption keys, `.env` files, or desktop data.

## Analysis Execution Paths

The maintained agent should prefer `query_source_data`. It accepts a source identity plus dimensions, metrics, filters, sorting, and a limit. The API binds those names to the current source schema, compiles read-only SQL, records the query plan and result hashes, and persists a replay-safe checkpoint boundary.

Two lower-level paths remain intentionally available:

- raw database or prepared-file SQL when the structured contract cannot express the investigation;
- the project-isolated Python workspace for transformations, statistics, and artifacts that are not well represented as a structured query.

These are controlled fallbacks, not separate product modes. They retain the same project-isolation, source-protection, cancellation, evidence, and completion boundaries.

## Focused Checks

Run checks in proportion to the change. The compact repository entry points are:

```bash
./start.sh test backend
./start.sh test frontend
./start.sh test all
```

The frontend target runs TypeScript checks and Vitest. The backend target uses `apps/api/run-tests.sh`.

For narrower work:

```bash
cd apps/web
npm run type-check
npm test -- <test-file>
npm run lint

cd ../api
.venv/bin/ruff check app tests
.venv/bin/pytest -q <test-file>
```

Do not treat a compile, one golden scenario, or a generated chart as proof that an analysis workflow is correct. High-risk changes should also exercise the real project/source/analysis surface and verify the evidence attached to the result.

## Docker Development

The Docker stack starts the web app, API, and PostgreSQL 16:

```bash
docker compose up --build
docker compose down
```

Default development endpoints:

```text
Web          http://localhost:3000
API          http://localhost:8000
PostgreSQL   localhost:5432
```

Docker is a development option, not the desktop product architecture. A hosted Vercel/Render deployment is not the primary ReceiptBI distribution path.

## Desktop Development

The maintained desktop host is Electron. It starts the local web application and the local FastAPI service. Packaged builds include a PyInstaller backend, Next.js resources, and the Rust `receiptbi-sqlite-executor-sidecar` built from `crates/sqlite-executor-sidecar`.

Desktop source mode and packaged mode intentionally resolve different resources:

- **Source mode** starts the current `apps/web` checkout with its local `next dev` binary on port `13000`. It does not use an old `apps/desktop/next` standalone bundle left by a packaging run.
- **Source mode** starts FastAPI on port `18080` with the repository `.venv` or `apps/api/.venv`. It does not fall back to an arbitrary system Python; a missing repository environment is a startup error.
- **Packaged mode** starts only the bundled PyInstaller executable and bundled Next.js `server.js`. A missing backend executable, frontend server, or required Rust SQLite sidecar fails closed instead of silently using source files or host runtimes.

From `apps/desktop`:

```bash
npm install
npx tsx scripts/build-all.ts
npm run build:electron:mac   # development macOS artifacts
npm run build:electron:win   # development Windows artifacts
```

During backend packaging, `scripts/build-pyinstaller.ts` runs Cargo for the sidecar, copies the executable beside the frozen API, and marks it executable on non-Windows targets. The Electron process manager sets `RECEIPTBI_SQLITE_EXECUTOR_PATH` and rejects a packaged startup when the sidecar is missing. The API then routes file-backed SQLite queries through the versioned sidecar process contract.

The normal `./start.sh` source workspace and Electron source mode do not build or require this Rust executable. Without an explicit `RECEIPTBI_SQLITE_EXECUTOR_PATH`, the API uses its guarded Python SQLite adapter. Test the path you changed; a source-mode SQLite pass is not evidence that the packaged sidecar path works, and the presence of an old packaged frontend is not evidence that current source UI is running.

These commands create development packages. They do not prove signing, notarization, Authenticode, clean-machine compatibility, update behavior, or release readiness. See [Status](STATUS.md) before making distribution claims.

## Documentation Rules

- `README.md` and `README.en.md` must keep the same section order and capability claims.
- [STATUS.md](STATUS.md) is authoritative for implemented versus open work.
- [PRODUCT_CONTRACT.md](PRODUCT_CONTRACT.md) defines durable system responsibilities, not a fixed demo scenario.
- [DATA_AND_PRIVACY.md](DATA_AND_PRIVACY.md) must follow the real model and storage data flow.
- User-visible docs and maintained configuration use the ReceiptBI brand. Historical identifiers may appear only inside bounded migration code, migration tests, or the real upstream repository URL.
- The SQLite executor code under `crates/`, its process contract, tests, and maintained desktop integration are current implementation evidence. Historical planning artifacts are not capability evidence.
