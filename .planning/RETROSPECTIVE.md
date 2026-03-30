# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0 — QueryGPT 优化迭代

**Shipped:** 2026-03-30
**Phases:** 3 | **Plans:** 13 | **Tasks:** 33

### What Was Built
- 后端 990 行单体拆分为 5 个服务模块（SQLExecutor、PythonSandbox、ResultProcessor、VisualizationEngine、GptmeEngine）
- 前端 ChatArea 408→133 行、SchemaSettings 618→357 行组件拆分
- 消息分页 API + TanStack Virtual 虚拟滚动（1000+ 消息 60 FPS）
- Schema 可视化性能优化（useMemo 节点/边、useSchemaLayout hook）
- 全局异常处理标准化 + 加密 key 安全配置
- 完整中文 README 文档（388 行，术语与应用内 zh.json 一致）

### What Worked
- 3 阶段 COARSE 粒度划分合理，后端→前端→文档自然递进
- Wave 并行执行显著提升效率（Phase 2 Wave 1 两个 agent 同时工作）
- 详细的 PLAN.md 任务分解让 executor agent 一次性完成，极少返工
- 验证阶段发现并修复了 5 个 bug，证明验证步骤有价值

### What Was Inefficient
- Phase 2 Wave 1 首次 worktree 失败（git config lock），需要重试
- 部分 SUMMARY.md 的 one_liner 字段为空，影响自动提取
- Phase 3（纯文档翻译）走完整 research→plan→verify 流程略显冗余

### Patterns Established
- TYPE_CHECKING guards 防循环导入（Phase 1 验证）
- useMemo + useCallback 组合优化 React 渲染性能
- 中文 README 镜像英文结构便于 diff 同步维护

### Key Lessons
1. 纯文档/翻译任务可以用 `--skip-research` 减少开销
2. Git worktree 并行执行时需处理 config lock 竞争
3. 组件拆分时同步做类型检查和 lint 验证能提前发现问题

### Cost Observations
- Model mix: 主要使用 Opus 4.6 (executor, verifier, planner)
- Sessions: 1 session 完成全部 3 个阶段
- Notable: Phase 3（1 plan 文档任务）全流程约 15 分钟

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Plans | Key Change |
|-----------|--------|-------|------------|
| v1.0 | 3 | 13 | 首次使用 GSD workflow，建立基线 |

### Top Lessons (Verified Across Milestones)

1. COARSE 粒度（3-5 phases）适合个人项目优化迭代
2. 详细的 PLAN.md 任务分解 > 简短指令，减少 executor 返工
