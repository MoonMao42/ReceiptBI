# UI-SPEC：Result-First Local Analytics Workspace

## 体验命题

界面必须让用户首先感到“我在操作一个分析工作区”，而不是“我在和机器人聊天”。对话负责提出意图和修改结果，Canvas 负责承载真正的工作成果，Inspector 负责在需要时提供完整技术证据。

三个判断标准：

1. 没打开 Inspector 的业务用户，也能理解结论、范围、变化和下一步。
2. 打开 Inspector 的分析师，不离开当前结果就能审计语义、SQL、血缘、分析代码和耗时。
3. 在窄窗口、键盘、深色、200% 缩放和 reduced-motion 下，核心任务仍完整可用。

## 信息架构

### Library Sidebar

用途：导航和保存对象，不显示执行日志。

分区：

- New analysis
- Recent analyses
- Dashboards
- Saved charts
- Data sources
- Semantic model

展开宽度 240 px，可折叠为 56 px icon rail。折叠状态保存在本地。底部仅放 Settings、local model/data health 和 Help，不显示账号或云同步入口。

### Conversation Rail

用途：提问、查看紧凑分析时间线、修正意图。

- 桌面默认占可用内容宽度 34%，最小 320 px、最大 520 px。
- 顶部显示当前分析标题、数据源和语义模型 revision 的简短状态。
- 中部是问题与紧凑 timeline，不把完整图表重复进消息泡。
- 底部是 sticky composer、Stop、上下文 chips 和模式提示。
- 成功结果消息只显示摘要和“结果已在 Canvas 更新”；Canvas 是唯一完整结果表面。

### Result Canvas

用途：结果的主要阅读、交互和保存空间。

结构：

1. Result header：标题、数据时间范围、freshness、保存状态、Inspector、更多操作。
2. Executive summary：2–4 句明确结论，区分事实、推断与预测。
3. KPI strip：最多 4 个核心指标，含单位、对比基准和变化方向。
4. Primary visualization：占首屏主要空间，支持键盘与指针钻取。
5. Supporting artifacts：次级图、明细表、假设/限制。
6. Footer evidence strip：语义模型 revision、数据行数、执行时间、plan hash 短码；点击打开 Inspector。

Canvas 有自己的滚动容器。结果切换时保持各自滚动位置。空状态、载入和错误都保留相同空间结构，避免布局跳动。

### Inspector

默认关闭，以右侧 Sheet 覆盖 Canvas，不因打开而突然把图表压窄。在 ≥ 1600 px 的用户主动设置下可以 pin，pin 状态不成为默认。

Tabs：

- Semantic：问题映射到的 scope、指标、维度、时间范围、filters 和 manifest revision。
- SQL：只读参数化 SQL、脱敏参数、target dialect、prepare/explain 状态。
- Lineage：指标到物理来源的可读血缘与已应用 policy 摘要。
- Sandbox：仅在深度分析存在时显示代码、输入摘要、包版本、seed、预算、日志与 output hash。
- Timing：本地检索、LLM、compile、DB、render、sandbox 的阶段耗时与取消状态。

所有 tab 支持 Copy evidence；复制内容是结构化、脱敏文本，不包含数据库绝对路径或未授权数据值。

### Command Palette

`Cmd+K`（macOS）/`Ctrl+K`（Windows）打开。支持：

- New analysis
- Go to analysis/dashboard/chart
- Switch local data source
- Open semantic model
- Open/close Inspector
- Save current chart/dashboard
- Toggle theme
- Show keyboard shortcuts

命令按上下文过滤，不提供 SQL console、远程 provider 或云分享命令。

## 桌面布局

```text
┌──────────────┬──────────────────────┬─────────────────────────────────────┐
│ Library      │ Conversation Rail    │ Result Canvas                       │
│ 240 / 56 px  │ 320–520 px           │ flexible                            │
│              │                      │ header + summary + KPI              │
│ Recent       │ question             │ ┌─────────────────────────────────┐ │
│ Dashboards   │ progress timeline    │ │ primary interactive chart       │ │
│ Charts       │ approvals            │ └─────────────────────────────────┘ │
│ Sources      │                      │ supporting chart / table            │
│ Model        │ sticky composer      │ evidence strip                      │
└──────────────┴──────────────────────┴─────────────────────────────────────┘
                                                    ┌───────────────────────┐
                                                    │ Inspector overlay     │
                                                    └───────────────────────┘
```

- 使用 native window frame 和原生窗口控制；首发不做 frameless titlebar。
- macOS 和 Windows 使用同一内容层级，但快捷键、菜单名、滚动条和 file picker 遵循平台习惯。
- Conversation/Canvas 分隔条可键盘调整，并有明显 focus ring。
- 用户可以隐藏 Conversation Rail，进入纯 Canvas 阅读；恢复动作始终可见。

## 响应式行为

### ≥ 1180 px

三栏结构；Conversation Rail 与 Canvas 并列。Library 可展开/折叠。

### 768–1179 px

Library 变为 off-canvas Sheet。Conversation 与 Canvas 仍可并列；低于可用阈值时 Conversation 变为底部 Sheet。Canvas 保持主表面。

### < 768 px 或窄窗口

- 默认显示 Canvas。
- 顶部 segmented control 在 Result / Conversation 间切换。
- Library 为左侧 full-height Sheet，Inspector 为右侧 full-height Sheet。
- KPI strip 横向可滚动但每个 KPI 可完整读出；不能裁掉单位。
- 图表有最小 280 px 绘图区，必要时将 legend 移到底部并折叠次级 series。
- 表格允许自己的横向滚动，页面本身不得出现横向溢出。

必须单独验收 320 px 与 390 px；它们不是“以后再做的 mobile web”，而是桌面窗口可缩窄时的产品状态。

## 视觉系统

### 字体

- Geist Sans：界面与正文，本地包内加载。
- Geist Mono：SQL、IR、hash、数值对齐区域。
- 默认正文 14 px/20 px；结果摘要 16 px/26 px；页面标题 20–24 px。
- 表格和 Inspector 可使用 12–13 px，但不能靠低对比度制造“专业感”。

### 色彩

以 CSS variables 定义语义 token，不在业务组件写原始 hex。

- Base：Zinc/Slate 风格的 neutral background、surface、border、text。
- 唯一品牌 accent：冷蓝紫，用于 primary action、当前 selection 和 AI active state。
- Success/warning/destructive 仅表达状态，不用于大面积装饰。
- Chart palette 使用固定、对比度验证过的 6 色 allowlist；LLM 不能选择颜色。
- 深色模式不是反色；surface 层级、grid、tooltip、focus 和 chart series 独立校准。

### 空间与形状

- 4 px 基础网格；常用间距 8/12/16/24/32。
- Canvas 主区减少无意义 card 嵌套；用 section、divider 和留白组织层次。
- Radius 克制：控件 6–8 px，surface 10–12 px；不使用每个元素都悬浮的“卡片汤”。
- Shadow 仅用于 Sheet、popover、dragged artifact 等真实层级。

### 图标与资产

- 一个开源 outline icon set，随包构建；不混用 emoji 作为产品 icon。
- 空状态插图如需使用必须原创或许可证明确，并随包本地存在。
- 不请求远程图片，不复制被调研产品的品牌图形或截图资产。

## 组件清单

### Shell

- `WorkspaceShell`
- `LibrarySidebar`
- `WorkspaceTopbar`
- `ConversationRail`
- `ResultCanvas`
- `InspectorSheet`
- `CommandPalette`
- `ResizableWorkspace`

### Conversation

- `QuestionComposer`
- `QuestionMessage`
- `AnalysisTimeline`
- `ProgressStep`
- `ClarificationCard`
- `ApprovalCard`
- `RunStatusBanner`
- `StopButton`

### Results

- `ResultHeader`
- `ExecutiveSummary`
- `KpiStrip` / `KpiItem`
- `ArtifactTabs`
- `ChartArtifact`
- `DataTableArtifact`
- `DrilldownMenu`
- `AssumptionsPanel`
- `EvidenceStrip`
- `SaveArtifactDialog`

### Inspector

- `SemanticPlanPanel`
- `CompiledSqlPanel`
- `LineagePanel`
- `SandboxPanel`
- `TimingPanel`
- `CopyEvidenceButton`

### System states

- `EmptyCanvas`
- `ChartSkeleton`
- `ResultSkeleton`
- `ErrorRecoveryCard`
- `OfflineLocalModelCard`
- `NativeRuntimeMismatchCard`
- `DataSourceUnavailableCard`

这些是全新 domain components，不是旧组件的 wrapper。shadcn primitives 只提供 Button、Sheet、Dialog、Command、Tooltip、Tabs、Table、Sidebar、Resizable、Skeleton 等基础行为。

## 关键交互

### 第一次使用

1. 空 Canvas 用一句话解释产品，不展示大型营销页。
2. Primary action：Open local SQLite。
3. 文件选定后显示本地 introspection 进度和 semantic model draft。
4. 用户确认关键表、时间字段和至少一个指标；未确认的定义不能进入 LLM context。
5. 检查本地模型；若无可用模型，选择本地 GGUF 或启用 loopback Ollama。
6. 提供 3 个来自已确认语义的 starter questions。
7. 第一个成功结果后，轻量提示 Inspector、drill-down 和 Save，不弹多步 onboarding tour。

### 提问与流式状态

- 发送后 composer 保留文本直到 run accepted，再清空。
- 250 ms 内显示 result-shaped skeleton 与第一个 timeline 状态。
- Timeline 使用业务语言：Understanding、Checking definitions、Preparing query、Reading data、Building result；默认不显示 chain-of-thought。
- skeleton 是 KPI/图表/表格轮廓，不用无限 spinner 作为主状态。
- Stop 始终在运行状态可见；按下后立即变为 Cancelling，最终明确显示 Cancelled。
- 新问题不会覆盖未完成 run；用户必须先停止或明确选择并行新分析（首发默认不允许并行）。

### 结果更新

- 新 artifact 到达时只替换对应稳定 `artifactId`，不整页闪烁。
- Executive summary 在数据与 compile evidence 完成后显示，不能先用未经验证的 LLM 文本填充。
- 图表进入使用 150–220 ms opacity/translate，reduced-motion 下直接出现。
- 数据 revision 或 result version 改变时显示可见 version indicator；用户可回到上一个 terminal version。

### Drill-down

用户点击或键盘选择柱、点、series、KPI 后显示菜单：

- Explain this change
- Break down by…
- Compare with previous period
- View records
- Add as filter

操作转化为结构化 intent + 当前 semantic member/filter context，再由本地 LLM 生成新的 `SemanticQuery`。不能把 SVG label 拼成隐藏自然语言，也不能直接修改 SQL。

每个图表交互都有 focusable 等价操作；hover 不是唯一入口。

### Inspector

- Result header、Evidence strip、Cmd/Ctrl+K 三处可打开。
- 打开时焦点进入 Sheet 标题；关闭后回到触发按钮。
- SQL 默认格式化、只读，参数单独显示；敏感值脱敏。
- Sandbox tab 在批准前展示 code preview/budget；批准后展示运行与结果证据。
- Inspector 状态不影响 Canvas artifact 数据或执行生命周期。

### 深度分析批准

Approval Card 必须展示：

- 为什么 SQL 不够；
- 将发送到分析舱的列、行数和字节数；
- 完整 Python source（可折叠但可检查）；
- 固定 package/version；
- timeout、seed、最大输出；
- Run once 与 Cancel。

不得使用预选 checkbox、模糊“继续”按钮或持久授权。每个 run 单独批准；代码或输入 hash 改变后旧批准失效。

### 保存与看板

- Save chart 保存 artifact spec、semantic query、model revision 和 display configuration，不只保存截图。
- Save dashboard 将已有 saved artifacts 排列到简单 grid；首发不做自由像素画布。
- 打开保存对象默认显示最后 terminal snapshot，并明确 data timestamp；重新执行由用户触发。
- 看板每个 tile 都可以 Open analysis、Inspect 和 Refresh。

## 图表规则

### 选择

图表类型由受控 deterministic recommender 在已验证数据结构上选择，LLM 只能提出语义 intent，不直接指定 React component。

- 单指标：KPI。
- 时间 + 1–4 series：line/area。
- 类别比较：bar；类别多时水平 bar。
- 两数值关系：scatter。
- 明细与精确值：table。
- Pie/donut 不在首发 allowlist。

### 上限

- 默认可见 series ≤ 8，类别 ≤ 30，点数 ≤ 2,000；超出先聚合、采样或转表格。
- Tooltip 显示完整单位、时间和 filter context。
- 轴不能截断造成误导；若使用非零 baseline，必须显式标注。
- 预测 series 使用不同 line style 和区间带，不与历史事实混淆。
- 每张图都有一句文本 takeaway、数据范围和 accessible table alternative。

## 状态设计

### Empty

- 无数据源：Open local SQLite。
- 有数据源无模型：Review semantic model。
- 模型未运行：Choose local model。
- 已就绪无结果：显示基于语义的 starter questions。
- dashboard 无 tile：Add a saved chart。

### Loading

- 使用 result-shaped skeleton。
- Timeline 只显示可验证阶段状态，不泄露 chain-of-thought。
- 长于 3 秒显示已用时间与 Stop；长于预算显示明确原因或终止。

### Error

每个 error card 必须包含：

- 用户语言标题；
- 发生在哪个阶段；
- 已保留的成果（例如 SQL 结果仍可用）；
- 一个 primary recovery action；
- Open Inspector；
- 稳定 error code。

禁止 toast-only 错误、原始 stack trace 占据 Canvas 或自动切到另一个运行模式。

### Cancelled

保留用户问题和已完成的安全证据，不把 partial data 当成功 artifact。提供 Edit and retry。

### Stale / Replay

- 历史 snapshot 显示 data timestamp、model revision 和 compiler version。
- Exact replay 只有输入、revision 和 data fingerprint 条件满足时可称 exact。
- 否则按钮文案是 Run on current data。

## 动效规则

- 只安装 `motion`，使用 `LazyMotion` + `m`。
- 允许：Canvas artifact entry、Inspector Sheet、skeleton shimmer、保存/批准状态的轻微转换。
- Recharts 自己负责 chart transition；不再套一层 Motion 动画。
- 禁止长 spring、parallax、循环装饰、数字滚动造成错误读数。
- `prefers-reduced-motion` 下关闭位移、缩放和 shimmer；状态仍通过文本/图标表达。

## 可访问性

- 全流程可键盘完成：打开数据、选择模型、提问、停止、查看结果、钻取、批准、打开 Inspector、保存。
- visible focus ring 不得被去除；resizable separator 有方向、值和键盘操作。
- Sheet/Dialog/Command 有真实 title/description、focus trap 与 focus restore。
- 运行区域使用 `aria-busy`；live region 只播报阶段变化，不重复 token stream。
- Recharts 开启 `accessibilityLayer`；所有图表有 takeaway 和表格替代。
- 颜色不是唯一编码；预测、成功、警告有文字或形状标识。
- 正文/控件满足 WCAG AA；200% zoom 无信息丢失或双向页面滚动。
- 支持 reduced motion、深浅色、高对比 Windows 设置的基本可辨识性。

## 文案原则

- 用业务动作：Check definitions、Read data、Build result；不用 Agent loop、AST pass、tool call。
- 把事实、推断、预测分别标识。
- 不说“绝对正确”“零幻觉”“军事级沙箱”。
- 错误告诉用户下一步，不用“Something went wrong”。
- 默认隐藏 SQL/IR/Python，但不使用“黑盒魔法”营销语言。

## 视觉与交互验收矩阵

每个关键流程必须有截图和行为证据：

| 场景 | Viewport/环境 | 验收 |
|---|---|---|
| First use | 1440×900 light | 层级清晰，10 分钟任务无死路 |
| Successful result | 1440×900 light/dark | summary/KPI/chart/table 首屏合理，Inspector 默认关闭 |
| Inspector | 1440×900 | 不破坏 Canvas，tab/复制/关闭焦点正确 |
| Narrow | 390×844 | document 无横向溢出，Result/Conversation/Sheets 完整 |
| Minimum | 320×720 | primary action、图表替代、composer 可操作 |
| Zoom | desktop 200% | 无遮挡，核心操作可达，无页面双向滚动 |
| Keyboard only | desktop | 全关键任务可完成，focus 顺序与可见性正确 |
| Reduced motion | all | 无非必要位移/循环动画，状态仍清楚 |
| Empty/loading/error/cancelled | desktop + 390 | 状态占位稳定、恢复动作明确 |
| Sandbox approval | desktop | code/input/budget 可检查，批准不可复用 |
| Windows paths | Windows x64 | 中文/空格路径显示友好，不泄露绝对路径 |

完成 UI 不能只凭组件测试；必须在真实 Electron 安装包中截图与键盘验收。
