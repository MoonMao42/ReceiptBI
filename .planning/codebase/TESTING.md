# Testing Patterns

**Analysis Date:** 2026-03-29

## Test Framework

**Runner:**
- Vitest 4.0.15
- Config: `vitest.config.ts`

**Assertion Library:**
- Vitest built-in assertion functions (imported from `vitest`)
- `@testing-library/jest-dom` for DOM assertions
- `@testing-library/react` for component testing utilities

**Run Commands:**
```bash
npm run test              # Run all tests once
npm run test:watch       # Watch mode - rerun tests on file change
npm run test:coverage    # Run tests with coverage report
npm run test:e2e         # Run Playwright E2E tests
```

## Test File Organization

**Location:**
- Unit tests: co-located in `/tests/` directory at project root
- E2E tests: separate `/e2e/` directory
- Pattern: Test files live separately from source, not co-located with components

**Naming:**
- Unit tests: `*.test.ts` (e.g., `utils.test.ts`, `chat-helpers.test.ts`)
- E2E tests: `*.spec.ts` (e.g., `settings-chat.smoke.spec.ts`)

**Structure:**
```
/Users/maokaiyue/QueryGPT/apps/web/
├── tests/
│   ├── setup.ts                    # Global test setup
│   ├── utils.test.ts
│   ├── chat-helpers.test.ts
│   └── settings-helpers.test.ts
├── e2e/
│   └── settings-chat.smoke.spec.ts
└── vitest.config.ts
```

## Test Structure

**Suite Organization:**
```typescript
import { describe, it, expect } from "vitest";

describe("chat helpers", () => {
  it("dedupes diagnostics by attempt, phase, status, and message", () => {
    // Arrange
    const diagnostics = mergeDiagnostics([...], [...]);

    // Assert
    expect(diagnostics).toEqual([...]);
  });

  it("applies progress and result events to the pending assistant message", () => {
    const progressMessages = applyStreamEvent(buildMessages(), {...});
    const resultMessages = applyStreamEvent(progressMessages, {...});

    expect(resultMessages[1]).toMatchObject({...});
  });
});
```

**Patterns:**
- `describe()` blocks group related tests by function/feature
- `it()` blocks describe individual test cases with descriptive names
- Test names follow pattern: "should [expected behavior]" or "[verb] [subject]"
- Three-part structure: Arrange → Act → Assert (implicit, not always commented)
- Helper functions used to build test data (e.g., `buildMessages()`)
- Multiple assertions per test when testing related outputs

## Mocking

**Framework:** Vitest's built-in `vi` mock utilities

**Patterns:**

Global module mocks in `setup.ts`:
```typescript
import { vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
  }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
}));

// Mock browser APIs
const localStorageMock = {
  getItem: vi.fn(),
  setItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn(),
};
Object.defineProperty(window, "localStorage", { value: localStorageMock });

// Mock matchMedia for responsive tests
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: vi.fn().mockImplementation((query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});
```

**What to Mock:**
- Browser APIs: `localStorage`, `matchMedia`, `fetch`
- Next.js hooks: `useRouter`, `usePathname`, `useSearchParams`
- External dependencies that require configuration

**What NOT to Mock:**
- Pure utility functions (test the real implementations)
- Type definitions and interfaces
- Helper functions like `applyStreamEvent`, `mergeDiagnostics` (test actual behavior)

## Fixtures and Factories

**Test Data:**
Helper function pattern used in test files:
```typescript
// From chat-helpers.test.ts
function buildMessages(): ChatMessage[] {
  return [
    { role: "user", content: "show sales" },
    buildPendingAssistantMessage()
  ];
}

// From settings-helpers.test.ts - using actual builder functions from source
const formData = buildModelFormData({
  id: "m1",
  name: "Claude",
  provider: "anthropic",
  // ... form data
});
```

**Pattern:**
- Reuse builder functions from production code when available (e.g., `buildPendingAssistantMessage()`)
- Create minimal helper functions for common test data setup
- Use actual types from source code for test data

**Location:**
- Fixture data defined in test files directly, usually as helper functions
- No separate fixtures directory

## Coverage

**Requirements:** Not enforced (no coverage thresholds in config)

**View Coverage:**
```bash
npm run test:coverage
```

Coverage configuration in `vitest.config.ts`:
```typescript
coverage: {
  provider: "v8",
  reporter: ["text", "json", "html"],
  include: ["src/**/*.{ts,tsx}"],
  exclude: ["src/**/*.d.ts"],
}
```

- V8 provider for coverage analysis
- Reports generated in text, JSON, and HTML formats
- Covers all TypeScript source files except type definitions

## Test Types

**Unit Tests:**
- Scope: Individual utility functions and helpers
- Approach: Direct function invocation with test data
- Examples:
  - `getErrorMessage()` type narrowing tests in `utils.test.ts`
  - `mergeDiagnostics()` deduplication in `chat-helpers.test.ts`
  - Form data builders in `settings-helpers.test.ts`

**Integration Tests:**
- Scope: Multiple functions working together
- Approach: Build messages through sequence of function calls, verify accumulated state
- Example from `chat-helpers.test.ts`:
  ```typescript
  it("applies progress and result events to the pending assistant message", () => {
    const progressMessages = applyStreamEvent(buildMessages(), {
      type: "progress",
      data: { ... }
    });
    const resultMessages = applyStreamEvent(progressMessages, {
      type: "result",
      data: { ... }
    });
    expect(resultMessages[1]).toMatchObject({ ... });
  });
  ```

**E2E Tests:**
- Framework: Playwright 1.57.0
- Config: `playwright.config.ts`
- Scope: Full user workflows including UI interactions
- Example: `settings-chat.smoke.spec.ts` tests complete settings and chat workflow
- Uses `test()` from `@playwright/test`
- Leverages `data-testid` attributes for element selection
- Default timeout: 90 seconds per test
- Captures traces, screenshots, and videos on failure
- CI mode: Single worker, 1 retry on failure
- Local mode: Parallel workers enabled, no retries

## Common Patterns

**Async Testing:**
Not extensively shown in unit tests (most are synchronous). Vitest async support available via `async/await` in test functions.

**Error Testing:**
Type narrowing pattern in `utils.test.ts`:
```typescript
it("should return default message for unknown types", () => {
  expect(getErrorMessage(null)).toBe("未知错误");
  expect(getErrorMessage(undefined)).toBe("未知错误");
  expect(getErrorMessage(123)).toBe("未知错误");
  expect(getErrorMessage({})).toBe("未知错误");
});
```

**Immutability Testing:**
Tests verify that helper functions return new arrays/objects rather than mutating inputs:
```typescript
// From chat-helpers.test.ts - applyStreamEvent returns new messages array
const progressMessages = applyStreamEvent(buildMessages(), {...});
const resultMessages = applyStreamEvent(progressMessages, {...});
// resultMessages is a new array, not mutation of progressMessages
```

**Discriminated Union Testing:**
Tests verify correct event type handling:
```typescript
it("applies python and visualization payloads incrementally", () => {
  const withVisualization = applyStreamEvent(buildMessages(), {
    type: "visualization",
    data: { chart: { type: "bar", data: [...] } }
  });
  const withOutput = applyStreamEvent(withVisualization, {
    type: "python_output",
    data: { output: "hello", stream: "stdout" }
  });
  const withImage = applyStreamEvent(withOutput, {
    type: "python_image",
    data: { image: "base64-data", format: "png" }
  });

  expect(withImage[1].visualization?.type).toBe("bar");
  expect(withImage[1].pythonOutput).toBe("hello");
  expect(withImage[1].pythonImages).toEqual(["base64-data"]);
});
```

## Test Environment Configuration

Environment setup in `vitest.config.ts`:
```typescript
export default defineConfig({
  test: {
    environment: "jsdom",          // Browser-like environment
    globals: true,                 // Global test functions (no import needed)
    setupFiles: ["./tests/setup.ts"],  // Global setup/teardown
    include: ["tests/**/*.test.{ts,tsx}"],
    coverage: { ... }
  }
});
```

- JSDOM environment for DOM API testing
- Global test functions enabled for concise syntax
- Single setup file for all mocks and initializations

---

*Testing analysis: 2026-03-29*
