# Requirements: QueryGPT 精进

**Defined:** 2026-03-29
**Core Value:** 自然语言查询数据库并获得完整的结果分析——这个核心流程必须流畅可靠。

## v1 Requirements

Requirements for this optimization milestone. Each maps to roadmap phases.

### Backend Refactoring

- [x] **BACK-01**: gptme_engine.py 拆分为独立服务模块（SQLExecutor、PythonSandbox、ResultProcessor、VisualizationEngine、GptmeEngine orchestrator），每个模块职责单一
- [x] **BACK-02**: 拆分后所有现有 API 端点行为不变，SSE 事件格式兼容，现有测试全部通过
- [x] **BACK-03**: 全局异常处理改为具体异常类型（SQLAlchemyError、asyncio.TimeoutError 等），不再使用裸 except
- [x] **BACK-04**: 移除默认加密 key 硬编码，非开发环境强制要求显式配置 ENCRYPTION_KEY
- [x] **BACK-05**: DEBUG 模式下错误响应不泄露系统内部信息（堆栈、路径、配置）
- [x] **BACK-06**: 重构过程中发现的 bug 和 dead code 顺手修复，commit 中标注

### Frontend Refactoring

- [ ] **FRONT-01**: ChatArea.tsx（408行）拆分为容器组件 + 子组件 + 自定义 hooks
- [x] **FRONT-02**: SchemaSettings.tsx（618行）拆分为图表组件 + 关系管理 + 布局管理
- [ ] **FRONT-03**: 聊天消息支持分页加载（新增后端 API 端点 + 前端无限滚动）
- [ ] **FRONT-04**: 消息列表使用虚拟滚动（TanStack Virtual），大对话不卡顿
- [ ] **FRONT-05**: Schema 可视化使用 useMemo 优化，节点/边数组避免不必要重渲染
- [ ] **FRONT-06**: Schema 图表布局计算提取为独立 hook
- [ ] **FRONT-07**: 重构过程中发现的 bug、race condition、低效写法顺手修复

### Documentation

- [ ] **DOC-01**: 创建 README.zh.md，完整翻译英文 README 所有章节（Features、Quick Start、Tech Stack、Configuration、Development 等）

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Performance

- **PERF-01**: 查询结果缓存（dogpile.cache + Redis），重复查询不打数据库
- **PERF-02**: 关系建议算法优化（O(n²) → 缓存）

### Security

- **SEC-01**: Python 执行沙箱加固（资源限制、超时、内存上限、subprocess 隔离）
- **SEC-02**: Docker 级别沙箱隔离（长期方案）

### Documentation

- **DOC-02**: 中文开发者指南（架构说明、贡献指南）

## Out of Scope

| Feature | Reason |
|---------|--------|
| 多租户/用户认证 | 个人使用，不需要 |
| 写操作 SQL | 核心设计决策，只读更安全 |
| 实时协作 | 单人使用场景 |
| 移动端适配 | 桌面场景足够 |
| 批量查询执行 | 个人使用不需要 |
| 技术栈迁移 | 现有栈无需更换，重点是内部优化 |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| BACK-01 | Phase 1 | Complete |
| BACK-02 | Phase 1 | Complete |
| BACK-03 | Phase 1 | Complete |
| BACK-04 | Phase 1 | Complete |
| BACK-05 | Phase 1 | Complete |
| BACK-06 | Phase 1 | Complete |
| FRONT-01 | Phase 2 | Pending |
| FRONT-02 | Phase 2 | Complete |
| FRONT-03 | Phase 2 | Pending |
| FRONT-04 | Phase 2 | Pending |
| FRONT-05 | Phase 2 | Pending |
| FRONT-06 | Phase 2 | Pending |
| FRONT-07 | Phase 2 | Pending |
| DOC-01 | Phase 3 | Pending |

**Coverage:**
- v1 requirements: 14 total
- Mapped to phases: 14 ✓
- Unmapped: 0

---

*Requirements defined: 2026-03-29*
*Last updated: 2026-03-29 after roadmap creation*
