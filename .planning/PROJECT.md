# QueryGPT 精进

## What This Is

QueryGPT 是一个开源 AI 数据库助手，用自然语言提问，自动生成只读 SQL 并执行，返回结果、分析和图表。支持语义层定义和 schema 关系图可视化。v1.0 优化迭代已完成：后端架构模块化、前端组件拆分与性能优化、中文文档。

## Core Value

自然语言查询数据库并获得完整的结果分析——这个核心流程必须流畅可靠。

## Requirements

### Validated

- ✓ 自然语言转 SQL 并执行 — existing
- ✓ 自动 Python 分析和图表生成 — existing
- ✓ 语义层（业务术语定义） — existing
- ✓ Schema 关系图可视化拖拽连接 — existing
- ✓ 多模型支持（OpenAI、Anthropic、Ollama、自定义） — existing
- ✓ 多数据库支持（SQLite、MySQL、PostgreSQL） — existing
- ✓ SSE 实时流式响应 — existing
- ✓ SQL/Python 自动修复重试 — existing
- ✓ 配置导入导出 — existing
- ✓ i18n 国际化支持（next-intl + 后端 i18n） — existing
- ✓ Docker 部署支持 — existing
- ✓ 桌面客户端（Electron） — existing
- ✓ CI/CD（GitHub Actions 多层测试） — existing
- ✓ gptme_engine.py 服务模块拆分（SQLExecutor、PythonSandbox、ResultProcessor、VisualizationEngine） — Phase 1
- ✓ 全局异常处理标准化（具体异常类型 + structlog） — Phase 1
- ✓ 加密 key 安全配置（非开发环境强制显式配置） — Phase 1
- ✓ 前端大组件拆分（ChatArea 408→132行、SchemaSettings 618→357行） — Phase 2
- ✓ 聊天消息分页和虚拟滚动（游标分页 + TanStack Virtual） — Phase 2
- ✓ Schema 可视化性能优化（useMemo + useSchemaLayout hook） — Phase 2
- ✓ 中文 README 文档（README.zh.md 388行，术语与 zh.json 一致） — Phase 3

### Active

（无 — v1 milestone 全部需求已完成）

### Out of Scope

- 多租户/用户认证 — 个人使用，不需要
- 实时协作 — 单人使用场景
- 写操作 SQL — 核心设计决策，只读更安全
- 移动端适配 — 桌面场景足够
- 批量查询执行 — 个人使用不需要

## Context

- v1.0 优化迭代完成：后端 990 行单体→5 模块，前端大组件拆分，消息分页+虚拟滚动，中文文档
- 前后端分离架构：Next.js 15 + FastAPI，SSE 通信
- 代码库映射已完成，见 `.planning/codebase/`
- 已解决技术债：大文件拆分、泛异常处理→具体异常、消息分页
- 剩余技术债：Python 沙箱加固、查询缓存、E2E 测试较薄

## Constraints

- **Tech Stack**: 保持现有技术栈（Next.js + FastAPI + SQLAlchemy），不做大规模技术迁移
- **兼容性**: 重构不能破坏现有功能，需要保持 API 兼容
- **个人项目**: 以实用为主，不需要过度工程化

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| 优先架构优化而非新功能 | 代码质量问题会持续拖慢后续开发 | ✓ Good — Phase 1 完成后代码结构清晰 |
| 安全加固降优先级 | 个人使用，风险可控 | ✓ Good — 基础安全已在 Phase 1 处理 |
| 保持现有技术栈 | 避免引入迁移风险，专注于打磨 | ✓ Good |
| 直接模块提取而非依赖注入 | 简单直接，风险低 | ✓ Good — Phase 1 验证 |
| TanStack Virtual 虚拟滚动 | 1000+ 消息场景需要，TanStack 生态一致 | ✓ Good — 60 FPS 验证 |
| 中文 README 镜像英文结构 | 便于 diff 同步维护 | ✓ Good — 388 行对 386 行 |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-03-30 after v1.0 milestone*
