# Phase 2: Frontend Component Optimization - Context

**Gathered:** 2026-03-30
**Status:** Ready for planning

<domain>
## Phase Boundary

Decompose large React components (ChatArea 408 lines, SchemaSettings 618 lines) into focused sub-components with custom hooks. Implement message history pagination with backend API support and infinite scroll. Add virtual scrolling for large conversations. Optimize Schema visualization rendering performance. Fix bugs found during refactoring.

</domain>

<decisions>
## Implementation Decisions

### Component Decomposition Strategy
- **D-01:** Split by functional area, not by state. Each sub-component maps to a visual region.
- **D-02:** ChatArea (408 lines) → MessageList, InputBar, MessageCard sub-components. State stays in useChatStore (Zustand).
- **D-03:** SchemaSettings (618 lines) → SchemaGraph, RelationshipPanel, LayoutControls sub-components.
- **D-04:** Target: each sub-component < 120 lines. Extract shared logic into custom hooks.

### Message Pagination
- **D-05:** Scroll-to-top auto-load (like WeChat/Telegram). When user scrolls to the top, automatically fetch earlier messages.
- **D-06:** Backend API returns 50 messages per page via new paginated endpoint.
- **D-07:** Use TanStack Query's useInfiniteQuery for paginated data fetching with cursor-based pagination.

### Virtual Scrolling
- **D-08:** Use TanStack Virtual (project already uses TanStack Query — ecosystem consistency).
- **D-09:** Handle dynamic message heights (SQL results, charts, code blocks vary in height). Use TanStack Virtual's `estimateSize` + `measureElement` for dynamic measurement.
- **D-10:** Maintain scroll position when new messages load at top (prepend without jump).

### Carried Forward from Phase 1
- **D-11:** Lightweight testing approach — rely on existing tests + manual verification (from Phase 1 D-06)
- **D-12:** Deep dive bug hunting — actively find edge cases, race conditions during refactoring (from Phase 1 D-08)

### Claude's Discretion
- Exact sub-component boundaries within ChatArea and SchemaSettings (decide based on actual code)
- Custom hook naming and extraction patterns
- Schema visualization memoization strategy (useMemo granularity)
- How to handle scroll-to-bottom for new incoming messages while virtual scrolling is active
- Loading skeleton/spinner design for pagination

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Frontend components to decompose
- `apps/web/src/components/chat/ChatArea.tsx` — 408-line chat component to split
- `apps/web/src/components/settings/SchemaSettings.tsx` — 618-line schema component to split
- `apps/web/src/components/chat/AssistantMessageCard.tsx` — Message display (288 lines, may need optimization)

### State management
- `apps/web/src/lib/stores/chat.ts` — Zustand chat store (messages, conversations)
- `apps/web/src/lib/stores/chat-helpers.ts` — Chat helper functions

### API layer
- `apps/web/src/lib/api/client.ts` — SSE/API client
- `apps/api/app/api/v1/chat.py` — Backend chat endpoints (needs pagination endpoint)
- `apps/api/app/api/v1/schema.py` — Schema API (relationship suggestions — O(n²) optimization)

### Types
- `apps/web/src/lib/types/chat.ts` — ChatMessage union type
- `apps/web/src/lib/types/api.ts` — API types

### Codebase analysis
- `.planning/codebase/ARCHITECTURE.md` — Frontend architecture overview
- `.planning/codebase/CONVENTIONS.md` — Code style and patterns
- `.planning/codebase/CONCERNS.md` — Performance bottlenecks (chat accumulation, schema re-renders)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Zustand store (`useChatStore`) — already manages messages, conversation state
- TanStack Query — already set up for data fetching (connections, models, history)
- `@xyflow/react` — already used for schema graph visualization
- Tailwind CSS + clsx/tailwind-merge — styling utilities in place
- `lucide-react` — icon library already available

### Established Patterns
- State management: Zustand for client state, TanStack Query for server state
- Styling: Tailwind CSS with utility composition via `cn()` helper
- Data fetching: axios + TanStack Query with invalidation on mutations
- SSE streaming: custom `createSecureEventStream` in api/client.ts
- Component exports: default exports for React components, named exports for utilities

### Integration Points
- New pagination API endpoint connects to existing chat.py router
- MessageList component connects to useChatStore for message data
- Virtual scrolling wraps around existing message rendering logic
- Schema memoization applies to existing ReactFlow node/edge state

</code_context>

<specifics>
## Specific Ideas

- Scroll-to-top loading should feel natural like WeChat/Telegram — no jarring jumps
- Schema graph should stay responsive even with 100+ tables
- Keep the existing chat UX feel — just make it faster and more maintainable

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-frontend-component-optimization*
*Context gathered: 2026-03-30*
