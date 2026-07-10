# QueryGPT vNext：本地可信分析工作区

状态：Approved for clean-room build
目标平台：macOS Apple Silicon、macOS Intel、Windows x64
产品形态：纯本地桌面软件
规格日期：2026-07-10

## 一句话定义

QueryGPT vNext 是一个结果优先的本地分析工作区：用户用自然语言提出业务问题，本地 LLM 只生成受限的 `SemanticQuery`，Rust 语义编译器把它编译成可验证、参数化、只读的 SQL，必要时再把有界数据交给一次性 Pyodide 分析舱，最终在可交互 Canvas 中交付结论、图表、表格和可追溯证据。

它不是数据库 IDE，不是聊天机器人套壳，也不是云端 BI 的离线客户端。

## 北极星体验

用户选择一个本地 SQLite 数据库和语义模型，输入：

> 对比上个月华东和华北的净利润，并预测下个月趋势。

产品应完成以下闭环：

1. 本地 LLM 输出受限语义中间态，不接触物理表名、SQL、凭据或策略上下文。
2. Rust 编译器解析可信语义模型，选择批准的指标与关系，生成参数化只读 SQL、输出结构、血缘与稳定计划哈希。
3. TypeScript 调度器以只读方式执行查询，并对行数、字节数、耗时与取消进行控制。
4. 若预测确有必要，用户先看到代码、输入摘要和资源预算并明确批准；数据才会进入一次性的本地 Pyodide 分析舱。
5. 主界面先展示业务结论、KPI、图表与表格；SQL、语义计划、沙箱日志和耗时仅在 Inspector 中按需出现。
6. 每个结果都可以解释、钻取、保存和精确重放；失败必须以可恢复状态呈现，不能静默降级为规则答案或伪造结果。

## 不可妥协的产品约束

1. **纯本地**：产品运行时没有账号、云端控制面、遥测、远程字体、云端存储、云模型或供应商 API 路径。
2. **LLM 必经**：所有自然语言分析都由真实本地 LLM 参与；模型不可用时明确停止，不生成本地规则冒充的回答。
3. **LLM 不写 SQL**：模型只产生版本化 `SemanticQuery`；不得产生原始 SQL、物理表列、连接条件、指标公式或安全策略。
4. **Rust 控制确定性**：Rust 核心只负责契约、语义、类型、策略、计划、SQL 降低、诊断和证明材料；它不联网、不连接数据库、不生成 UI。
5. **TS/Electron 负责产品**：Electron 主进程与独立 Node utility process 负责本地模型、数据库、持久化、任务生命周期和安全 IPC；Next.js 15/React 19 只承载 Workspace UI。
6. **Python 必须隔离**：不在主进程或宿主 Node 进程运行 CPython。Python 仅存在于一次性、沙箱化 Electron renderer 内的离线 Pyodide/WebAssembly 环境。
7. **结果优先**：默认视觉重心是 Result Canvas；技术细节默认关闭，只能在 Inspector 中按需查看。
8. **clean-room 重建**：新工程独立设计、独立包图、独立组件和独立状态模型；不导入、包装、复制或微调旧实现。
9. **重建后删除**：新产品通过切换门后，删除旧实现；不保留兼容层、双运行时或“以后再清理”的路径。
10. **跨平台路径纪律**：TypeScript 的宿主路径只能由 `node:path` 组合；Rust 的宿主路径只能由 `Path`、`PathBuf`、`OsStr`、`OsString` 处理。
11. **CI 先于功能扩张**：第一个 Rust→N-API Hello World 就必须在 `aarch64-apple-darwin`、`x86_64-apple-darwin`、`x86_64-pc-windows-msvc` 构建并实际加载。

## 首发范围

### 包含

- macOS Apple Silicon、macOS Intel、Windows x64 桌面安装包。
- 本地 SQLite 文件数据源。
- 应用自带的本地模型运行时，以及仅限 loopback 的本地 Ollama 兼容入口。
- 可视化语义模型：实体、维度、指标、时间维度、关系、基数、可见范围和版本。
- `SemanticQuery@1`：聚合、明细、对比三类受限查询。
- Rust N-API 语义编译器、参数化 SQLite SQL、只读执行与血缘证明。
- Result Canvas、Conversation Rail、Library Sidebar、Inspector、Cmd/Ctrl+K、图表钻取、保存图表和保存看板。
- 本地 Pyodide 深度分析舱：固定离线包、明确批准、资源上限、结构化输出、执行后销毁。
- 完整的空、载入、成功、部分失败、可修复错误、取消、恢复与重放状态。

### 不包含

- 任何 SaaS、团队服务器、登录、同步、共享链接、云端队列、远程执行或云端升级路径。
- 云模型 API、任意远程 OpenAI-compatible URL 或 API key 配置。
- Firecracker、E2B、Docker、WSL、远程容器或宿主 CPython。
- PostgreSQL、MySQL、数据仓库和供应商专属连接器的首发承诺。
- 原始 SQL 编辑器、Schema 树 IDE、数据库管理、DDL/DML、任意脚本终端。
- 任意 HTML/SVG/JavaScript 产物、LLM 定义的 CSS 或未列入允许表的图表组件。
- 旧版本配置、历史记录、数据库或 UI 状态的迁移；vNext 使用全新的本地配置根目录。

## 产品原则

### 可信而非“绝对正确”

Rust 可以阻断不存在的成员、模型指定连接、未经批准的函数、写操作、策略绕过和不可重放计划，但不能证明业务人员写下的指标公式本身正确，也不能证明自然语言意图映射永远正确。产品必须展示定义、血缘、数据范围和限制，不能宣称“彻底消灭幻觉”。

### 有界而非任意

查询、上下文、结果、图表和 Python 分析都必须有版本化契约和资源预算。新的表达能力只能通过新版本操作和相应的负向测试加入，不能开放逃生字符串。

### 技术细节可发现但不打扰

业务用户无需看到 IR、SQL 或日志也能完成工作；需要审计的用户可以在不离开结果的情况下打开 Inspector，并复制完整证据。

### 本地不是“少一个后端”

纯本地是完整产品边界：数据、模型、日志、缓存、字体、依赖和分析包都随应用或用户设备存在；任何网络访问都必须是用户明确选择的本地数据库或 loopback 本地模型。

## 成功定义

首发可被称为完成，必须同时满足：

- 三个目标 ABI 的 N-API 插件在 CI 中从空环境构建并被 Node 实际加载。
- 三个平台安装包在干净虚拟机或真实机器上完成安装、启动、卸载和路径矩阵冒烟。
- 代表性语义查询语料能证明模型无法注入原始 SQL、物理成员、连接、公式、策略或方言。
- 一个全新用户可在十分钟内完成“打开 SQLite →确认语义模型→提问→获得可解释图表”。
- 一个预测问题可在明确授权后于本地分析舱完成，并在超时、内存压力、非法输出和网络尝试时安全终止。
- 320/390 px、桌面宽屏、200% 缩放、键盘、深浅色和 reduced-motion 验收通过。
- 应用运行时抓包证明没有未经用户发起的外网请求。
- 新产品通过切换清单后，旧实现、旧依赖入口和兼容分支被删除，仓库只剩一个产品运行路径。

## 已确认决策

| 决策 | 结论 | 理由 |
|---|---|---|
| 首发平台 | macOS arm64、macOS x64、Windows x64 | 覆盖用户指定平台，发布矩阵从第一天真实存在 |
| 部署形态 | Electron 桌面应用 | 本地文件、原生插件、受控 renderer、安装包与桌面 UX 的共同边界 |
| UI | Next.js 15 App Router 静态 renderer + React 19 | 保留 TS 交付速度，同时让生产包不需要本地 HTTP 服务 |
| 语义核心 | 纯 Rust + N-API | 确定性规则、类型与平台 ABI 独立于 Node 版本 |
| LLM 合约 | `SemanticQuery@1` | 关闭 raw SQL、物理 Schema、连接和任意函数逃生口 |
| Python | Pyodide in disposable sandboxed renderer | macOS/Windows 一致、离线、无宿主 Python；明确不冒充 MicroVM |
| 图表 | Recharts 3 + 自有允许表适配层 | 一个图表引擎，React 19 兼容，可访问性和交互可控 |
| UI primitives | shadcn/ui Radix base，按组件引入 | 源码所有权明确，避免完整模板和多组件体系混用 |
| 动效 | `motion` 单包、LazyMotion | 避免重复动画运行时，尊重 reduced motion |
| 字体 | 应用内置 Geist | 离线、跨平台一致、不发出字体网络请求 |
| 旧实现 | 不迁移、不兼容，切换后删除 | 保证 clean-room，而非第二次渐进式改造 |

## 文档权威顺序

冲突时按以下顺序解释：

1. [REQUIREMENTS.md](./REQUIREMENTS.md) 的原子验收条款。
2. [ARCHITECTURE.md](./ARCHITECTURE.md) 的信任边界和协议。
3. [UI-SPEC.md](./UI-SPEC.md) 的可见行为。
4. [PRODUCT-STRATEGY.md](./PRODUCT-STRATEGY.md) 的定位与优先级。
5. [ROADMAP.md](./ROADMAP.md) 的交付顺序。
6. [RESEARCH-EVIDENCE.md](./RESEARCH-EVIDENCE.md) 的外部证据与复用边界。
