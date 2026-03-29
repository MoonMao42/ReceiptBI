---
phase: 01-backend-service-decomposition
plan: 06b
type: execute
wave: 3
depends_on:
  - 01-06
files_modified:
  - apps/api/tests/test_services.py
autonomous: true
requirements:
  - BACK-06
user_setup: []

must_haves:
  truths:
    - "New service module tests created and passing (test_services.py)"
    - "Code review checklist applied to refactored modules"
    - "Bug fixes from refactoring documented with clear commit messages"
    - "Dead code identified and removal tracked"
  artifacts:
    - path: "apps/api/tests/test_services.py"
      provides: "Comprehensive service module tests"
      should_exist: true
  key_links:
    - from: "test_services.py"
      to: "sql_executor.py, python_sandbox.py, result_processor.py, visualization_engine.py"
      via: "imports and tests all service modules"
      pattern: "from apps.api.app.services"
---

<objective>
Execute new service module tests, perform comprehensive code review of refactored services, document any bugs or code quality improvements found (BACK-06), create test report with findings.

Purpose: Verify service modules work correctly, identify and document bugs and improvements during refactoring, establish code quality baseline.

Output: New tests pass, code review findings documented, bug/improvement report created for commit tracking.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/ROADMAP.md
@.planning/phases/01-backend-service-decomposition/01-CONTEXT.md
@.planning/phases/01-backend-service-decomposition/01-RESEARCH.md

# Test files to execute
@apps/api/tests/test_services.py

# Refactored code to review
@apps/api/app/services/gptme_engine.py
@apps/api/app/services/sql_executor.py
@apps/api/app/services/python_sandbox.py
@apps/api/app/services/result_processor.py
@apps/api/app/services/visualization_engine.py
@apps/api/app/main.py
@apps/api/app/db/session.py
@apps/api/app/services/execution.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Execute new service module tests and analyze results</name>
  <files>
    - apps/api/tests/test_services.py (execute)
  </files>
  <read_first>
    - apps/api/tests/test_services.py (the test file)
  </read_first>
  <action>
Run the new test_services.py test suite to validate service module implementation:

**Step 1: Execute new tests**
```bash
cd /Users/maokaiyue/QueryGPT
python -m pytest apps/api/tests/test_services.py -v --tb=short 2>&1 | tee /tmp/test_services_results.log
```

**Step 2: Analyze results**
- How many tests passed?
- How many failed? (If any, debug the failures)
- Are failures in test code or in service modules?
- Do failures indicate bugs in the refactored code?

**Step 3: Document test results**
Create test summary:
```
TEST RESULTS: test_services.py
==============================
Total tests: [N]
Passed: [X] ✓
Failed: [Y]
Skipped: [Z]

Status: [ALL PASS / SOME FAILURES]
```

For any failures, document:
- Test name and what it tests
- Error message
- Root cause (test bug vs code bug)
- Severity (critical, major, minor)

All tests MUST pass per BACK-02. If failures exist, trace root cause.
  </action>
  <verify>
Tests executed successfully:
- [ ] Test suite runs without fatal errors
- [ ] All tests pass (or failures documented with root cause)
- [ ] Test results logged

Automated check:
```bash
cd /Users/maokaiyue/QueryGPT && python -m pytest apps/api/tests/test_services.py --tb=no -q 2>&1 | tail -3
```

Expected: All tests pass.
  </verify>
  <done>
Service module tests executed. Results analyzed (BACK-02 compliance verified).
  </done>
</task>

<task type="auto">
  <name>Task 2: Code review of refactored modules with specific checklist (BACK-06)</name>
  <files>
    - apps/api/app/services/gptme_engine.py (review)
    - apps/api/app/services/sql_executor.py (review)
    - apps/api/app/services/python_sandbox.py (review)
    - apps/api/app/services/result_processor.py (review)
    - apps/api/app/services/visualization_engine.py (review)
    - apps/api/app/main.py (review)
    - apps/api/app/db/session.py (review)
    - apps/api/app/services/execution.py (review)
  </files>
  <read_first>
    - All refactored files (gptme_engine, sql_executor, python_sandbox, result_processor, visualization_engine, main, session, execution)
  </read_first>
  <action>
Perform comprehensive code review using specific checklist:

**Code Review Checklist:**

1. **Error Handling Quality**
   - [ ] All exceptions have specific types (no bare `except:` or `except Exception:`)
   - [ ] Error messages are user-friendly (no stack traces, internal paths)
   - [ ] All error paths are logged with structlog
   - [ ] Error categorization uses engine_diagnostics functions
   - [ ] Check: Search for bare except clauses
     ```bash
     grep -n "except:" apps/api/app/services/*.py
     grep -n "except Exception:" apps/api/app/services/*.py
     ```

2. **Type Safety**
   - [ ] All functions have return type hints
   - [ ] All parameters have type hints
   - [ ] TYPE_CHECKING guards prevent circular imports
   - [ ] No `Any` types without justification
   - [ ] Check: Run mypy on changed files
     ```bash
     mypy apps/api/app/services/gptme_engine.py
     ```

3. **Logging Completeness**
   - [ ] All service modules import structlog
   - [ ] Error conditions logged at appropriate level (error/warning)
   - [ ] Success conditions logged at info level
   - [ ] No logging to stdout (only structlog)
   - [ ] Check: Search for print statements
     ```bash
     grep -n "print(" apps/api/app/services/*.py
     ```

4. **API Compatibility**
   - [ ] GptmeEngine.execute() signature unchanged
   - [ ] Return types match original (AsyncGenerator[SSEEvent])
   - [ ] Service modules don't change public API contract
   - [ ] SSE event format preserved

5. **Dead Code Detection**
   - [ ] Unused imports removed
   - [ ] Unused functions/methods removed
   - [ ] No commented-out code blocks
   - [ ] Duplicate implementations removed
   - [ ] Check: Look for commented code
     ```bash
     grep -n "^[[:space:]]*#" apps/api/app/services/gptme_engine.py | grep -v "^#" | head -20
     ```

6. **Performance Concerns**
   - [ ] No unnecessary database queries
   - [ ] No inefficient loops
   - [ ] Resource leaks prevented (files closed, connections returned)
   - [ ] Service instances created efficiently (not per-request if avoidable)
   - [ ] Check: Look for nested loops or O(n^2) patterns
     ```bash
     grep -n "for.*for" apps/api/app/services/*.py
     ```

7. **Security Concerns**
   - [ ] No hardcoded secrets
   - [ ] Sensitive data not logged
   - [ ] Encryption key validation enforced
   - [ ] SQL injection prevention (via SQLAlchemy)
   - [ ] Python sandbox security checks in place

8. **Code Quality Metrics**
   - [ ] Functions under 100 lines (except orchestrator)
   - [ ] Method names are descriptive
   - [ ] No magic numbers (use constants)
   - [ ] Comments explain "why", not "what"

**Document Findings:**

For each issue found, record:
- **Category:** Error handling / Type safety / Logging / API compatibility / Dead code / Performance / Security / Other
- **Severity:** Critical / Major / Minor / Info
- **Location:** File and line number
- **Description:** What is the issue?
- **Recommendation:** How to fix it?
- **Commit message:** How would you commit this fix?

Example:
```
ISSUE #1: Bare except clause in sql_executor.py
- Category: Error handling
- Severity: Major
- Location: sql_executor.py:line 238
- Description: Exception caught with bare `except:` instead of specific type
- Recommendation: Use `except (OperationalError, ProgrammingError) as exc:`
- Commit: fix(BACK-06): replace bare except with specific types in SQLExecutor

ISSUE #2: Unused import in gptme_engine.py
- Category: Dead code
- Severity: Minor
- Location: gptme_engine.py:line 5
- Description: `import asyncio` unused after refactoring
- Recommendation: Remove unused import
- Commit: refactor(BACK-06): remove unused asyncio import from GptmeEngine
```

Create comprehensive review report documenting all issues.
  </action>
  <verify>
Code review complete:
- [ ] Checked all refactored files
- [ ] Applied code review checklist
- [ ] Found and documented issues
- [ ] Documented severity and recommendations

Review findings recorded:
- [ ] Error handling issues found/verified correct
- [ ] Type safety verified
- [ ] Logging verified complete
- [ ] API compatibility verified
- [ ] Dead code identified (if any)
- [ ] Performance concerns checked
- [ ] Security concerns verified
- [ ] Code quality assessed
  </verify>
  <done>
Code review complete with checklist verification (BACK-06). All issues documented for commit tracking.
  </done>
</task>

<task type="auto">
  <name>Task 3: Create bug/improvement report and summary document</name>
  <files>
    - [Review findings, create summary]
  </files>
  <action>
Create comprehensive bug/improvement report from code review and testing findings:

**Step 1: Compile findings**
From code review (Task 2) and test results (Task 1), compile:
- All critical issues found
- All major issues found
- All minor issues found
- Code quality improvements identified
- Dead code findings
- Performance optimization opportunities

**Step 2: Create REFACTORING_REPORT.md**
Document in clear format:

```markdown
# Refactoring Report: Phase 1 Backend Service Decomposition

## Summary
- Phase: 01-backend-service-decomposition
- Modules refactored: gptme_engine.py (5 service modules extracted)
- Test coverage: [X tests, all passing]
- Code review: Completed with [N] issues found

## Critical Issues Found
[List each critical issue with:
 - Description
 - Root cause
 - Impact
 - Recommended fix
 - Commit message
]

If no critical issues: "No critical issues identified ✓"

## Major Issues Found
[List each major issue]

If no major issues: "No major issues identified ✓"

## Minor Issues Found
[List each minor issue]

## Code Quality Improvements
[List improvements discovered during refactoring:
 - Simplified logic through modularization
 - Reduced cyclomatic complexity
 - Better separation of concerns
 - Improved readability
]

## Dead Code Identified
[List dead code found:
 - Old implementations
 - Unused functions
 - Unused imports
 - Commented-out code
]

## Performance Observations
[List performance-related findings:
 - Unnecessary queries
 - Inefficient patterns
 - Resource leaks prevented
]

## Security Assessment
- Encryption key validation: ✓ Enforced in production
- Error response safety: ✓ No stack traces exposed
- Sensitive data logging: ✓ Protected by structlog
- SQL injection prevention: ✓ SQLAlchemy protection
- Python sandbox security: ✓ Security analyzer in place

## Testing Results
- Existing tests (test_gptme_engine.py): [X/X passed] ✓
- New service tests (test_services.py): [Y/Y passed] ✓
- API compatibility: MAINTAINED ✓
- SSE streaming: VERIFIED ✓

## Commits to Create
[List commits in order:
 1. fix(BACK-06): [issue 1 description]
 2. refactor(BACK-06): [improvement 1 description]
 3. perf(BACK-06): [performance 1 description]
]

## Phase 1 Status
- ✓ BACK-01: Service decomposition complete
- ✓ BACK-02: API compatibility verified
- ✓ BACK-03: Error handling standardization
- ✓ BACK-04: Encryption key enforcement
- ✓ BACK-05: Error response safety
- ✓ BACK-06: Bug fixes and improvements documented

Phase 1 COMPLETE and ready for next phase.
```

**Step 3: Create PHASE_SUMMARY.md**
Create final phase summary showing:
- Objectives achieved
- Requirements satisfied
- Deliverables created
- Bugs fixed (with commit references)
- Next steps

Use this format:

```markdown
# Phase 1 Summary: Backend Service Decomposition

## Objectives
- ✓ Refactor gptme_engine.py monolith into focused service modules
- ✓ Standardize error handling across backend
- ✓ Secure encryption key configuration
- ✓ Maintain full backward compatibility

## Requirements Addressed

| Req ID | Description | Status | Plan |
|--------|-------------|--------|------|
| BACK-01 | Service decomposition | ✓ Complete | 01-01 to 01-03 |
| BACK-02 | API compatibility | ✓ Verified | 01-06 |
| BACK-03 | Error handling | ✓ Complete | 01-04 |
| BACK-04 | Encryption key | ✓ Complete | 01-05 |
| BACK-05 | Error response safety | ✓ Complete | 01-04, 01-05 |
| BACK-06 | Bug fixes & docs | ✓ Complete | 01-06b |

## Key Achievements

### Service Modules Created
- **SQLExecutor** (sql_executor.py): SQL execution with error categorization
- **PythonSandbox** (python_sandbox.py): Python code execution with security analysis
- **ResultProcessor** (result_processor.py): AI output parsing and artifact extraction
- **VisualizationEngine** (visualization_engine.py): Chart generation and formatting
- **GptmeEngine** (refactored): Thin orchestrator, down from 991 to ~200 lines

### Error Handling Improvements
- Replaced bare except clauses with specific exception types
- Standardized error logging via structlog
- Safe error responses (no stack traces in client responses)
- Error categorization via engine_diagnostics

### Security Hardening
- Encryption key validation in production/staging environments
- Application fails fast if ENCRYPTION_KEY not configured
- Development mode permits default key with warnings
- Error responses never expose internal information

## Code Quality Metrics
- Test pass rate: 100% (all existing + new tests)
- API compatibility: 100% (no breaking changes)
- Exception handling: 100% (no bare except clauses)
- Type hints: Complete (all functions, parameters)
- Code coverage: Existing + new service tests

## Files Modified
- [List all files changed]

## Commits Created
[List commit SHAs and messages]

## Next Steps
- Phase 2: [Next phase objectives]
- Deployable: Yes — Phase 1 is production-ready
- Breaking changes: None — Full backward compatibility

---
*Report generated: [date]*
*Phase 1 Status: COMPLETE ✓*
```

This summary becomes the final verification that BACK-06 is satisfied.
  </action>
  <verify>
Report documents created:
- [ ] REFACTORING_REPORT.md created with detailed findings
- [ ] PHASE_SUMMARY.md created with completion status
- [ ] All issues categorized (critical/major/minor)
- [ ] Test results summarized
- [ ] Requirements table shows completion
- [ ] Commits documented for traceability

Reports should clearly show:
- [ ] Phase 1 is complete
- [ ] All requirements satisfied (BACK-01 through BACK-06)
- [ ] Test pass rate 100%
- [ ] API compatibility maintained
- [ ] Code quality baseline established
  </verify>
  <done>
Comprehensive bug/improvement report created. Phase 1 refactoring complete and documented (BACK-06 satisfied).
  </done>
</task>

</tasks>

<verification>
After all tasks complete:
1. Verify new service module tests pass
2. Verify code review findings documented
3. Verify bug/improvement report created
4. Verify summary documents show phase completion
5. Verify all requirements satisfied (BACK-01 to BACK-06)
</verification>

<success_criteria>
- [ ] New service module tests (test_services.py) pass
- [ ] Code review completed with checklist verification
- [ ] Bug/improvement report created with findings
- [ ] Phase summary shows all requirements satisfied
- [ ] All tests pass (100% pass rate)
- [ ] API compatibility verified
- [ ] Code quality baseline established
- [ ] Phase 1 ready for completion
</success_criteria>

<output>
After completion, documents created:
- `.planning/phases/01-backend-service-decomposition/REFACTORING_REPORT.md`
- `.planning/phases/01-backend-service-decomposition/PHASE_SUMMARY.md`
- `.planning/phases/01-backend-service-decomposition/01-06b-SUMMARY.md`
</output>
