# Coding Conventions

**Analysis Date:** 2026-03-29

## Naming Patterns

**Files:**
- React components: PascalCase (e.g., `ChatArea.tsx`, `AssistantMessageCard.tsx`)
- Utility/helper modules: lowercase-dash or camelCase (e.g., `chat-helpers.ts`, `connections.ts`)
- Type definition files: lowercase with `.ts` extension (e.g., `api.ts`, `chat.ts`)
- Configuration/settings files: descriptive lowercase (e.g., `schema.ts`, `models.ts`)

**Functions:**
- Use camelCase for all functions (e.g., `applyStreamEvent`, `buildPendingAssistantMessage`, `mergeExecutionContext`)
- Builder functions prefixed with `build` (e.g., `buildConnectionExportName`, `buildModelFormData`)
- Mapper/transformer functions prefixed with appropriate verbs (e.g., `mapApiMessage`, `applyStreamEvent`)
- Query/filter functions named descriptively (e.g., `filterVisibleTables`, `deriveHiddenTables`)
- Hook functions start with `use` prefix (e.g., `useChatStore`, `useModelSettingsResource`)

**Variables:**
- Use camelCase for local variables and parameters
- Use underscore prefix for unused parameters that are required by API (e.g., `_sidebarOpen` in `ChatArea`)
- Constants in UPPER_SNAKE_CASE (e.g., `STORAGE_KEY_CONNECTION`, `CONNECTION_DRIVERS`, `MODEL_PRESETS`)
- Boolean variables often prefixed with `is`, `has`, `show`, `can` (e.g., `isLoading`, `hasError`, `showForm`, `canRetry`)

**Types:**
- Interface names are PascalCase (e.g., `ChatMessage`, `ConnectionFormData`, `SSEProgressData`)
- Suffix interfaces with specific naming conventions:
  - Form data types: `*FormData` (e.g., `ConnectionFormData`, `ModelFormData`, `TermFormData`)
  - API response types: `*Data` (e.g., `SSEProgressData`, `SSEResultData`, `SSEErrorData`)
  - Summary/summary types: `*Summary` (e.g., `ConnectionSummary`, `ExecutionContextSummary`)
  - Component prop types: `*Props` (e.g., `ChatAreaProps`, `ModelSettingsFormProps`)

## Code Style

**Formatting:**
- Enforced by ESLint with Next.js configuration (`eslint.config.mjs`)
- Uses TypeScript strict mode
- Import sorting enforced by ESLint

**Linting:**
- ESLint 9.x with `@typescript-eslint` support
- Extends `next/core-web-vitals` and `next/typescript`
- Unused variables rule: `@typescript-eslint/no-unused-vars` set to warn, arguments matching `^_` pattern are ignored
- Explicit `any` usage: `@typescript-eslint/no-explicit-any` set to warn (discouraged but allowed with warning)

## Import Organization

**Order:**
1. React and Next.js core imports (e.g., `import { useState } from "react"`)
2. Third-party libraries (e.g., `from "zustand"`, `from "@tanstack/react-query"`)
3. Type imports from third-party (e.g., `from "next/navigation"`)
4. Absolute imports from codebase using `@/` alias (e.g., `from "@/lib/types/api"`)
5. Relative imports from same directory (e.g., `from "./ChatEmptyState"`)

Example from `ChatArea.tsx`:
```typescript
import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { AppSettings, ConnectionSummary, ModelSummary } from "@/lib/types/api";
import { api } from "@/lib/api/client";
import { useChatStore } from "@/lib/stores/chat";
import { AssistantMessageCard } from "./AssistantMessageCard";
```

**Path Aliases:**
- `@/` maps to `src/` directory (configured in `vitest.config.ts` and Next.js)
- Always use absolute imports with `@/` for codebase modules, never relative paths across directories

## Error Handling

**Patterns:**
- Type guard functions for error checking (see `isError()` in `api.ts`)
- Utility function `getErrorMessage()` for extracting error messages from any error type
- State management for error handling in hooks: `const [error, setError] = useState<string | null>(null)`
- API errors caught in mutation handlers with `onError` callback
- Error categories tracked separately (e.g., `errorCategory: "sql"`, `errorCategory: "client"`)
- Client-side errors distinguished from server-side errors via `errorCode: "CLIENT_ERROR"`

Example from `useModelSettingsResource.ts`:
```typescript
onError: (error) => {
  setError(getApiErrorMessage(error, "Failed to add model"));
}
```

## Logging

**Framework:** No logging framework used in frontend code. Uses browser console.

**Patterns:**
- Direct console output appears to be avoided in favor of UI state management
- Errors are captured in component state and displayed to users
- SSE parsing errors caught but silently ignored (in `api/client.ts` line 66-67)

## Comments

**When to Comment:**
- Comment code that implements non-obvious business logic
- Comments on type definitions explaining purpose (e.g., line 2 in `api.ts`: "消除 any 类型，提供类型安全")
- No excessive comments on self-documenting code

**JSDoc/TSDoc:**
- Minimal usage in frontend codebase
- Type definitions in `api.ts` include comments on complex interfaces:
  ```typescript
  /** 数据库查询结果行 */
  export type DataRow = Record<string, string | number | boolean | null>;

  /** SSE 进度事件数据 */
  export interface SSEProgressData { ... }
  ```

## Function Design

**Size:**
- Helper functions are small and focused (e.g., `cn()` in `utils.ts` is 2 lines)
- Component functions range from 100-600 lines for complex settings components
- Store mutation functions are contained within Zustand store definition

**Parameters:**
- React components receive props as single object parameter typed with interface
- Utility functions take specific parameters rather than generic objects
- Optional parameters defaulted in function signature (e.g., `now = new Date()` in `buildConnectionExportName`)

**Return Values:**
- Functions return properly typed values (no implicit `any`)
- Error handling functions return discriminated unions for type safety (e.g., `SSEEventData` union type)
- Builder functions return complete objects ready for API/state use

## Module Design

**Exports:**
- Named exports preferred for utilities and helpers
- Default exports for React components
- Type-only exports for interface definitions: `export type TermFormData = { ... }`

Example from `chat-helpers.ts`:
```typescript
export type ChatStreamEventPayload = Exclude<SSEEventData, { type: "error" | "done" }>;
export function mapApiMessage(msg: APIMessage): ChatMessage { ... }
export const useChatStore = create<ChatState>(...)
```

**Barrel Files:**
- Not extensively used in this codebase
- Each module exports its own functions directly
- Imports are specific to what's needed (e.g., `import { applyStreamEvent, buildPendingAssistantMessage } from "@/lib/stores/chat-helpers"`)

---

*Convention analysis: 2026-03-29*
