# Phase 1: Backend Service Decomposition - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-29
**Phase:** 01-backend-service-decomposition
**Areas discussed:** Decomposition Strategy, Error Handling Style, Compatibility Approach, Bug Fix Scope

---

## Decomposition Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| 直接提取模块 | 把函数按职责移到新文件，保持 GptmeEngine 作为编排器调用它们。简单直接，不变 API。 | ✓ |
| 依赖注入模式 | 通过 FastAPI Depends() 注入服务。更解耦但改动更大。 | |
| Claude 判断 | Claude 看着代码决定最合适的方式 | |

**User's choice:** 直接提取模块
**Notes:** 简单直接，风险最低

---

## Error Handling Style

| Option | Description | Selected |
|--------|-------------|----------|
| 开发详细/生产简洁 | 开发环境看具体错误类型+描述，生产只看类型+通用描述 | |
| 始终简洁 | 任何环境都只看错误类型+用户友好描述，详细信息只在日志 | ✓ |
| Claude 判断 | Claude 根据代码现状决定 | |

**User's choice:** 始终简洁
**Notes:** 详细信息只在 structlog 日志中

---

## Compatibility Approach

| Option | Description | Selected |
|--------|-------------|----------|
| 先写兼容测试 | 先给 SSE 事件格式和关键 API 写快照测试，然后再拆分 | |
| 靠现有测试 | 现有测试套件已经覆盖了主要路径，拆完跑一遍就行 | |
| Claude 判断 | Claude 看现有测试覆盖率决定要不要补 | |

**User's choice:** Other (自定义)
**Notes:** "不要太复杂,随便测试一下就好,因为本来的ci做的也很差" — 靠现有测试 + 手动验证即可

---

## Bug Fix Scope

| Option | Description | Selected |
|--------|-------------|----------|
| 顺手修明显的 | 走过路看到明显问题就修，不专门挖掘 | |
| 深挖潜在问题 | 主动找 edge case、race condition、内存泄漏等 | ✓ |
| 只拆分不修 bug | 专注拆分，bug 另开处理 | |

**User's choice:** 深挖潜在问题
**Notes:** 重构时主动寻找并修复潜在问题

## Claude's Discretion

- 具体模块边界划分（哪些函数放哪个文件）
- Import 组织方式（避免循环导入）
- 是否引入模块间共享类型/接口
- Structlog 格式优化

## Deferred Ideas

None
