# Phase 2: Frontend Component Optimization - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-30
**Phase:** 02-frontend-component-optimization
**Areas discussed:** Component Decomposition, Pagination Loading, Virtual Scrolling

---

## Component Decomposition Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| 按功能区域拆 | ChatArea → MessageList + InputBar + MessageCard。SchemaSettings → SchemaGraph + RelationshipPanel + LayoutControls。每个子组件 <120 行。 | ✓ |
| 按状态拆 | 把状态逻辑提取到 custom hooks，组件只保留渲染。 | |
| Claude 判断 | Claude 看实际代码结构决定 | |

**User's choice:** 按功能区域拆
**Notes:** 每个子组件映射到一个视觉区域

---

## Pagination Loading

| Option | Description | Selected |
|--------|-------------|----------|
| 向上滚动自动加载 | 滚到顶部时自动加载更早的消息（像微信/Telegram）。后端每次返回 50 条。 | ✓ |
| 手动点击加载更多 | 顶部显示"加载更多"按钮，用户主动点击 | |
| Claude 判断 | Claude 根据现有代码结构决定 | |

**User's choice:** 向上滚动自动加载
**Notes:** 像聊天 app 那样自然的体验

---

## Virtual Scrolling

| Option | Description | Selected |
|--------|-------------|----------|
| TanStack Virtual | 现代标准，支持动态高度。项目已用 TanStack Query，生态统一。 | ✓ |
| react-virtuoso | 开箱即用的聊天列表组件，自带"滚到底部"和动态高度。但是新依赖。 | |
| Claude 判断 | Claude 调研后决定最合适的 | |

**User's choice:** TanStack Virtual
**Notes:** 生态统一，与现有 TanStack Query 一致

## Claude's Discretion

- 具体子组件边界划分
- Custom hook 命名和提取模式
- Schema 可视化 memoization 策略
- 新消息到达时的滚动行为
- 分页加载的 loading skeleton 设计

## Deferred Ideas

None
