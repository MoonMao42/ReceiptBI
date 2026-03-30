# Phase 2: Frontend Component Optimization - Research

**Researched:** 2026-03-30
**Domain:** React component decomposition, virtual scrolling, pagination, performance optimization
**Confidence:** HIGH

## Summary

Phase 2 requires refactoring two large React components (ChatArea 408 lines, SchemaSettings 618 lines) into maintainable sub-components, implementing message pagination with cursor-based infinite scrolling, and optimizing rendering with virtual scrolling for conversations with 1000+ messages.

The technology stack is well-defined: TanStack Query v5.50.0 for infinite pagination (useInfiniteQuery), TanStack Virtual for dynamic-height message virtualization, and custom hooks for stateful logic extraction. The project already uses Zustand for client state and has working SSE infrastructure for real-time data streaming.

**Primary recommendation:** Decompose by functional area (MessageList, InputBar, MessageCard), extract scroll/pagination logic into custom hooks (useMessagePagination, useMessageVirtualizer), and implement cursor-based message history pagination starting from the backend API.

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Split by functional area, not by state. Each sub-component maps to a visual region.
- **D-02:** ChatArea (408 lines) → MessageList, InputBar, MessageCard sub-components. State stays in useChatStore (Zustand).
- **D-03:** SchemaSettings (618 lines) → SchemaGraph, RelationshipPanel, LayoutControls sub-components.
- **D-04:** Target: each sub-component < 120 lines. Extract shared logic into custom hooks.
- **D-05:** Scroll-to-top auto-load (like WeChat/Telegram). When user scrolls to the top, automatically fetch earlier messages.
- **D-06:** Backend API returns 50 messages per page via new paginated endpoint.
- **D-07:** Use TanStack Query's useInfiniteQuery for paginated data fetching with cursor-based pagination.
- **D-08:** Use TanStack Virtual (project already uses TanStack Query — ecosystem consistency).
- **D-09:** Handle dynamic message heights (SQL results, charts, code blocks vary in height). Use TanStack Virtual's `estimateSize` + `measureElement` for dynamic measurement.
- **D-10:** Maintain scroll position when new messages load at top (prepend without jump).
- **D-11:** Lightweight testing approach — rely on existing tests + manual verification (from Phase 1 D-06)
- **D-12:** Deep dive bug hunting — actively find edge cases, race conditions during refactoring (from Phase 1 D-08)

### Claude's Discretion
- Exact sub-component boundaries within ChatArea and SchemaSettings (decide based on actual code)
- Custom hook naming and extraction patterns
- Schema visualization memoization strategy (useMemo granularity)
- How to handle scroll-to-bottom for new incoming messages while virtual scrolling is active
- Loading skeleton/spinner design for pagination

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FRONT-01 | ChatArea.tsx (408 lines) decomposed into container + sub-components + custom hooks | Component decomposition patterns documented; current ChatArea structure analyzed (header 132 lines, message rendering 96 lines, input form 62 lines, state management ~118 lines) |
| FRONT-02 | SchemaSettings.tsx (618 lines) decomposed into graph + relationships + layout components | SchemaSettings structure analyzed (header/controls 154 lines, layout dropdown 152 lines, graph rendering 145 lines, mutations 85 lines) |
| FRONT-03 | Chat message pagination: new backend API + frontend infinite scroll | Backend history.py pagination pattern verified; cursor-based pagination implementation pattern identified |
| FRONT-04 | Virtual scrolling for 1000+ messages at 60 FPS | TanStack Virtual patterns researched; dynamic height measurement verified |
| FRONT-05 | Schema visualization useMemo optimization | Current useCallback/useMemo usage analyzed in SchemaSettings |
| FRONT-06 | Schema layout calculation extracted to independent hook | buildLayoutSnapshot helper already extracted; can be wrapped in custom hook |
| FRONT-07 | Bug fixes during refactoring | Testing infrastructure (Vitest 4.0+) verified; chat-helpers.test.ts pattern established |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| @tanstack/react-query | 5.50.0 | Server state management, infinite pagination | Already in project; useInfiniteQuery built for cursor/offset pagination |
| @tanstack/react-virtual | (NEW) | Virtualization for large lists | Ecosystem consistency with TanStack Query; handles dynamic item heights via estimateSize + measureElement |
| zustand | 5.0.0 | Client state management | Already managing chat messages, conversation state; lightweight alternative to Redux |
| React | 19.0+ | UI framework | Server components support; 18+ required for async transitions |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| react-markdown | 9.0.0 | Message content rendering | User messages use markdown; assistant responses in markdown tabs |
| react-syntax-highlighter | 15.6.6 | SQL/Python code display | SQL results and Python code tabs in AssistantMessageCard |
| recharts | 2.13.0 | Chart visualization | Visualization results in message cards |
| next-intl | 3.20.0 | i18n for loading states | Pagination loading messages, context round labels |
| lucide-react | 0.460.0 | Icons for UI controls | Already used throughout for buttons, status chips |
| @xyflow/react | 12.10.0 | Schema graph visualization | SchemaSettings uses ReactFlow; unchanged from Phase 1 |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| @tanstack/react-virtual | react-window | TanStack Virtual: dynamic heights, scroll preservation; react-window: simpler API but fixed heights |
| @tanstack/react-virtual | Intersection Observer (manual) | Virtual: optimized, handles edge cases; manual: ~200 LOC overhead, scroll position loss on re-renders |
| useInfiniteQuery | useQuery + manual pagination | Infinite Query: built for cursor pagination, automatic page deduping; useQuery: requires manual state tracking |
| Custom hooks (useMessagePagination) | Context + Provider | Custom hooks: easier to test, compose; Context: prop drilling reduction but adds provider wrapping |

**Installation:**
```bash
cd /Users/maokaiyue/QueryGPT/apps/web
npm install @tanstack/react-virtual@^3.0.0
```

**Version verification:**
- @tanstack/react-query: 5.50.0 (confirmed in package.json)
- @tanstack/react-virtual: v3.0.0+ (latest stable as of 2026, supports dynamic measurement)
- Zustand 5.0.0 (confirmed in package.json)

## Architecture Patterns

### Recommended Project Structure

```
apps/web/src/
├── components/
│   ├── chat/
│   │   ├── ChatArea.tsx          # Container (100 lines)
│   │   ├── MessageList.tsx       # Message virtualization (110 lines)
│   │   ├── InputBar.tsx          # Input form + submit (85 lines)
│   │   ├── MessageCard.tsx       # Message display wrapper (optional, if AssistantMessageCard needs nesting)
│   │   └── AssistantMessageCard.tsx  # Already exists, 288 lines (unchanged)
│   ├── settings/
│   │   ├── SchemaSettings.tsx    # Container with ReactFlowProvider (80 lines)
│   │   ├── SchemaSettingsInner.tsx # Core logic, refactored to ~180 lines
│   │   ├── SchemaGraph.tsx       # ReactFlow wrapper (120 lines)
│   │   ├── RelationshipPanel.tsx # Relationship suggestions + display (90 lines)
│   │   └── LayoutControls.tsx    # Layout dropdown + search (100 lines)
│   └── [existing components unchanged]
├── lib/
│   ├── hooks/
│   │   ├── useMessagePagination.ts  # (NEW) Infinite query + cursor state
│   │   ├── useMessageVirtualizer.ts # (NEW) TanStack Virtual + scroll position
│   │   ├── useSchemaLayout.ts       # (NEW) Extract layout snapshot logic
│   │   └── [existing hooks]
│   ├── stores/
│   │   ├── chat.ts              # (MODIFIED) Remove pagination logic, delegate to useMessagePagination
│   │   └── [existing stores]
│   └── [existing utilities]
```

### Pattern 1: Component Decomposition by Functional Area

**What:** Split large components into focused sub-components mapped to visual regions, not state concerns. Keep state in Zustand, pass down as props or via custom hooks.

**When to use:** Components >120 lines with multiple layout regions (header, content area, footer) or repeated rendering logic (message list items).

**Example:**

```typescript
// ChatArea.tsx — refactored container (100 lines)
import { MessageList } from "./MessageList";
import { InputBar } from "./InputBar";

export function ChatArea({ sidebarOpen, onToggleSidebar }: ChatAreaProps) {
  const { messages, isLoading } = useChatStore();
  const { data: connections } = useQuery({ queryKey: ["connections"] });
  const { data: models } = useQuery({ queryKey: ["models"] });

  return (
    <div className="flex h-full flex-col">
      <header>{/* Header content, connection/model dropdowns */}</header>
      <MessageList messages={messages} isLoading={isLoading} />
      <InputBar onSubmit={handleSubmit} readyToQuery={readyToQuery} />
    </div>
  );
}

// MessageList.tsx — virtualized message rendering (110 lines)
import { useMessageVirtualizer } from "@/lib/hooks/useMessageVirtualizer";
import { useMessagePagination } from "@/lib/hooks/useMessagePagination";

export function MessageList({ messages, isLoading }: MessageListProps) {
  const { virtualizer, virtualItems } = useMessageVirtualizer(messages);
  const { hasMore, isFetchingPreviousPage } = useMessagePagination();

  return (
    <div className="flex-1 overflow-y-auto" ref={virtualizer.parentRef}>
      {isFetchingPreviousPage && <LoadingSkeleton />}
      <div style={{ height: virtualizer.getTotalSize() }}>
        {virtualItems.map((virtualItem) => (
          <div key={messages[virtualItem.index].id} style={virtualItem.style}>
            {/* Message content */}
          </div>
        ))}
      </div>
    </div>
  );
}
```

**Source:** Component decomposition patterns from [React documentation](https://react.dev/learn/thinking-in-react), verified against existing project's AssistantMessageCard (288 lines, single responsibility: message display formatting).

### Pattern 2: Infinite Pagination with TanStack Query

**What:** Use `useInfiniteQuery` for cursor-based pagination. Backend returns pageParam (cursor) for next page; frontend calls `fetchNextPage()` when user scrolls to boundary.

**When to use:** Chat histories, feed scrolling, any scenario where user needs unlimited historical data.

**Example:**

```typescript
// hooks/useMessagePagination.ts (50 lines)
export function useMessagePagination(conversationId: string | null) {
  const { data, fetchPreviousPage, isFetchingPreviousPage, hasNextPage } = useInfiniteQuery({
    queryKey: ["messages", conversationId],
    queryFn: async ({ pageParam }) => {
      if (!conversationId) return { messages: [], nextCursor: null };
      const response = await api.get(`/api/v1/conversations/${conversationId}/messages`, {
        params: { cursor: pageParam, limit: 50 },
      });
      return {
        messages: response.data.data.items,
        nextCursor: response.data.data.next_cursor,
      };
    },
    initialPageParam: null, // Start with no cursor (most recent messages)
    getNextPageParam: (lastPage) => lastPage.nextCursor,
    select: (data) => data.pages.flatMap((page) => page.messages), // Flatten pages for rendering
  });

  return {
    messages: data || [],
    isFetchingPreviousPage,
    hasMore: hasNextPage,
    loadEarlier: fetchPreviousPage,
  };
}
```

**Backend API (new endpoint):**
```python
@router.get("/{conversation_id}/messages", response_model=APIResponse[PaginatedResponse[APIMessage]])
async def list_messages(
    conversation_id: UUID,
    cursor: str | None = Query(None),  # ISO timestamp or message ID
    limit: int = Query(50, ge=1, le=100),
):
    """Paginate messages with cursor-based pagination."""
    query = select(Message).where(Message.conversation_id == conversation_id)

    if cursor:
        # cursor is ISO datetime of the oldest message to fetch before
        query = query.where(Message.created_at < parse_iso(cursor))

    query = query.order_by(Message.created_at.desc()).limit(limit + 1)

    messages = await db.execute(query)
    items = list(messages.scalars())

    next_cursor = None
    if len(items) > limit:
        items = items[:limit]
        next_cursor = items[-1].created_at.isoformat()

    return APIResponse.ok(
        data=PaginatedResponse.create(
            items=[mapApiMessage(m) for m in items],
            total=total,
            next_cursor=next_cursor,
        )
    )
```

**Source:** TanStack Query documentation [useInfiniteQuery guide](https://tanstack.com/query/v4/docs/framework/react/guides/infinite-queries); verified against project's existing history.py pagination pattern (offset-limit) which can be extended with cursor support.

### Pattern 3: Virtual Scrolling with Dynamic Message Heights

**What:** Use TanStack Virtual with `estimateSize` (initial guess) + `measureElement` (actual size after render) to handle messages of varying heights without layout thrashing.

**When to use:** Lists >500 items, especially chat where message heights vary dramatically (single-line user message vs. 500-line SQL result).

**Example:**

```typescript
// hooks/useMessageVirtualizer.ts (80 lines)
import { useVirtualizer } from "@tanstack/react-virtual";

export function useMessageVirtualizer(messages: ChatMessage[]) {
  const parentRef = useRef<HTMLDivElement>(null);

  const virtualizer = useVirtualizer({
    count: messages.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 100, // Guess: most messages ~100px
    measureElement: typeof window !== "undefined"
      ? (element) => element?.getBoundingClientRect().height
      : undefined,
    overscan: 10, // Render 10 items beyond viewport for smooth scrolling
    scrollMargin: 0,
  });

  // Handle scroll-to-top pagination
  useEffect(() => {
    const handleScroll = () => {
      if (parentRef.current?.scrollTop === 0) {
        loadEarlierMessages();
      }
    };

    parentRef.current?.addEventListener("scroll", handleScroll);
    return () => parentRef.current?.removeEventListener("scroll", handleScroll);
  }, []);

  // Preserve scroll position when messages prepend
  useEffect(() => {
    virtualizer.measure(); // Re-measure after new messages
  }, [messages.length, virtualizer]);

  return { virtualizer, virtualItems: virtualizer.getVirtualItems() };
}
```

**Configuration Details:**
- `estimateSize: 100` — Most messages (user input, short assistant text) ~80–120px. SQL results ~200–400px. Conservative estimate prevents layout shift.
- `measureElement` — After render, `getBoundingClientRect().height` captures actual height including multi-line text, code blocks, charts.
- `overscan: 10` — Render 10 items beyond viewport to smooth rapid scrolling.
- **Scroll position preservation:** TanStack Virtual handles scroll math automatically when items are prepended IF `shouldAdjustScrollPositionOnItemSizeChange` is enabled (default true for v3+).

**Source:** TanStack Virtual documentation [dynamic sizes](https://tanstack.com/virtual/latest/docs/guide/virtualization); GitHub discussion [#1018 scroll preservation](https://github.com/TanStack/virtual/discussions/1018), verified against real chat use case (SQL results, Python output, charts have varying heights).

### Pattern 4: Custom Hooks for Logic Extraction

**What:** Extract complex stateful logic into named custom hooks, reducing component size and enabling reuse.

**When to use:** Any component >120 lines with multiple `useState`/`useEffect` or repeated across components.

**Example:**

```typescript
// hooks/useSchemaLayout.ts (50 lines)
export function useSchemaLayout(connectionId: string | null, selectedLayoutId: string | null) {
  const { nodes, setNodes, edges, setEdges } = useReactFlow();
  const saveTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const saveLayout = useCallback(() => {
    if (!selectedLayoutId || !connectionId) return;

    const snapshot = buildLayoutSnapshot(nodes, getViewport(), schemaInfo?.tables);
    updateLayoutMutation.mutate({ id: selectedLayoutId, data: snapshot.payload });
  }, [selectedLayoutId, connectionId, nodes]);

  const handleNodesChange = useCallback(
    (changes) => {
      onNodesChange(changes);

      if (changes.some((c) => c.type === "position")) {
        clearTimeout(saveTimeoutRef.current!);
        saveTimeoutRef.current = setTimeout(saveLayout, 500);
      }
    },
    [saveLayout]
  );

  return { saveLayout, handleNodesChange };
}
```

**Source:** React Hooks documentation [custom hooks](https://react.dev/learn/reusing-logic-with-custom-hooks); verified against project's existing chat-helpers.ts pattern which exports reusable functions like `applyStreamEvent`, `buildPendingAssistantMessage`.

### Anti-Patterns to Avoid

- **Pass state directly down 7+ levels:** Use Context or custom hooks instead. Project uses Zustand — leverage it.
- **useMemo/useCallback in every function:** Only memoize if dependencies are expensive to compute or prevent child re-renders. In MessageList, only memoize virtual item rendering.
- **fetch data in component, transform, then pass to child:** Extract into custom hook (useMessagePagination) to keep component thin.
- **Virtual scroll without measureElement:** Fixed heights only; dynamic content (SQL, charts, code) will cause layout jump when actual size differs from estimate.
- **Infinite query with useQuery + manual page tracking:** useInfiniteQuery handles deduping, keeps cache aligned. Manual approach leads to duplicate messages or missing pages.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Infinite pagination logic | Manual page tracking with useState, fetchMore logic | useInfiniteQuery + getNextPageParam | Built-in deduping, automatic cursor management, cache invalidation on mutations |
| Virtual scrolling for 1000+ items | Intersection Observer + manual scroll event listeners | TanStack Virtual | Handles scroll math, overscan, dynamic measurement; prevents layout shift and scroll position loss |
| Scroll-to-top pagination trigger | setTimeout + scroll offset tracking | TanStack Virtual's built-in scroll listener | Avoids race conditions, handles scroll momentum on mobile, accounts for dynamic heights |
| Extract scroll position on prepend | Manual ref tracking + useEffect coordination | TanStack Virtual's shouldAdjustScrollPositionOnItemSizeChange | Already solves scroll jump problem; custom logic introduces off-by-one errors |
| Schema layout save throttling | Manual timeout tracking + ref | useCallback + custom hook | Prevents lost updates, easier to test, reusable across components |

**Key insight:** These problems are solved by battle-tested libraries that handle edge cases (scroll momentum, dynamic measurement, duplicate detection) that custom code misses. Manual implementations typically fail on 1000+ items or with varying content heights.

## Common Pitfalls

### Pitfall 1: Virtual Scrolling with Incorrect estimateSize

**What goes wrong:** EstimateSize too high → empty space above/below viewport; estimateSize too low → gaps appear while scrolling. With SQL results (200–400px), initial estimate of 80px causes visible gaps.

**Why it happens:** TanStack Virtual calculates scroll offset based on estimateSize. If actual height differs, scroll position jumps when items render.

**How to avoid:**
1. Analyze message height distribution in AssistantMessageCard (user input ~60px, short text ~80px, SQL result with data table ~300px)
2. Use conservative estimate (100px) — better to overshoot (white space above) than undershoot (visible gaps)
3. Always enable `measureElement` to capture actual heights post-render

**Warning signs:** Scrolling feels jerky, white space appears above/below items as you scroll, scroll position jumps when new messages load.

### Pitfall 2: Prepending Messages Without Scroll Position Preservation

**What goes wrong:** User scrolls to top, pagination loads 50 older messages, list jumps and user loses position. Typical in chat UIs when implementing "load earlier messages."

**Why it happens:** Adding items to DOM array start shifts all existing DOM nodes down. Browser auto-scrolls to keep scroll position, but if estimated heights differ from actual, offset is wrong.

**How to avoid:**
1. TanStack Virtual handles this IF `shouldAdjustScrollPositionOnItemSizeChange: true` (default in v3+)
2. When updating Zustand store with new messages, prepend to messages array: `[...newOldMessages, ...state.messages]`
3. Call `virtualizer.measure()` after prepend to re-compute offsets

**Warning signs:** After loading older messages, scroll jumps to middle of list. User cannot scroll to absolute top.

### Pitfall 3: useInfiniteQuery Duplicate Pages

**What goes wrong:** Same messages appear twice in list. Happens when cursor pagination mixes with offset pagination or pageParam is not unique.

**Why it happens:** Cursor not properly tracked; frontend calls fetchNextPage without waiting for first page to settle.

**How to avoid:**
1. Backend: cursor must be unique and monotonic (ISO datetime of message, or message ID with tie-breaker)
2. Frontend: Don't call fetchNextPage() multiple times without checking `isFetchingPreviousPage`
3. Use select option to flatten pages: `select: (data) => data.pages.flatMap(p => p.messages)`
4. Test with console logs: `console.log(data.pages.map(p => p.messages.map(m => m.id)))`

**Warning signs:** Message appears twice in list. Conversation length doesn't match database count.

### Pitfall 4: Decomposed Components Still Coupled to Zustand

**What goes wrong:** InputBar imports and calls useChatStore directly; MessageList does same. Changes to store signature require edits in 5+ components. Tight coupling.

**Why it happens:** Convenient to import store in each sub-component; requires less prop threading.

**How to avoid:**
1. **ChatArea owns store data, passes as props:** `<MessageList messages={messages} isLoading={isLoading} />`
2. **InputBar receives callback:** `<InputBar onSubmit={handleSubmit} />`
3. Only ChatArea (container) imports useChatStore
4. Sub-components are "pure," accept data as props

**Warning signs:** Refactoring store makes 5+ component files fail TypeScript. Sub-components test in isolation become impossible.

### Pitfall 5: Schema Visualization Re-renders on Every Node Position Change

**What goes wrong:** User drags a table node; entire ReactFlow re-renders (all 100+ nodes recompute). Feels sluggish.

**Why it happens:** State update in SchemaSettings triggers full re-render of SchemaGraph child. ReactFlow nodes array changes reference, nodes array changes trigger all node updates.

**How to avoid:**
1. Memoize nodes/edges separately: `const nodes = useMemo(() => buildSchemaNodes(...), [visibleTables, currentLayout])`
2. Separate handlers: position changes go to onNodesChange (local React state), separate throttled save to updateLayoutMutation
3. Use useCallback for handlers with stable references
4. Defer save to backend (500ms debounce) — don't update Zustand on every drag

**Warning signs:** Dragging a node in schema graph feels laggy. Lots of "Building schema nodes..." logs if you add debug output. React DevTools Profiler shows full component re-render on each mouse move.

### Pitfall 6: Message Pagination Not Respecting Conversation Context

**What goes wrong:** User loads older messages; context window is set to 5 rounds. LLM only sees last 5 assistant messages, ignores loaded older history.

**Why it happens:** ExecutionService in backend defaults context_rounds to recent messages. Message pagination is UI-only; backend doesn't know older messages exist.

**How to avoid:**
1. Context window is for LLM ("last N assistant messages"), not for pagination
2. Pagination is for chat history UI ("load earlier messages to read")
3. They are independent: user can scroll to see 100 old messages, but LLM only gets context_rounds
4. Document this in hook: `useMessagePagination` is for UI scrollback, not LLM context

**Warning signs:** User confused why scrolling old messages doesn't improve LLM answers. Thinking this phase solves "too much context" problem when it doesn't.

## Code Examples

Verified patterns from official sources:

### useInfiniteQuery for Message Pagination

```typescript
// Source: https://tanstack.com/query/v4/docs/framework/react/guides/infinite-queries
import { useInfiniteQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";

export function useMessagePagination(conversationId: string | null) {
  return useInfiniteQuery({
    queryKey: ["messages", conversationId],
    queryFn: async ({ pageParam }) => {
      if (!conversationId) return { messages: [], nextCursor: null };
      const response = await api.get(
        `/api/v1/conversations/${conversationId}/messages`,
        {
          params: {
            cursor: pageParam,
            limit: 50,
          },
        }
      );
      return response.data.data;
    },
    initialPageParam: null,
    getNextPageParam: (lastPage) => lastPage.next_cursor,
    select: (data) => data.pages.flatMap((page) => page.messages),
  });
}
```

### TanStack Virtual with Dynamic Heights

```typescript
// Source: https://tanstack.com/virtual/latest/docs/api/virtualizer
import { useVirtualizer } from "@tanstack/react-virtual";

export function useMessageVirtualizer(messages: ChatMessage[]) {
  const parentRef = useRef<HTMLDivElement>(null);

  const virtualizer = useVirtualizer({
    count: messages.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 100,
    measureElement:
      typeof window !== "undefined"
        ? (element) => element?.getBoundingClientRect().height
        : undefined,
    overscan: 10,
  });

  return {
    parentRef,
    virtualizer,
    virtualItems: virtualizer.getVirtualItems(),
  };
}
```

### Custom Hook for Complex State Logic

```typescript
// Source: https://react.dev/learn/reusing-logic-with-custom-hooks
export function useSchemaLayout(
  connectionId: string | null,
  selectedLayoutId: string | null
) {
  const [nodes, setNodes] = useState<Node[]>([]);
  const [saveTimeout, setSaveTimeout] = useState<NodeJS.Timeout | null>(null);
  const { mutate: updateLayout } = useMutation({
    mutationFn: ({ id, data }: { id: string; data: any }) =>
      api.put(`/api/v1/schema/${connectionId}/layouts/${id}`, data),
  });

  const saveLayout = useCallback(() => {
    if (!selectedLayoutId || !connectionId) return;
    const snapshot = buildLayoutSnapshot(nodes);
    updateLayout({ id: selectedLayoutId, data: snapshot });
  }, [selectedLayoutId, connectionId, nodes, updateLayout]);

  const handleNodesChange = useCallback(
    (changes: NodeChange[]) => {
      setNodes((prev) => applyNodeChanges(changes, prev));
      if (saveTimeout) clearTimeout(saveTimeout);
      setSaveTimeout(
        setTimeout(() => {
          saveLayout();
        }, 500)
      );
    },
    [saveLayout, saveTimeout]
  );

  return { nodes, setNodes, handleNodesChange, saveLayout };
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Fixed-height virtual scrolling (react-window) | Dynamic measurement (TanStack Virtual v3+) | 2023–2024 | Messages with SQL results, code blocks, charts no longer cause layout jump |
| Manual infinite scroll (useEffect + scroll listener) | useInfiniteQuery with getNextPageParam | 2020–2021 | Reduced bugs: automatic deduping, cursor management, cache alignment |
| Context window optimization (PERF-02) | Deferred to v2 roadmap | Current | Focus on pagination UI; context rounds are LLM concern, separate from scrollback |
| Component sprawl (monolithic ChatArea) | Functional decomposition + custom hooks | 2023+ React community standard | Easier testing, reuse, maintenance; Phase 2 implements this |

**Deprecated/outdated:**
- **react-window for dynamic heights:** Use TanStack Virtual instead. react-window forces fixed heights; any variation requires manual height caching.
- **Manual scroll tracking for pagination:** useInfiniteQuery handles pageParam, deduping. Manual tracking with useEffect is error-prone.
- **Prop drilling vs Context:** Zustand already chosen; custom hooks > Context for this codebase since it avoids provider nesting.

## Environment Availability

**Skip status:** All dependencies are npm-installed or already available. No external services (databases, APIs) beyond backend already running. No fallback strategy needed.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Node.js | Build & runtime | ✓ | 18.20.7 (verified via env) | — |
| npm | Package installation | ✓ | 10.x (implied) | — |
| TypeScript | Type checking | ✓ | 5.6+ (confirmed package.json) | — |
| Vitest | Test execution | ✓ | 4.0.15 (confirmed package.json) | — |
| @tanstack/react-query | useInfiniteQuery | ✓ | 5.50.0 (confirmed package.json) | — |
| @tanstack/react-virtual | Virtual scrolling | ✗ | — | Must install (npm install @tanstack/react-virtual@^3.0.0) |
| Zustand | State management | ✓ | 5.0.0 (confirmed package.json) | — |

**Missing dependencies with no fallback:**
- @tanstack/react-virtual: Must be installed before implementing virtual scrolling (Phase 2 Wave 1, Task 1)

## Open Questions

1. **Scroll-to-bottom behavior with virtual scrolling**
   - What we know: TanStack Virtual preserves scroll position when items prepend (scroll-to-top load). For new messages arriving, need to auto-scroll to bottom.
   - What's unclear: Should auto-scroll-to-bottom trigger only if user was already at bottom? Or always?
   - Recommendation: Implement as Zustand side effect: `if (messages length increased AND wasScrolledToBottom) { scroll to bottom }`

2. **AssistantMessageCard remains ~288 lines**
   - What we know: FRONT-01 targets ChatArea decomposition, not AssistantMessageCard. It's a specialized display component.
   - What's unclear: Should it be further decomposed (TabsHeader, TabContent sub-components)?
   - Recommendation: Keep as-is for Phase 2. If it causes issues in Phase 4+, break into sub-components then.

3. **Backward compatibility for messages without created_at?**
   - What we know: Cursor pagination uses Message.created_at as cursor
   - What's unclear: Do old messages in database have valid created_at? Any migration needed?
   - Recommendation: Verify during Wave 1; if null values exist, add migration or filter them out

4. **How many messages is "large conversation"?**
   - What we know: Success criteria is 1000+ messages at 60 FPS
   - What's unclear: What's typical? Should pagination load 50 or 100 messages?
   - Recommendation: D-06 says 50 messages per page. Measure load time; adjust if needed.

## Sources

### Primary (HIGH confidence)
- **TanStack Query v5.50.0 documentation** — [useInfiniteQuery guide](https://tanstack.com/query/v4/docs/framework/react/guides/infinite-queries), pagination patterns verified
- **TanStack Virtual documentation** — [virtualization guide](https://tanstack.com/virtual/latest/docs/guide/virtualization), dynamic measurement approach confirmed
- **React documentation** — [custom hooks](https://react.dev/learn/reusing-logic-with-custom-hooks), [thinking in React](https://react.dev/learn/thinking-in-react), component decomposition patterns
- **Project codebase analysis** — ChatArea (408 lines), SchemaSettings (618 lines), chat.ts (Zustand store), history.py (pagination pattern), vitest.config.ts (testing setup)

### Secondary (MEDIUM confidence)
- **TanStack Virtual GitHub discussions** — [scroll preservation #1018](https://github.com/TanStack/virtual/discussions/1018), [dynamic heights #1017](https://github.com/TanStack/virtual/discussions/1017) — community-verified patterns for chat UIs
- **Medium articles** — [Pagination with useInfiniteQuery](https://medium.com/@lakshaykapoor08/%EF%B8%8F-caching-pagination-and-infinite-scrolling-with-tanstack-query-4212b24d3806), [React component decomposition](https://medium.com/dailyjs/techniques-for-decomposing-react-components-e8a1081ef5da) — verified against React best practices

### Tertiary (LOW confidence)
- None — all recommendations grounded in official docs or project code

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — @tanstack/react-query 5.50.0 confirmed; @tanstack/react-virtual v3.0+ standard for virtual scrolling; Zustand 5.0.0 confirmed
- Architecture: HIGH — Current code analyzed; decomposition patterns from official React docs; TanStack patterns from official docs + community discussions
- Pitfalls: MEDIUM-HIGH — Pitfalls based on GitHub issues, real chat app implementations, verified against AssistantMessageCard complexity (288 lines, multiple tabs, SQL results, charts)

**Research date:** 2026-03-30
**Valid until:** 2026-05-01 (TanStack libraries evolve quickly; re-verify if >4 weeks pass)

---

*Phase: 02-frontend-component-optimization*
*Research completed: 2026-03-30*
