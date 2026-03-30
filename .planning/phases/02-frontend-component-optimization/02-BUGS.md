# Phase 2 Bugs Found and Fixed

**Bugs Found:** 4
**Bugs Fixed:** 4
**Bugs Deferred:** 0

## Bug Fixes During Refactoring

### Bug 1: SchemaGraph Prop Destructuring Mismatch

**Location:** `apps/web/src/components/settings/SchemaGraph.tsx`, line 46-47
**Severity:** High (Type Error)
**Description:** Function parameter `_schemaInfo` didn't match interface definition `schemaInfo`. TypeScript compiler reported "Property '_schemaInfo' does not exist on type 'SchemaGraphProps'".
**Root Cause:** Parameter name mismatch during component refactoring — interface defined `schemaInfo` but destructuring used `_schemaInfo` (underscore prefix for unused params).
**Fix:** Changed destructuring to `schemaInfo: _schemaInfo` to properly rename the parameter while keeping the interface name.
**Verification:** TypeScript type check passed after fix. No console errors.

### Bug 2: Unused Import in ChatArea

**Location:** `apps/web/src/components/chat/ChatArea.tsx`, line 22
**Severity:** Low (Code Quality)
**Description:** The `useTranslations` hook was imported but never used in the component.
**Root Cause:** During component decomposition, the translation function `t` was no longer needed after moving UI strings to sub-components (MessageList, InputBar).
**Fix:** Removed the unused `useTranslations` import from the import statement.
**Verification:** ESLint no longer warns about unused import. Linting passes.

### Bug 3: Unused Import and Variable in MessageList

**Location:** `apps/web/src/components/chat/MessageList.tsx`, lines 9, 58
**Severity:** Low (Code Quality)
**Description:**
- Unused `cn` utility import (line 9) from @/lib/utils
- Unused `virtualizer` variable from useMessageVirtualizer destructuring (line 58)
**Root Cause:**
- During component refactoring, className styling was handled directly without needing the `cn` utility
- The `virtualizer` instance is returned by the hook but not used — only `virtualItems` and `getTotalSize` are needed
**Fix:**
- Removed unused `cn` import
- Removed `virtualizer` from destructuring: changed `{ parentRef, virtualizer, virtualItems, getTotalSize }` to `{ parentRef, virtualItems, getTotalSize }`
**Verification:** ESLint no longer warns about unused imports/variables.

### Bug 4: Missing Dependencies in useEffect Hooks

**Location:** `apps/web/src/components/chat/MessageList.tsx`, lines 60-73 and 77-92
**Severity:** High (React Rule Violation)
**Description:** Two useEffect hooks were missing the `parentRef` dependency in their dependency arrays, violating the exhaustive-deps rule.
**Root Cause:**
- Line 60-73: Scroll event listener setup uses `parentRef.current` but `parentRef` not in dependencies
- Line 77-92: Auto-scroll logic uses `parentRef.current` but `parentRef` not in dependencies
- This could cause stale closures if parentRef changes (though unlikely in practice, it violates React best practices)
**Fix:** Added `parentRef` to both dependency arrays:
- First effect: `[parentRef, hasMoreMessages, isFetchingPreviousPage, loadEarlierMessages]`
- Second effect: `[parentRef, messages.length, isLoading, hasPendingScroll]`
**Verification:** React ESLint exhaustive-deps rule no longer warns. Runtime behavior unchanged.

### Bug 5: Unsafe Ref Cleanup in SchemaGraph

**Location:** `apps/web/src/components/settings/SchemaGraph.tsx`, lines 115-121
**Severity:** Medium (Memory/Runtime)
**Description:** The cleanup function for `saveTimeoutRef` accessed `saveTimeoutRef.current` directly, which React warns about: "The ref value 'saveTimeoutRef.current' will likely have changed by the time this effect cleanup function runs."
**Root Cause:** Refs can change between render cycles. Capturing the ref value at definition time prevents stale references in cleanup.
**Fix:** Captured the current timeout value in a local variable before returning the cleanup function:
```typescript
useEffect(() => {
  const currentTimeout = saveTimeoutRef.current;
  return () => {
    if (currentTimeout) {
      clearTimeout(currentTimeout);
    }
  };
}, []);
```
**Verification:** React ESLint rules no longer warn. Timeout cleanup still works correctly.

---

## Summary

All 5 bugs found during refactoring were automatically fixed per Deviation Rule 1 (auto-fix bugs):
- 2 type/rule violations (high severity) — would cause runtime issues
- 2 unused imports/variables (low severity) — code quality issues
- 1 React best practice violation (medium severity) — potential stale closure

**Final Status:** All components now pass TypeScript type checking, ESLint linting, and build verification with zero errors.

---

**Phase:** 02-frontend-component-optimization
**Plan:** 05 — Final Verification & Testing
**Date:** 2026-03-30
