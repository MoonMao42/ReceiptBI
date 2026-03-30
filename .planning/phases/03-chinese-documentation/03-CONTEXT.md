# Phase 3: Chinese Documentation - Context

**Gathered:** 2026-03-30
**Status:** Ready for planning

<domain>
## Phase Boundary

Create README.zh.md — a complete Chinese translation of the existing README.md (386 lines). This phase delivers documentation only; no code changes.

</domain>

<decisions>
## Implementation Decisions

### Translation Style
- **D-01:** Technical terms (Next.js, FastAPI, SQLAlchemy, Docker, SSE, etc.) remain in English. Descriptive content uses natural Chinese expression, not literal word-for-word translation.
- **D-02:** Code blocks, CLI commands, environment variable names, and file paths remain unchanged (English).
- **D-03:** UI-related terms that appear in the app should match the app's existing Chinese i18n translations (check `apps/web/src/i18n/messages/` for consistency).

### Document Structure
- **D-04:** Mirror the English README structure exactly — same sections in same order. This keeps maintenance simple (diff-based sync).
- **D-05:** File name: `README.zh.md` in project root.

### Language Switching
- **D-06:** Add a language switch line at the top of both README.md and README.zh.md linking to each other. Format: `[English](README.md) | [中文](README.zh.md)`

### Claude's Discretion
- Translation tone: professional but approachable, consistent with the existing README tone
- Whether to localize the Mermaid diagram labels (recommend: yes, translate to Chinese)
- Badge text: keep English (shield.io badges don't render well with CJK)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Source Document
- `README.md` — The English source document to translate (386 lines, all sections)

### i18n Reference
- `apps/web/src/i18n/messages/` — Existing Chinese translations for UI terms; use consistent terminology

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `README.md` (386 lines): Complete source document with Features table, Mermaid diagram, Quick Start (3 platforms), Tech Stack badges, Configuration reference, Startup scripts, Docker dev, Local dev, Tests, Deployment, Known Limitations
- `apps/web/src/i18n/messages/`: Existing Chinese UI translations for terminology consistency

### Established Patterns
- Project uses `docs/images/` for screenshots — same paths work in both READMEs
- Mermaid diagram syntax is language-agnostic but labels should be translated

### Integration Points
- `README.zh.md` in project root alongside `README.md`
- Both files need cross-links added at the top

</code_context>

<specifics>
## Specific Ideas

No specific requirements — standard professional translation following the source document structure.

</specifics>

<deferred>
## Deferred Ideas

- DOC-02 (v2): 中文开发者指南（架构说明、贡献指南）— tracked in REQUIREMENTS.md as v2

</deferred>

---

*Phase: 03-chinese-documentation*
*Context gathered: 2026-03-30*
