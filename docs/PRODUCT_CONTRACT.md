# ReceiptBI Product Contract

> This contract defines durable product behavior. It is not a statement that every desired quality loop is already complete; current implementation truth lives in [Status](STATUS.md).

## 1. Positioning

ReceiptBI is a local-first personal data analyst for operations, finance, sales, and small-team owners who work with recurring business files and ordinary read-only databases.

The durable loop is:

```text
messy data → non-destructive preparation → project understanding → autonomous investigation
           → evidence-backed report → user correction → verified reuse on later work
```

ReceiptBI is not a chat-to-SQL interface, database IDE, general notebook, low-code app platform, or enterprise BI governance system. Conversation drives investigation, while an editable report workspace lets the user assemble durable BI reports from verified results and manual content. Projects, data versions, knowledge, runs, report documents, recipes, and evidence are durable objects.

“Local-first” means project state is managed on the user's device. It does not mean a configured cloud model receives no context. The application must describe the real data flow rather than promise absolute privacy or offline behavior.

## 2. System Responsibility Invariants

The following responsibilities belong to ReceiptBI and must not depend on a model remembering instructions:

1. **Project isolation** — sources, knowledge, history, recipes, references, and corrections from one project do not silently enter another.
2. **Source protection** — file originals remain unchanged; customer databases are read-only by default; working copies and analysis artifacts are separate objects.
3. **Deterministic preflight** — the system detects structural and quality issues, applies only safe transformations automatically, and blocks on business ambiguity that can materially change the result.
4. **Version identity** — source fingerprints, working versions, schema drift, and checkpoint inputs are tracked. A changed source cannot be mistaken for an old verified input.
5. **Relationship safety** — proposed joins are candidates until match rate, cardinality, and row expansion are checked. Proof is bound to exact source and table inputs; a filtered, aggregated, derived, truncated, or table-unknown result cannot validate the full relationship. Unverified relationships are not executable knowledge.
6. **Knowledge precedence** — candidates cannot overwrite confirmed or locked definitions; locked definitions change only through explicit user action.
7. **Execution boundaries** — SQL, Python, dependency installation, cancellation, timeouts, and result persistence run through product-owned tools and policies.
8. **Evidence-bound completion** — numbers, tables, and charts presented as completed results must come from current execution and retain their source and validation evidence.
9. **Recoverable lifecycle** — a run has a stable identity and observable state; checkpoints store verified tool state rather than hidden model reasoning.
10. **Reversible learning** — durable knowledge has provenance, evidence, validity, and a way to become stale, be corrected, unlocked, or removed.

A weaker model may investigate less effectively, require repair, or fail to finish. It must not be able to bypass these invariants and turn a plausible narrative into a trusted result.

## 3. Model and Product Boundary

The model may:

- interpret the user's business goal;
- identify useful questions and competing hypotheses;
- choose an investigation direction and product-owned tools;
- adapt the depth, grouping, and presentation to the data;
- explain findings in ordinary business language;
- ask one material clarification when the system cannot safely resolve it.

ReceiptBI must:

- load and profile the actual current sources;
- expose only allowed source identities and tools;
- prefer a source-bound structured query contract, validate requested fields against the current schema, and compile read-only execution plans inside the product;
- resolve and validate data relationships;
- normalize, query, join, aggregate, and run analysis inside controlled runtimes;
- verify result shape, row expansion, truncation, hashes, and requested artifact integrity;
- preserve the report, evidence, corrections, and run lifecycle;
- decide whether knowledge is merely a candidate or is eligible for durable reuse.

Raw SQL and project-isolated Python remain controlled fallbacks for work the structured contract cannot express. They do not bypass the same source, read-only, evidence, cancellation, and completion policies.

A reusable analysis is a method contract, not captured model code. ReceiptBI may execute a saved method before the model only when the method is a v3 contract with one logical source, one strictly typed structured query, one final validation, and no hidden semantic or relationship side effects. The system must bind the current source, recompile the declarative plan, execute it under current read-only limits, validate the current result, and issue a SQL-free receipt bound to that execution. The model then explains or presents the verified result; it does not recreate the data step. Complex, unknown, and v2 methods remain `agent_replan_required`, and no old result rows are silently reused.

Python, the Rust SQLite sidecar, PydanticAI, Wren Core, DuckDB, Polars, pandas, Plotly, and any particular model provider are replaceable implementation components. They are not the product moat or a public ABI.

## 4. Project Understanding and Evolution

Project knowledge has three states:

| State | Meaning | Allowed behavior |
|---|---|---|
| Candidate | Inferred from data, a model, or prior work | May guide investigation as a hypothesis; cannot silently override durable meaning |
| Confirmed | Accepted by the user or supported by an independent validation | Reused inside the same project, subject to source and validity checks |
| Locked | Explicitly owned by the user | Cannot be changed or demoted by the agent |

Every entry records its type, value or executable strategy, source, evidence, confidence, validity, and timestamps. Text that cannot constrain execution is not enough for an executable metric, filter, or relationship.

An entry's history is append-only. One revision is the active head; editing or restoring creates another revision with its parent, actor, reason, and source evidence instead of rewriting the old record. A restore is therefore reversible too. Concurrent work based on a stale head must refresh and surface the conflict rather than silently replacing the newer meaning. Any material definition change invalidates execution proof produced for the previous revision.

Business meaning and execution readiness are separate contracts. A confirmed or locked entry may still be `definition_only`, `needs_validation`, `verified`, or `blocked`. Only `verified` definitions enter ordinary future execution automatically; a correction-specific rerun may trial a typed `needs_validation` definition, but it becomes verified only after the system proves that the current definition was applied, reached the final result, and was followed by final validation.

An executable metric formula is data, not code: a bounded expression tree over stable source bindings, with explicit evaluation order, null policy, and divide-by-zero behavior. ReceiptBI evaluates supported arithmetic with Decimal semantics and records both the definition hash and output-column lineage. Python snippets, `eval`, model-authored callables, or a later unrelated aggregate cannot manufacture formula verification.

Promotion rules:

1. Tool success alone never promotes knowledge.
2. A user can explicitly confirm or lock a business definition.
3. A relationship also requires current structural validation before execution.
4. A report correction is run-scoped by default. Long-term reuse requires the user to select a business-facing target issued from the completed run's system evidence; the client receives an opaque, run-bound and semantic-revision-bound reference rather than an internal key. “Overall conclusion / other” remains unbound and cannot be silently inferred into project knowledge.
5. Reusable analysis methods store source roles, business rules, typed transformation intent, validation requirements, and artifact shape—not stale source IDs, old result rows, compiled SQL, or blindly replayable model code. Only the narrow v3 system-executable shape may run deterministically; every other shape is an agent replanning contract.
6. New-period data re-runs preparation and checks drift before reuse. A previously trusted version remains distinguishable from a pending replacement.
7. Conflicts create a visible candidate or attention state; they do not silently mutate confirmed or locked knowledge.
8. A corrected report carries a system-owned application receipt. Report prose, tool success, or a model claim cannot manufacture that receipt.
9. Editing or restoring project knowledge appends a revision; it never erases the prior definition, and old execution proof does not survive a changed meaning.
10. Material confirmation questions use system-owned stable decision slots. Known aliases may resolve to one canonical slot, but fuzzy similarity must not merge neighboring concepts; conflicting durable answers block automatic reuse.
11. A correction created from an older report cannot overwrite a newer semantic revision. Editing the same correction may continue only while that correction still owns the active semantic head; locked, deactivated, conflicting, cross-run, and tampered targets fail closed.

Cleaning methods follow the same non-destructive history rule. Each source has one current method and that method has one active head plus append-only revisions for acceptance, undo, and restore. Restoring an earlier method must not silently replace the working data behind a current report: it becomes effective only after an explicit reapply and current drift checks. A portable project bundle may preserve the complete method history, but an imported template is not executable until it is trialled in an isolated working area and explicitly bound to a source. Binding must reject stale source, working-copy, recipe-head, template-head, or output evidence instead of creating a second competing current method.

The learning loop is successful only when later work asks fewer redundant questions, preserves the intended business definition, detects drift, and can explain or reverse what was reused.

## 5. Investigation Lifecycle

ReceiptBI exposes five ordinary-user states:

| State | User meaning | Required behavior |
|---|---|---|
| Understanding data | Reading the task, sources, and current project definitions | Show the current goal without implying a conclusion exists |
| Waiting for confirmation | One material business ambiguity blocks safe progress | Ask in business language, explain impact, and continue the same run after the answer |
| Investigating | Querying, relating, comparing, analyzing, or validating | Show business milestones and a cancel action, not model chain-of-thought |
| Completed | Current execution and validation produced a usable result | Show the report, scope, evidence, and useful next questions |
| Needs attention | Data, drift, user stop, or unrecoverable failure requires action | Give one clear next action rather than only a technical error |

Runs may use multiple SQL and Python steps, revise hypotheses, or decide that no chart is useful. ReceiptBI must not force every question into a predefined table, a visualization, one SQL query, or one Python call.

When a required reusable analysis is classified as the narrow system-executable v3 shape, the lifecycle has one additional pre-model step: bind the current source, run the saved typed intent, validate it, and hand the verified result to the model for explanation. If the source is ambiguous, pending replacement, structurally drifted, truncated, or no longer matches the stored result contract, the run needs attention rather than falling back to old data. This is a bounded reliability lane, not a promise that all analyses automatically re-run.

## 6. Generic Completion Contract

There is no product-wide fixed golden output. A run can be completed only when all conditions relevant to that task are satisfied:

1. The user's actual goal and current project scope are preserved.
2. Required sources are present and safe to use; unresolved material ambiguities are handled.
3. Every stated number or comparison comes from current execution.
4. Cross-source analysis uses a validated relationship and records its effect on match and row count. Reusable proof must come from a complete system-owned check over two table-bound inputs; partial-result evidence remains local to the current run.
5. The result is checked for required columns, truncation, row expansion, hashes, and other task-relevant assertions.
6. Requested deliverables are real artifacts bound to the run. ReceiptBI does not require a chart when none was requested or useful, and it does not hard-code a chart type unless the user explicitly requires that type.
7. Limitations, missing data, and unresolved uncertainty are stated in business language.
8. The report and its advanced evidence are two views of the same run, not separately invented answers.

Acceptance scenarios should test these invariants across varied domains and artifact shapes. A test suite may include messy single files, cross-source joins, corrections, weak-model repair, interrupted runs, and new-period drift, but no one business story defines the product.

### Editable report documents

An investigation report and an editable BI report are related but different objects. The investigation and its artifacts remain evidence-bearing records. A `ReportDocument` may reference those records and combine them with user-authored pages and blocks without rewriting the original run or artifact.

The report workspace has a calm reading mode and an explicit editing mode. In editing mode the user can add, remove, reorder, resize, duplicate, relabel, and reconfigure pages and blocks; add content from completed investigations; and maintain manual narrative, KPI, chart, table, evidence, and filter blocks. Manual changes are identified as manual content. Editing a displayed value must never silently change the underlying investigation evidence.

Project understanding is likewise user-editable. The user may create and change names, types, definitions, relationships, and governance state. Each change remains versioned, invalidates stale execution proof when material, and cannot erase the prior semantic revision.

## 7. Ordinary and Advanced Views

The ordinary workspace shows projects, data readiness, business milestones, conclusions, metrics, charts, evidence summaries, horizontally browsable report history, project-understanding history, cleaning-method history, imported-method before/after previews, and next actions. It does not require users to understand SQL, Python, schema editors, semantic-engine names, prompts, dependency managers, fingerprints, local paths, or diagnostics.

Advanced views may reveal real queries, code, data preparation steps, relationship checks, knowledge provenance, retries, checkpoints, dependencies, and technical errors. Advanced access does not bypass source protection, project isolation, read-only database rules, or completion validation.

## 8. Data and Privacy Contract

- Model context follows the configured provider and must be disclosed honestly.
- Credentials remain local and encrypted at rest in the current application database.
- File originals and customer databases are not mutated by analysis.
- Logs and advanced evidence are local but may contain sensitive technical or data details and require review before sharing.
- Dependency installation is isolated by project and may use the network.
- Uninstall and deletion behavior must be stated explicitly; the application cannot imply that removing the executable erases all local data.

See [Data and Privacy](DATA_AND_PRIVACY.md) for the current data flow.

## 9. Product Boundaries

ReceiptBI does not currently pursue:

- the largest connector catalog;
- database administration or write SQL;
- a general-purpose coding or notebook environment;
- team accounts, permission centers, shared dashboards, or a hosted control plane;
- low-code application publishing;
- claims of zero hallucination, absolute correctness, absolute privacy, or absolute locality;
- a UI organized around internal frameworks, schema plumbing, or prompt configuration.

New work should strengthen the preparation → understanding → investigation → correction → reuse loop before expanding the product surface.

## 10. Decision Gate

Before adding a capability, answer:

1. Does it help an ordinary user complete real analysis work faster?
2. Does it strengthen a system responsibility or the verified learning loop?
3. Can it be accepted through current execution evidence and user-visible states?
4. Would the capability still matter if the model or internal framework changed?

If any answer is no, the capability should not enter the current product by default.
