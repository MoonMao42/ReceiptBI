# Phase 3: Chinese Documentation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-30
**Phase:** 03-chinese-documentation
**Areas discussed:** Translation Style, Document Structure, Language Switching
**Mode:** Auto (all decisions auto-selected)

---

## Translation Style

| Option | Description | Selected |
|--------|-------------|----------|
| Technical terms in English, descriptions in Chinese | Natural Chinese with English technical vocabulary | ✓ |
| Full translation including technical terms | All content translated to Chinese | |
| Mixed with pinyin annotations | Technical terms with Chinese annotations | |

**User's choice:** [auto] Technical terms in English, descriptions in Chinese (recommended default)
**Notes:** Standard approach for Chinese technical documentation

---

## Document Structure

| Option | Description | Selected |
|--------|-------------|----------|
| Mirror English structure exactly | Same sections, same order | ✓ |
| Reorganize for Chinese readers | Adjust section order for Chinese reading habits | |

**User's choice:** [auto] Mirror English structure exactly (recommended default)
**Notes:** Simplifies maintenance — changes to one README can be easily synced to the other

---

## Language Switching

| Option | Description | Selected |
|--------|-------------|----------|
| Cross-links at top of both files | Simple text links between README.md and README.zh.md | ✓ |
| Language badge | Shield.io badge for language switching | |
| No switching mechanism | Separate files, no cross-linking | |

**User's choice:** [auto] Cross-links at top of both files (recommended default)
**Notes:** Most common pattern for multilingual GitHub READMEs

---

## Claude's Discretion

- Translation tone (professional but approachable)
- Mermaid diagram label localization
- Badge text language

## Deferred Ideas

- DOC-02: Chinese developer guide (architecture, contribution guide) — v2 scope
