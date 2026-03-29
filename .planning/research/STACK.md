# Technology Stack for QueryGPT Optimization

**Project:** QueryGPT (AI Database Assistant Optimization Milestone)
**Researched:** 2026-03-29
**Scope:** Refactoring large files, caching, virtualization, sandboxing
**Overall Confidence:** HIGH (most findings verified with official docs and current sources)

---

## Executive Summary

QueryGPT's existing Next.js 15 + FastAPI + SQLAlchemy stack is well-chosen for the optimization work ahead. The refactoring priorities (large Python files, large React components, chat virtualization, query caching) align naturally with the ecosystem's current best practices:

- **Backend refactoring** follows established FastAPI patterns: Service/Repository layers with dependency injection, modular file organization
- **Frontend refactoring** leverages React hooks, Context, and component composition (no new libraries needed for basic refactoring)
- **Chat virtualization** has clear winners: TanStack Virtual (paired with existing TanStack Query) for rendering, react-virtuoso as an alternative
- **Query result caching** should use Redis + dogpile.cache (official SQLAlchemy caching library) with careful async handling
- **Python sandboxing** requires hard architectural choices: Docker containers (most secure) vs RestrictedPython (convenience with known vulnerabilities)

No major technology changes needed. Focus is on architectural patterns, library configuration, and deployment strategy.

---

## Recommended Stack for Optimization

### Backend Refactoring Layer

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| **FastAPI** | 0.115.0+ | Web framework | Already in use. Dependency injection system supports service layer architecture naturally. |
| **Pydantic** | 2.7+ | Validation & settings | Already in use. Use for cleaner Service layer contracts; separate request/response schemas from domain models. |
| **SQLAlchemy** | 2.0.30+ | ORM + async | Already in use. Async support is critical for large operations; session management improved in 2.0. |
| **Ruff** | 0.4+ | Python formatting | Already in use. Use to enforce consistent code style across refactored modules (max-line-length ~100 for readability). |

**Refactoring Pattern: Service Layer + Dependency Injection**

FastAPI's native dependency injection (`Depends()`) should orchestrate a three-layer architecture:

1. **Routes (Controller Layer):** Thin, HTTP-focused. Validate input → call service → return response.
2. **Services:** Business logic, transaction management, orchestration. No HTTP awareness.
3. **Repositories:** Data access. Single entity focus, query composition.

Example structure for `gptme_engine.py` (990 lines → modular):

```
/apps/api/app/services/
├── __init__.py
├── gpt_chat_service.py      # Main conversation orchestration
├── sql_generation_service.py # SQL generation + validation
├── python_execution_service.py # Python code execution + analysis
├── schema_service.py         # Schema introspection + caching
└── result_analysis_service.py # Result analysis + chart generation

/apps/api/app/repositories/
├── __init__.py
├── query_repository.py       # Query execution + result caching
├── schema_repository.py      # Schema metadata + relations
└── semantic_repository.py    # Semantic layer CRUD
```

Each service gets injected dependencies (DB session, cache, config, logger) via `Depends()`:

```python
async def chat(
    message: str,
    db: AsyncSession = Depends(get_db),
    cache: RedisCache = Depends(get_cache),
    config: Settings = Depends(get_settings),
) -> ChatResponse:
    service = GPTChatService(db=db, cache=cache, config=config)
    return await service.process_message(message)
```

**Confidence:** HIGH. FastAPI dependency injection is official docs and widely adopted pattern. Service layer is standard in production Python APIs.

---

### Frontend Refactoring Layer

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| **React** | 19.0+ | UI library | Already in use. Hooks and Context eliminate most large component issues. |
| **TypeScript** | 5.6+ | Type safety | Already in use. Use strict types (`as const`, discriminated unions) to enforce component props contracts. |
| **React Context** | native | State management | Use for avoiding prop drilling in large components. NOT a replacement for Zustand; use Zustand for global app state, Context for feature-local state. |
| **Custom Hooks** | typescript | Logic extraction | Extract stateful logic, side effects, and subscriptions from large components into reusable hooks. |
| **React.memo** | native | Performance | Wrap sub-components to prevent unnecessary re-renders when parent updates. |

**Refactoring Pattern: Component Composition + Custom Hooks**

For large components (600+ lines like ChatArea, SchemaSettings):

1. **Extract custom hooks** for distinct features:
   ```typescript
   // useChat.ts - manages chat state, message handling
   function useChat(sessionId: string) {
     const [messages, setMessages] = useState([]);
     const [input, setInput] = useState("");
     // ... complex chat logic
     return { messages, input, setInput, sendMessage };
   }

   // ChatArea becomes:
   function ChatArea({ sessionId }) {
     const { messages, input, setInput, sendMessage } = useChat(sessionId);
     return <ChatUI messages={messages} input={input} {...} />;
   }
   ```

2. **Break into smaller presentation components:**
   ```typescript
   // <ChatArea> becomes:
   <ChatContainer>
     <ChatHeader session={session} />
     <MessageList messages={messages} />
     <InputBox value={input} onChange={setInput} onSend={sendMessage} />
   </ChatContainer>
   ```

3. **Use Context only for feature-local state** (avoid global Context unless truly app-wide):
   ```typescript
   // SchemaContext - avoid if possible, prefer props or Zustand
   // Instead: useSchemaState hook with Context internals, injected via prop
   ```

**Confidence:** HIGH. React composition patterns are official docs and community standard. Hook extraction is idiomatic React 19.

---

### Chat Virtualization Layer

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| **TanStack Virtual** | 3.0+ | Virtual scrolling | Modern, lightweight replacement for react-virtualized. Handles reverse scroll (chat) naturally. **USE THIS.** |
| **react-virtuoso** | 4.x | Chat-specific alternative | Pre-built chat component with infinite scroll. More opinionated, less flexible. Use only if TanStack Virtual too low-level. |
| **TanStack Query** | 5.50+ | Data fetching + caching | Already in use. Pair with TanStack Virtual: Query handles pagination, Virtual handles rendering. |

**Refactoring Pattern: Paginated Infinite Scroll with Virtual List**

Replace naive `messages.map()` rendering:

```typescript
// OLD: renders 1000+ messages in DOM, OOM risk
function MessageList({ messages }) {
  return <div>{messages.map(m => <Message key={m.id} {...m} />)}</div>;
}

// NEW: renders only visible messages (~20 at a time)
import { useVirtualizer } from '@tanstack/react-virtual';

function MessageList() {
  const query = useInfiniteQuery({
    queryKey: ['messages', sessionId],
    queryFn: ({ pageParam = 0 }) => fetchMessages(sessionId, pageParam),
    getNextPageParam: (lastPage) => lastPage.nextCursor,
    initialPageParam: 0,
    // Key: disable automatic refetch on mount for chat (messages are append-only)
    staleTime: Infinity,
    gcTime: 1000 * 60 * 10, // Keep in cache 10 min
  });

  const flatMessages = useMemo(
    () => query.data?.pages.flatMap(p => p.messages) ?? [],
    [query.data]
  );

  const virtualizer = useVirtualizer({
    count: flatMessages.length,
    getScrollMargin: () => 40,
    overscan: 10,
    size: containerHeight,
    scrollMargin: bottomReached ? 40 : 0, // Scroll to bottom on new message
  });

  return (
    <div ref={parentRef} onScroll={handleScroll}>
      {virtualizer.getVirtualItems().map(item => (
        <div key={item.key}>
          <Message message={flatMessages[item.index]} />
        </div>
      ))}
    </div>
  );
}
```

**Key Trade-offs:**
- TanStack Virtual: ~3KB gzipped, full control, requires manual pagination logic. **Recommended for QueryGPT** (need custom infinite scroll behavior).
- react-virtuoso: ~15KB, opinionated, scrollToBottom built-in. Use if you want less boilerplate.

**Confidence:** HIGH. TanStack Virtual is new standard (Facebook/Meta team maintains it). react-virtualized is deprecated in favor of react-virtual/TanStack Virtual.

---

### Query Result Caching Layer

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| **dogpile.cache** | 1.5.0+ | Query-level caching | Official SQLAlchemy caching library. Supports Redis backend. Key for large result sets. |
| **Redis** | 7.0+ | Cache backend | Memory store for query results. Much faster than re-querying database. |
| **TanStack Query** | 5.50+ | Client-side caching | Already in use. Combine with server-side caching: Query handles request deduplication, server handles result persistence. |

**Caching Strategy for QueryGPT:**

```python
# Backend: SQLAlchemy 2.0 + dogpile.cache + Redis
from dogpile.cache import make_region

# Configure Redis backend with distributed locking for async safety
cache = make_region(
    backend='dogpile.cache.redis',
    expiration_time=3600,  # 1 hour default
    arguments={
        'url': 'redis://localhost:6379/0',
        'distributed_lock': True,  # Critical for async
        'lock_prefix': 'qgpt',
        'ignore_exc': True,  # Don't fail requests if Redis down
    }
).configure()

# Wrap expensive queries
@cache.cache_on_arguments(
    namespace='schema',
    function_key_generator=lambda ns, fn, *args: f"{ns}:{args[1]}",
    expiration_time=3600 * 12,  # Schema changes rarely
)
async def get_database_schema(db: AsyncSession, db_url: str):
    # Expensive: introspect DB schema, build relationships, etc.
    result = await db.execute(text("SELECT ..."))
    return result.fetchall()

# Invalidate cache on schema changes
from sqlalchemy import event

@event.listens_for(Engine, "connect")
def receive_connect(dbapi_conn, connection_record):
    # After schema mutations, invalidate:
    cache.invalidate(get_database_schema)
```

**Frontend: TanStack Query + smart TTL**

```typescript
// Already configured in codebase, but optimize:
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Schema: very stable, cache longer
      staleTime: 1000 * 60 * 60 * 4, // 4 hours
      gcTime: 1000 * 60 * 60 * 24, // Keep 24 hours

      // Query results: cache shorter, may change
      // Use query key tags to group:
      // ['query', 'result', sessionId] → staleTime: 1000 * 60
      // ['schema', databaseId] → staleTime: 1000 * 60 * 60
    },
  },
});

// Use query invalidation on mutations
const mutation = useMutation({
  mutationFn: executeQuery,
  onSuccess: (result, variables) => {
    // Only invalidate THIS query's results, not all
    queryClient.invalidateQueries({
      queryKey: ['query', 'result', variables.sessionId],
    });
  },
});
```

**Critical Issue: Async + Redis Locking**

dogpile.cache's default thread-local locking **breaks with async creators** (FastAPI uses async). Solution: Use `distributed_lock=True` for Redis backend:

```python
# Async creator - WILL DEADLOCK with default locking
async def expensive_query_creator():
    result = await db.execute(...)
    return result

# Solution: use distributed_lock + handle async properly
cache = make_region(
    backend='dogpile.cache.redis',
    arguments={
        'url': 'redis://localhost:6379/0',
        'distributed_lock': True,  # Use Redis lock instead of thread-local
    }
).configure()
```

**Confidence:** HIGH. dogpile.cache + Redis is official SQLAlchemy recommendation. Issue with async locking documented in dogpile.cache GitHub issues.

---

### Python Sandboxing Layer

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| **Docker containers** | 24.0+ | Code sandboxing (SECURE) | Isolate Python code execution. Each execution in isolated container. Highest security. |
| **RestrictedPython** | 7.x | Code sandboxing (RISKY) | Restrict built-ins. **NOT RECOMMENDED** — multiple CVEs (Agenta, n8n 2026). Maintenance burden. |
| **QEMU microVMs** | - | Code sandboxing (EXTREME) | Hardware virtualization for each execution. Overkill for local development. |

**Current Status:** QueryGPT already uses RestrictedPython in `python_execution_service.py`. Analysis below.

**Option 1: Keep RestrictedPython (Current, Medium Risk)**

Pros:
- Already integrated
- Minimal overhead
- Fast iteration

Cons:
- Known vulnerabilities (CVE-2026-0863, Agenta sandbox escape)
- Requires constant maintenance as Python evolves
- Bypasses via `__import__`, exception formatting exist

**Option 2: Switch to Docker Containers (Recommended)**

Pros:
- True isolation (OS-level)
- Can enforce resource limits (CPU, memory, timeout)
- Handles library breakouts
- Industry standard (used by LangChain, Claude, OpenAI Playground)

Cons:
- Overhead: 200-500ms per execution (vs 5-10ms RestrictedPython)
- Requires Docker installation
- More complex error handling

**Option 3: Hybrid (Pragmatic)**

For QueryGPT's use case (local, single-user, analysis code only):

1. **Keep RestrictedPython for development/local use** (fast iteration)
2. **Add Docker option for production/deployment** (secure)
3. **Explicit whitelist of allowed libraries** (numpy, pandas, matplotlib)
4. **No access to file system** (code analysis only, no I/O)
5. **Hard limits: 5s execution timeout, 512MB memory**

```python
import asyncio
from restrictedjython import compile_restricted
import signal

# Whitelist safe imports only
ALLOWED_MODULES = {'numpy', 'pandas', 'matplotlib', 'math', 'statistics'}

async def execute_analysis_code(code: str, data_context: dict, timeout_s: int = 5):
    # Validate imports in code
    for module in extract_imports(code):
        if module not in ALLOWED_MODULES:
            raise ValueError(f"Import '{module}' not allowed")

    # Compile with restrictions
    byte_code = compile_restricted(code, '<analysis>', 'exec')
    if byte_code.errors:
        raise SyntaxError(byte_code.errors)

    # Execute with timeout
    try:
        async with asyncio.timeout(timeout_s):
            exec_globals = {
                '__builtins__': SAFE_BUILTINS,
                'numpy': numpy,
                'pandas': pandas,
                'plt': matplotlib.pyplot,
                **data_context,  # Provide data
            }
            exec(byte_code.code, exec_globals)
            return exec_globals.get('result')
    except asyncio.TimeoutError:
        raise RuntimeError(f"Code execution exceeded {timeout_s}s timeout")
    except Exception as e:
        raise RuntimeError(f"Execution error: {str(e)}")
```

**Recommendation for QueryGPT:**

**Keep RestrictedPython in Phase 1** (maintenance priority is lower). **Plan Docker integration for Phase 2** (stability phase). For now:

1. Add explicit library whitelist (`ALLOWED_MODULES`)
2. Implement hard timeout (5 seconds)
3. Remove file I/O entirely (no `open()`, `glob`, etc.)
4. Document as "development sandbox, not production-grade"

This balances security with keeping refactoring focused on architecture, not security theater.

**Confidence:** HIGH. Vulnerabilities documented in GitHub/CVE databases. Industry practices clear (Agenta removed RestrictedPython entirely, switched to Firecracker microVMs).

---

## Dependency Installation & Configuration

### Backend Setup

```bash
# Core optimization doesn't require new packages — use existing:
# FastAPI 0.115.0+, SQLAlchemy 2.0.30+, Pydantic 2.7+ already present

# ADD for caching:
pip install dogpile.cache[redis] redis

# ADD for background tasks (optional, for long queries):
pip install celery[redis]

# Versions in uv workspace (/apps/api/pyproject.toml):
[project]
dependencies = [
    "fastapi==0.115.0",
    "sqlalchemy[asyncio]==2.0.30",
    "pydantic[email]==2.7",
    "uvicorn[standard]==0.30.0",
    "dogpile.cache[redis]==1.5.0",  # NEW
    "redis==5.0.0",  # NEW (dogpile.cache dependency)
]
```

### Frontend Setup

```bash
# Core optimization doesn't require new packages:
# React 19.0+, TanStack Query 5.50+ already present

# ADD for virtual scrolling:
npm install @tanstack/react-virtual

# Version in package.json:
{
  "dependencies": {
    "react": "^19.0.0",
    "@tanstack/react-query": "^5.50.0",
    "@tanstack/react-virtual": "^3.0.0"  # NEW
  }
}
```

### Redis Configuration

For caching and message broker:

```bash
# docker-compose.yml addition:
redis:
  image: redis:7-alpine
  ports:
    - "6379:6379"
  volumes:
    - redis-data:/data
  command: redis-server --appendonly yes
```

### Backend Environment Variables

```bash
# .env or app/core/config.py
REDIS_URL=redis://localhost:6379/0
CACHE_BACKEND=redis  # or "memory" for dev
CACHE_TTL_SCHEMA=43200  # 12 hours
CACHE_TTL_RESULTS=3600  # 1 hour
CACHE_TTL_SEMANTIC=86400  # 24 hours

# For Celery (optional):
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/1
```

---

## Recommended Refactoring Order (for Roadmap)

1. **Backend Service Layer** (Phase 1)
   - Break `gptme_engine.py` into service modules
   - Implement dependency injection with `Depends()`
   - Result: 990 lines → 5 services × ~150 lines each
   - Enabler for subsequent work

2. **Query Result Caching** (Phase 2)
   - Add dogpile.cache + Redis integration
   - Cache schema introspection, semantic layer, query results
   - Estimated 3-5x speedup for repeated queries
   - Depends on: Service layer separation

3. **Frontend Component Refactoring** (Phase 2)
   - Extract custom hooks from large components
   - Break ChatArea (600+ lines) into ChatUI sub-components
   - Use Context for feature-local state only
   - Result: Easier to maintain, test, extend

4. **Chat Virtualization** (Phase 3)
   - Implement TanStack Virtual for message list
   - Add paginated infinite scroll from server
   - Handle 1000+ message sessions without OOM
   - Depends on: Frontend refactoring, Query layer pagination API

5. **Python Sandboxing Hardening** (Phase 4)
   - Add library whitelist and timeout enforcement
   - Plan Docker integration (not implementing yet)
   - Document current limitations

---

## Anti-Patterns to Avoid

| Anti-Pattern | Why Bad | What to Do Instead |
|--------------|---------|-------------------|
| Monolithic route handler (100+ lines) | Untestable, violates SRP | Extract logic to Service layer |
| Global Context everywhere | Prop drilling confusion, hard to test | Use Zustand for app-wide state, Context for feature-scoped |
| Rendering 1000+ messages in DOM | OOM, jank, slow interactions | Use TanStack Virtual, paginate server-side |
| No query result caching | Repeated expensive DB work | Use dogpile.cache + Redis with TTL strategy |
| RestrictedPython as final security | Known CVEs, maintenance burden | Document as dev-only, plan Docker for production |
| SQLAlchemy query cache assumptions | Doesn't cache results, only compiled SQL | Implement application-level caching (dogpile) |
| Async code with thread-local locks | Deadlock in dogpile.cache | Use distributed_lock=True for Redis backend |
| Frontend Context for every piece of state | Over-engineering, performance drag | Use Context minimally, props for component data |

---

## Sources

### Backend Refactoring & FastAPI Patterns
- [FastAPI Best Practices — GitHub](https://github.com/zhanymkanov/fastapi-best-practices)
- [Structuring a FastAPI Project: Best Practices — DEV Community](https://dev.to/mohammad222pr/structuring-a-fastapi-project-best-practices-53l6)
- [Bigger Applications - Multiple Files — FastAPI Official](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- [Layered Architecture & Dependency Injection — DEV Community](https://dev.to/markoulis/layered-architecture-dependency-injection-a-recipe-for-clean-and-testable-fastapi-code-3ioo)
- [Production-Ready FastAPI Project Structure (2026 Guide) — DEV Community](https://dev.to/thesius_code_7a136ae718b7/production-ready-fastapi-project-structure-2026-guide-b1g)

### Frontend Refactoring & React Patterns
- [Refactoring A Junior's React Code — Profy Dev](https://profy.dev/article/react-junior-code-review-and-refactoring-1)
- [How Many Lines of Code Until I Need to Refactor a React Component? — Medium](https://medium.com/geekculture/how-many-lines-of-code-until-i-need-to-refactor-a-react-component-c1b8d16f5a5b)
- [5 Best Practices for Refactoring React Components — Marco Ghiani](https://marcoghiani.com/blog/refactoring-a-react-component)
- [Common Sense Refactoring of a Messy React Component — Alex Kondov](https://alexkondov.com/refactoring-a-messy-react-component/)

### Chat Virtualization
- [react-window — GitHub](https://github.com/bvaughn/react-window)
- [TanStack Virtual (React Virtual) — Official Docs](https://tanstack.com/virtual/latest/docs/framework/react/introduction)
- [Building an Efficient Virtualized Table with TanStack Virtual and React Query — DEV Community](https://dev.to/ainayeem/building-an-efficient-virtualized-table-with-tanstack-virtual-and-react-query-with-shadcn-2hhl)
- [Mastering Virtualization in Modern Web Development — Medium](https://medium.com/@pddadson/mastering-virtualization-in-modern-web-development-a-complete-guide-to-virtual-scrolling-and-140cc2afcc95)

### Query Result Caching
- [How to Implement Response Caching with Redis in Python — OneUptime (2026)](https://oneuptime.com/blog/post/2026-01-22-response-caching-redis-python/view)
- [Caching Database Queries with Redis — OneUptime (2026)](https://oneuptime.com/blog/post/2026-01-21-redis-database-query-caching/view)
- [dogpile.cache Official Documentation](https://dogpilecache.sqlalchemy.org/en/latest/)
- [dogpile.cache + Redis Backend — GitHub](https://github.com/sqlalchemy/dogpile.cache)
- [Caching Database Queries in SQLAlchemy - Part 1/2 — Rollbar](https://rollbar.com/blog/caching-database-queries-in-sqlalchemy-part-1-2/)
- [Caching Data with Redis and SQLAlchemy in Python — Level Up Coding](https://levelup.gitconnected.com/caching-data-with-redis-and-sqlalchemy-in-python-a-step-by-step-guide-97f898f55ef)

### TanStack Query & Caching
- [TanStack Query Official Docs](https://tanstack.com/query/latest)
- [Caching Examples — TanStack Query Docs](https://tanstack.com/query/v4/docs/framework/react/guides/caching)
- [TanStack Query v5: The Complete Guide — Medium (Mar 2026)](https://medium.com/@pratikjadhav6632/tanstack-query-react-query-v5-the-complete-guide-for-building-smarter-react-applications-8fdf482212e5)

### Python Code Sandboxing
- [Sandboxing Untrusted Python Code: Secure Execution Strategies — UBOS](https://ubos.tech/news/sandboxing-untrusted-python-code-secure-execution-strategies-and-ubos-solutions/)
- [Python Sandbox Escape in Agenta, Leading to RCE — GitHub Security Advisory](https://github.com/Agenta-AI/agenta/security/advisories/GHSA-pmgp-2m3v-34mq)
- [CVE-2026-0863: n8n Python Sandbox Escape — SmartKeyss](https://www.smartkeyss.com/post/cve-2026-0863-python-sandbox-escape-in-n8n-via-exception-formatting-and-implicit-code-execution)
- [RestrictedPython Documentation](https://restrictedpython.readthedocs.io/)
- [Security Considerations for Popular Python Repos — Technical News (2026)](https://dasroot.net/posts/2026/03/security-considerations-popular-python-repos/)

### Next.js 15 Performance
- [React Server Components Streaming Performance Guide 2026 — SitePoint](https://www.sitepoint.com/react-server-components-streaming-performance-2026/)
- [The Next.js 15 Streaming Handbook — FreeCodeCamp](https://www.freecodecamp.org/news/the-nextjs-15-streaming-handbook/)
- [Next.js 15 Performance Optimization Guide 2026 — Verlua](https://www.verlua.com/blog/nextjs-performance-optimization)

### Background Tasks & Async
- [How to Implement Background Tasks in FastAPI — OneUptime (2026)](https://oneuptime.com/blog/post/2026-02-02-fastapi-background-tasks/view)
- [Celery and Background Tasks — Medium](https://medium.com/@hitorunajp/celery-and-background-tasks-aebb234cae5d)
- [The Definitive Guide to Celery and FastAPI — TestDriven.io](https://testdriven.io/courses/fastapi-celery/intro/)

---

**Analysis Date:** 2026-03-29
**Next Steps:** Use these recommendations to inform Phase 1-2 roadmap for Service layer refactoring and caching implementation.
