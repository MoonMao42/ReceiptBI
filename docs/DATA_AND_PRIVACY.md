# ReceiptBI Data and Privacy

ReceiptBI is local-first, not automatically offline and not a guarantee that data never leaves the device. This document describes the current maintained `apps/` runtime.

## What Stays on the Device

ReceiptBI stores the following locally:

- project records, conversations, analysis runs, settings, and knowledge;
- uploaded source copies and analysis-ready working copies;
- sanitation recipes, schema/profile summaries, checkpoints, and generated artifacts;
- configured database and model-service records;
- project-specific Python environments and dependency manifests when that capability is used;
- local application and desktop process logs.

In packaged desktop mode, a fresh install uses `~/.receiptbi-desktop`. It contains the application database, project workspaces, environment settings, and logs. Normal startup never renames, moves, merges, or deletes a legacy data directory or `querygpt.db`: an uncooperative historical process could otherwise keep writing an open SQLite file after its path moved. A legacy-only layout therefore stops with an explicit cold-migration error requiring the old application to be closed and a verified backup to exist. If both directories already exist, ReceiptBI uses the ReceiptBI directory without changing either one.

The maintained cold-migration command is inspection-only by default. Execution requires a separate flag acknowledging that the historical application is closed. It verifies the database and any SQLite WAL/SHM sidecars, writes a local receipt, and preserves both the source and a dedicated backup; it does not delete historical data automatically.

Source-development paths can be changed through environment variables. See [Development](DEVELOPMENT.md).

## Files and Databases

When a file is added to a project, ReceiptBI copies it into the project workspace. Preflight and analysis operate on a derived working copy. They do not rewrite the original file selected by the user.

Database connections are used for read-only inspection and queries. ReceiptBI validates statements and blocks write operations in the normal execution path. Users should still provide a database account whose server-side permissions are read-only; application checks are not a substitute for database permissions.

In packaged desktop mode, file-backed SQLite queries are sent over local standard input/output to the bundled Rust sidecar. That process receives the selected database path, compiled read-only SQL, allowed relations, and execution limits; it returns rows, truncation information, and source identity to the local API. It is a local process boundary, not a ReceiptBI cloud service. Source-development mode uses the guarded Python SQLite adapter unless a sidecar path is explicitly configured.

Connection passwords and model API keys are stored encrypted in the application database using a local encryption key. Do not publish the application database, environment file, or desktop data directory.

## What a Model Provider May Receive

An investigation uses the model service selected in Settings. Depending on the task, a request may include:

- the user's question and relevant conversation context;
- source names, formats, table and column structure, inferred types, and quality/profile summaries;
- confirmed project definitions, relevant candidates, validated relationships, and reusable analysis context;
- bounded samples or summaries returned by read-only queries and analysis tools;
- execution errors in sanitized form when the model is asked to repair a failed step.

ReceiptBI does not treat “local-first” as permission to hide this transfer. If the configured endpoint is a cloud service or third-party gateway, the provider's own retention and privacy terms apply.

Using an Ollama or other local compatible endpoint can keep model requests on the device. ReceiptBI cannot prove that an arbitrary custom URL is local or that a gateway does not forward requests elsewhere; check the endpoint you configure.

## Other Network Access

The current application can contact:

- the model-service endpoint configured by the user;
- MySQL or PostgreSQL hosts configured as project data sources;
- a Python package index when a missing project dependency is explicitly installed or automatically resolved for an analysis;
- development package registries while setting up or building the source workspace.

There is no ReceiptBI account, cloud sync service, hosted analytics backend, or team control plane in the maintained product. There is also no public automatic-update channel claimed by the current release status.

## Logs and Diagnostics

Desktop logs are written under `~/.receiptbi-desktop/logs` in the normal packaged path, using names such as `receiptbi-2026-07-18.log`. A legacy fallback launch writes into the legacy data root so that the active workspace and its diagnostics stay together. Technical logs may contain process paths, source names, configured endpoint information, execution stages, and error text. They should not intentionally contain API keys or database passwords, but users should inspect logs before sharing them.

When the retired TypeScript model database is present, Electron prepares a private, no-overwrite archive under `migration-backups/legacy-model-config`. The API uses SQLite's online backup operation to publish one standalone database snapshot there, verifies it with `PRAGMA quick_check`, imports from that snapshot, re-encrypts any credential, and publishes a launch-bound acknowledgement only after the transaction commits. SQLite performs the backup so a concurrently active WAL cannot be mistaken for a coherent file-by-file copy. The acknowledgement prevents duplicate imports, while the old database contents and `.env` are not rewritten, renamed, or deleted: without cooperation from the historical process, automatic deletion cannot safely rule out a concurrent SQLite writer. SQLite may update transient read-lock metadata in an existing SHM file while taking the consistent snapshot. Missing acknowledgements, path escapes, symlinks, snapshot failures, and credential conflicts likewise preserve the source data. Physical cleanup is performed only as a separate cold-maintenance operation with its own backup.

Advanced evidence inside a report can contain SQL, Python, cleaning details, field names, and result samples. It is hidden from the ordinary view for usability, not removed from the local project.

## Retention and Deletion

Project data and history remain on the device until the relevant records or files are removed. The current Windows installer configuration preserves application data during uninstall, and removing the macOS application bundle does not by itself delete the desktop data directory.

For a complete local erase in the current developer-preview state:

1. close ReceiptBI and stop its local services;
2. back up any projects that must be retained;
3. remove the ReceiptBI application artifacts;
4. remove `~/.receiptbi-desktop` if all local projects, settings, credentials, and logs should be deleted;
5. if a legacy directory still exists, review it separately and remove it only after a verified cold migration.

This manual operation is destructive. A future release should provide an in-product, clearly scoped erase/export flow before claiming polished lifecycle management.

## Practical Guidance for Sensitive Data

- Use a database account with server-enforced read-only permissions.
- Prefer a local model endpoint when source content must not be sent to a cloud provider.
- Remove unnecessary identifying columns before import when the task does not require them.
- Review the selected provider URL and model before starting an investigation.
- Inspect report evidence and exported artifacts before sharing them.
- Do not share the desktop data directory, application database, `.env` files, or logs without review.

## Claims ReceiptBI Does Not Make

ReceiptBI does not claim zero data exposure, zero hallucination, absolute privacy, absolute correctness, or compliance with a particular regulatory regime. Its trust boundary is narrower: protect originals, default databases to read-only, isolate projects, disclose model context, preserve execution evidence, and let users correct durable business meaning.

See [Status](STATUS.md) for current implementation and release gaps.
