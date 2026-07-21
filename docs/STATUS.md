# ReceiptBI Status

> Last reviewed against the maintained `apps/` and `crates/` implementation on 2026-07-19.

This document is the compact source of truth for what the current ReceiptBI application does, including the Rust SQLite sidecar used by the desktop chain.

## Current Runtime

The maintained application is:

```text
Electron desktop host
  ├─ local Next.js/React workspace
  └─ local FastAPI service
       └─ PydanticAI analysis loop
            ├─ project context and semantic knowledge
            ├─ required AnalysisPlaybook v3 safe lane
            │    └─ current-source binding, typed execution, validation, SQL-free receipt
            ├─ schema-bound query_source_data contract
            │    ├─ prepared-file execution
            │    └─ read-only database adapters
            │         └─ packaged SQLite: Rust sidecar process
            ├─ raw SQL and isolated Python fallbacks
            ├─ relationship and result validation
            └─ persisted report artifacts and checkpoints
```

Wren Core is used behind an internal adapter for database semantic validation where it fits. It is not the public product contract and does not replace ReceiptBI's own cross-source validation, project knowledge, or execution rules.

The maintained execution route is built by `ExecutionService` and `PydanticAnalystRuntime`. `query_source_data` is the preferred model-facing data contract: the model names source-bound dimensions, metrics, filters, sorting, and limits, while ReceiptBI validates those names and compiles read-only SQL. For a required AnalysisPlaybook v3 that contains exactly one safe single-source typed query plus final validation, ReceiptBI now performs that binding, compilation, execution, and validation before the model sees the result. The model explains the current verified result rather than recreating the data step. Raw database/file SQL and project-isolated Python remain controlled escape hatches rather than the default contract.

`crates/sqlite-executor-sidecar` is built by the maintained desktop packaging script, copied beside the frozen API, required at packaged startup, and selected by the API SQLite adapter through `RECEIPTBI_SQLITE_EXECUTOR_PATH`. Source development still uses the Python SQLite path unless that sidecar is explicitly configured.

## Implemented Product Surface

| Area | Current behavior |
|---|---|
| Projects | Separate sources, history, knowledge, recipes, runs, and artifacts by project; project names can be edited |
| Files | Upload CSV, XLS, XLSX, Parquet, and JSON into a project-local source copy |
| Databases | Attach SQLite, MySQL, and PostgreSQL connections to the current project; packaged SQLite queries use the bundled Rust sidecar when configured by the desktop host |
| File preflight | Detect and prepare headers, types, dates, missing values, exact duplicates, total rows, outliers, sheet ambiguity, grain candidates, and schema drift for uploaded files |
| Database context | Verify a connection; read table kind, column type/nullability, real primary keys, foreign keys, and unique constraints when the connector exposes them; then build a bounded read-only value profile (at most 257 fetched rows per table) with missingness, sample uniqueness, roles, ranges, low-cardinality values, grain candidates, explicit sampling/budget markers, and sensitive/high-cardinality value suppression. Unavailable constraint metadata is marked unavailable rather than reported as an empty catalog |
| Working data | Preserve the original file and materialize an analysis-ready working copy |
| Sanitation history | Execute only the versioned, bounded declarative cleaning operations supported by the product; keep one immutable revision chain and active head per method; reject stale restores; require an explicit reapply before a restored method affects current analysis; preserve complete cleaning history in ProjectBundle v3 export/import; let an imported method be trialled in isolation and explicitly bound to one source; and provide a visual preview-then-apply editor for trimming text, filling missing values with zero, normalizing dates/currency, and removing exact duplicates. Existing manual steps can be replaced or cleared without modifying the original file |
| Project understanding | Store candidate, confirmed, and locked business meaning separately from execution state (`definition_only`, `needs_validation`, `verified`, `blocked`); provide a paged large-workspace editor where the user can add and fully edit names, types, definitions, governance state, and structured relationship endpoints; each entry keeps an immutable revision chain and one active head, including across key renames; restores create a new revision instead of rewriting history, stale concurrent edits are rejected, stale/inactive entries are excluded from reuse, and registered business decisions use system-owned stable slots so known model aliases do not create a second question. A narrow deterministic learner can now propose a schema-bound `sum`/`avg` metric only from a complete, retained, single-row final result with exact validation and unique current-source binding; it records the business meaning as a candidate while preserving the independently verified execution evidence |
| Relationships | Infer candidates, use declared database foreign keys as catalog-backed evidence, validate match and expansion behavior, and expose only active, confirmed/locked, execution-verified relationships to ordinary runs; neither an FK declaration nor a model guess auto-confirms a join. Evidence is bound to the exact source and table scope that produced it: filtered, aggregated, derived, truncated, or table-unknown results remain current-run evidence, while only a complete system-checked two-table relation can become reusable |
| Analysis | Run a multi-step PydanticAI tool loop that prefers the structured `query_source_data` contract. Analysis-ready files are queried locally through bounded DuckDB views, while databases use their read-only adapter; raw SQL and isolated Python remain available when the contract cannot express the task. Required AnalysisPlaybook v3 methods use a system-owned pre-model runner only for the narrowly classified single-source typed-query lane, while complex, unknown, and v2 methods remain agent-replanned |
| Results | Persist reports, metrics, tables, deterministic ChartSpec v1 documents or images, and hidden technical evidence against an analysis run. Chart rows and result identity are bound by ReceiptBI to a current validated result; arbitrary colors, renderer options, code, and model-authored rows are rejected. Only an explicit result can complete a run, while silent or exceptional termination remains visibly failed. If only the model's structured report shape fails after the exact complete final table has already been retained and validated, ReceiptBI can preserve a clearly labelled table-only report without inventing metrics, explanations, or charts |
| Editable reports | Store versioned `ReportDocument → ReportPage → ReportBlock` trees separately from immutable investigations; assemble manual content or referenced run artifacts in a reading/editing workspace with page outline, 12-column layout, properties, manual-override labels, six business block types, deterministic multi-series chart presentations, chart family/axes/series/stack/label/format/palette controls, paged tables, current-page static filters, PDF and Excel export, and an explicit “add from investigation” flow. Concurrent stale saves return a conflict instead of overwriting newer work. A durable provenance snapshot keeps the source description and stored content readable when a referenced run or artifact is later removed |
| Recovery | Request cancellation, including active SQLite, MySQL, and PostgreSQL queries; persist integrity-checked checkpoints after observable replay-safe tool progress; and resume only when source identity still matches. Free Python state is not replayable |
| Corrections | Keep a report correction run-scoped by default; let the user choose a business-facing, server-issued target without exposing its semantic key; bind that opaque target to the source run, system evidence, and current semantic revision; keep “overall conclusion / other” unbound; promote only an explicitly selected canonical target; safely compile validated full-result refund filters, identities, numeric metric-column choices, bounded arithmetic metric formulas, and explicit two-endpoint relationship corrections; a latest-data rerun carries the report's project-scoped correction identity so the new result can emit a fresh system-owned receipt only when the current definition reaches and is revalidated in the final result |
| Suggestions | Generate project-specific starting questions with model output validation and a deterministic preflight fallback |
| Workbench | Keep the task composer, project-specific suggestions, data understanding, semantic revision review, cleaning-method history, visual cleaning editor, imported-method before/after preview and explicit application, truthful investigation timeline, typed report correction, explicit replacement-version choice, and horizontally browsable investigation history in one ordinary-user surface; completed investigations can open the separate editable report workspace with their exact analysis-run identity |
| Settings | Configure OpenAI-compatible, Anthropic, DeepSeek, Ollama, or custom services; manage databases and advanced diagnostics |
| About | Show ReceiptBI product boundaries and read the real Electron application version in desktop mode, with the API version as the source-workspace fallback |

## Current Safety Boundaries

- File originals are not modified by preflight or analysis.
- Operational database access is read-only by default; write statements are blocked.
- The primary data contract binds requested fields and operations to the current source schema before compiling SQL; raw SQL remains inside the same read-only and evidence boundaries.
- A saved method is not automatically replayable code. Only an AnalysisPlaybook v3 classified as `system_structured_query`—one current logical source, one typed query, one final validation, no hidden semantic or relationship side effects—uses the system runner. Each required run rebinds the current source by logical role and schema signature, recompiles and executes the declarative plan, rejects drift or truncation, and emits a SQL-free receipt bound to the playbook, current source, result, profile, and validation. Complex or unknown v3 methods and all v2 methods use `agent_replan_required`; their old rows, SQL, or Python are never treated as an automatic replay result.
- In packaged desktop mode, SQLite execution crosses a versioned local Rust process contract with relation, row, byte, timeout, cancellation, and source-identity checks. The source-development Python SQLite adapter remains a fallback, not proof of packaged-sidecar behavior.
- Project context is loaded from the current project, rather than silently merging knowledge from other projects.
- Candidate knowledge cannot overwrite confirmed or locked definitions.
- A model proposal cannot rewrite or confirm a system-derived aggregate-metric candidate in place. Promotion uses the governed semantic update path; changing its meaning or definition invalidates the old execution proof.
- Deterministic metric learning never stores the observed metric value and runs in an isolated savepoint. An ambiguous source binding, partial result, unsupported query shape, or candidate-write conflict produces no learning side effect and cannot turn an otherwise verified report into a failure.
- Stable decision slots use a small explicit alias registry and conservative business-signal matching, not fuzzy text similarity. A legacy alias may be read as its canonical slot, while conflicting durable answers fail closed and remain visible as a semantic diagnostic.
- A completed report exposes only business-language correction targets backed by system-owned run evidence. Target references are run-bound and revision-bound; a stale report cannot overwrite a newer semantic head, an inactive definition is not resurrected, and an unbound overall correction stays local to that run.
- A database value profile is sampled and budgeted; it supplies navigation facts, not exact whole-table counts. Raw samples, sensitive values, identifiers, and high-cardinality values are not copied into model-facing project context.
- Database constraints are catalog evidence, not proof that current values still satisfy a relationship. Declared foreign keys stay unverified until the value and join checks required by the execution path succeed.
- Knowledge edits and restores append immutable revisions. A changed or restored definition loses any execution proof that belonged to its previous value, and a stale writer must refresh instead of overwriting a newer head.
- Cleaning-method acceptance, undo, and restore append immutable revisions too. Restoring only changes the active method head; it does not rewrite the original file or silently replace the working data currently used by a report.
- Applying an imported cleaning method is a two-step action. Preview runs in a disposable directory and does not alter the source, recipe, or official preflight report; apply reruns it and rejects the change if the original file, current working copy, current recipe head, template head, or output proof differs from the preview.
- An unverified relationship is not executable merely because a model proposed it. A match observed in a filtered, aggregated, derived, truncated, or table-unknown result cannot be promoted as proof of the full relationship; nullable keys report both non-null match quality and full-record coverage.
- Remembering a business definition does not make it executable. Verified execution requires current definition, source binding, application, lineage to the final result, and result validation evidence.
- Metric formulas are declarative expression trees over bound columns, never model-authored Python or `eval`. Supported arithmetic runs with explicit null/divide-by-zero policy and Decimal result evidence; later steps cannot keep the verified marker after replacing the metric output with an unrelated result.
- A completed report must be backed by current run evidence; a model-only narrative is not equivalent to completion.
- Checkpoint recovery verifies source fingerprints and stored artifact integrity before replay.

These are system responsibilities. Different models may choose different investigation directions or fail to produce a valid structured response, but no model is expected to remember or enforce these boundaries itself.

## Distribution Status

The source workspace is usable as a developer preview through `./start.sh`. Electron source mode starts the current `apps/web` checkout with `next dev` and requires a repository Python environment instead of silently using a stale standalone frontend or arbitrary system Python. The desktop source uses the ReceiptBI identity (`com.receiptbi.desktop`, `receiptbi-desktop@1.0.0`), ReceiptBI log names, and a `receiptbi-api` packaged executable. Fresh installs use `~/.receiptbi-desktop` and `receiptbi.db`. Runtime startup never renames a legacy data root or `querygpt.db`; layouts that still need a physical move fail closed and require an explicit, verified, backed-up cold migration, while independently existing roots are never merged or overwritten. For the separate historical model database, the API uses SQLite's online backup operation to create a private standalone snapshot, verifies it with `PRAGMA quick_check`, and imports it transactionally with strict UUID/field/credential equivalence on retries. Its launch-bound acknowledgement prevents duplicate imports, while the old active files remain preserved for a separate cold cleanup because automatic deletion cannot exclude a concurrent historical writer. Electron packaging code and local unsigned artifacts exist, with Python, the web application, Alembic migrations, and the Rust SQLite sidecar wired into the desktop resource chain. Recognized historical SQLite metadata databases are upgraded through the real migration chain before any application session opens; partial, mixed, or unknown schemas stop startup instead of being hidden by `create_all`. Packaged startup also fails closed when its backend executable, Next.js server, or expected sidecar is absent.

The repository does **not** currently claim:

- a signed and notarized macOS release;
- an Authenticode-signed Windows installer;
- clean-machine verification for every declared package target;
- a public automatic-update channel;
- a single synchronized version source across web, API, and Electron packages.

The current Electron builder explicitly disables macOS signing and hardened runtime. Treat generated packages as development artifacts until release hardening is completed.

## Important Open Work

1. Prove the implemented correction receipts across a real later-period desktop flow: the compiler and deterministic tests cover metric/filter/relationship reuse and drift, but the complete installed-app interaction still needs visible replacement-period reuse and revalidation.
2. Extend the new safe visual cleaning editor with richer distribution differences and more governed transformations, and route restore/reapply through the same preview-then-confirm contract. Arbitrary user-authored transformations and preview-confirm for every existing-recipe path do not yet exist.
3. Add proactive cross-table value-overlap discovery and execution support for composite relationships. Runtime relation evidence is now scoped to exact source/table inputs and refuses to promote partial-result matches, but declared constraints remain evidence-only and bounded profiling does not discover every relationship or claim exact whole-table duplicate or outlier counts.
4. Define a safe recovery boundary for open-ended Python. Current free Python execution deliberately marks its checkpoint `python_state_not_replayable` rather than pretending process state can be restored.
5. Expand system-owned reuse and semantic learning only where deterministic rebinding and validation can stay honest. The first AnalysisPlaybook v3 lane covers one logical source and one typed query, and the first deterministic semantic learner covers one unfiltered, dimension-free `sum`/`avg` metric with a unique current binding. Joins, raw SQL, Python, multi-step transformations, richer metric formulas, and older v2 methods still require agent replanning or explicit user governance.
6. Unify the version source across web, API, and Electron packages. The About surface already reads the real Electron version dynamically in desktop mode; matching version strings do not yet make the packages share one authoritative version source.
7. Verify the bundled SQLite sidecar and live database cancellation on every declared package target, then complete signed desktop distribution, uninstall/data-retention guidance, clean-machine smoke checks, and release notes.
8. Extend current-page static report filters with explicit page/block scope and cross-filtering, then add drill-to-detail, PNG/PPT-friendly export, source refresh receipts, original-file change detection, and remote scheduled refresh. Current filters act on stored chart/table data; PDF/Excel export is available, but the report does not yet re-query a source or claim a live dashboard runtime.
9. Move initial CSV/XLSX/JSON preparation and visual-cleaning replay onto a bounded or streaming data plane. DuckDB already executes analysis-ready file queries and compares cleaning previews without loading both copies into Python, but the current preflight transformation itself still materializes a pandas frame and is not yet an honest 500 MB-file guarantee.

## Explicit Non-Goals

ReceiptBI is currently a local, single-user analysis workspace. It does not aim to provide team accounts, enterprise permissions, hosted dashboards, database administration, arbitrary write SQL, a public notebook, or a ReceiptBI cloud control plane.

## Updating This File

Move an item into the implemented table only when the user-visible path and its system boundary both exist. Build success, a model response, or one golden scenario is not sufficient evidence by itself.

Related documents:

- [Product Contract](PRODUCT_CONTRACT.md)
- [Data and Privacy](DATA_AND_PRIVACY.md)
- [Development](DEVELOPMENT.md)
