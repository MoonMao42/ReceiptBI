# 市场、架构与 UI 调研证据

快照日期：2026-07-10（Asia/Shanghai）
方法：只使用官方仓库；浅克隆后读取源文件、包清单、许可证和 Git 元数据；未运行被调研项目。
用途：形成产品与架构决策，不构成法律意见，也不授权复制受限源码。

## 调研计划与完成情况

| 工作流 | 问题 | 方法 | 完成证据 | 结论 |
|---|---|---|---|---|
| ChatBI 产品 | 市面产品真正解决了什么，缺了什么 | 克隆 WrenAI、Vanna、DB-GPT、Chat2DB、Lightdash、Metabase；检查核心链路和 UI | 下方 ChatBI 快照 | 语义上下文、typed artifacts、成熟 BI 状态比“聊天转 SQL”更重要 |
| 语义编译器 | Rust 应该证明什么，哪些不能证明 | 克隆 WrenAI、Cube、Malloy、PRQL、DataFusion、sqlparser-rs、napi-rs；读 IR、planner、policy、binding | 下方语义快照 | 使用自有严格 IR 和纯 Rust 核心；N-API 默认；不宣称绝对正确 |
| UI/模板 | 哪些现代 UI 能合法复用，哪些只是参考 | 克隆 Vercel Chatbot、shadcn/ui、Tremor、Motion、Geist、Vercel admin starter | 下方 UI 快照 | 自建 Result-First Workspace；选 shadcn primitives、Recharts、Motion、Geist；不套模板 |
| 沙箱 | MicroVM 是否适合纯本地 macOS+Windows | 克隆 Pyodide、Firecracker、E2B、E2B infra、Wasmtime；检查平台与许可证 | 下方沙箱快照 | Firecracker/E2B 不符合本地双平台；采用诚实命名的 Pyodide 分析舱 |
| 许可证 | 哪些源码可依赖、改写、仅研究或禁止 | 读取根许可证、路径映射、包元数据和补充许可 | 每表 License 列及复用规则 | 默认独立实现；少量 MIT/Apache/OFL 组件保留 notice；AGPL/商业/自定义限制仅研究 |

后续每次准备引入源码或依赖时，必须重新固定版本、复查许可证与平台支持。这里的 HEAD 是调研证据，不是自动升级策略。

## 语义编译器仓库快照

所有仓库曾以 `--depth=1 --filter=blob:none` 克隆到临时调研目录。

| 项目 | 克隆 HEAD | 许可证 | 官方来源 | 采用/拒绝 |
|---|---|---|---|---|
| WrenAI | `60a934e10511f4446a03a184e759d1b072c8ce3b` | 路径映射：core/sdk Apache-2.0，docs CC-BY-4.0 | [Canner/WrenAI](https://github.com/Canner/WrenAI) | 借鉴 manifest、关系、policy 与 DataFusion pass；不把 modeled SQL 或上游类型暴露给 LLM/产品 ABI |
| Cube | `3b4b85ec6a11f179ea7e61191fcbec788da555cf` | 默认 Apache-2.0，部分包 MIT；逐文件复核 | [cube-js/cube](https://github.com/cube-js/cube) | 借鉴 query 词汇、fanout 与 access-policy 测试；不引入整套运行时 |
| Malloy | `3445d28af669e2bf40e7f9ec0ba09547fd7a94b3` | MIT | [malloydata/malloy](https://github.com/malloydata/malloy) | 借鉴 restricted query 的负向能力测试；不用完整文本语言作为 LLM 合约 |
| PRQL | `30fd81d6de9a61d427bd5474383e4053c9550e1e` | Apache-2.0 | [PRQL/prql](https://github.com/PRQL/prql) | 借鉴分阶段 IR、版本、JSON Schema、诊断与方言测试；不向 LLM 暴露通用 RQ |
| Apache DataFusion | `f4a700d79de4deb36ff21700c2b85f91d5507c07` | Apache-2.0 | [apache/datafusion](https://github.com/apache/datafusion) | 作为类型/计划机制参考或受控依赖；默认 `SQLOptions` 不是安全证明 |
| sqlparser-rs | `aeb616fc65134cb7dc2e8a20ee68c6bb612b5c76` | Apache-2.0 | [apache/datafusion-sqlparser-rs](https://github.com/apache/datafusion-sqlparser-rs) | 用于最终 AST 审计与方言解析；解析成功不等于语义正确或数据库可执行 |
| napi-rs | `68cbb8d63a73d4c740c4c1c9b61b82c88e13f8b7` | MIT | [napi-rs/napi-rs](https://github.com/napi-rs/napi-rs) / [napi.rs](https://napi.rs) | 采用 Node-API binding、平台包 loader 与 CI 模式 |

### 被源码证据否定的说法

- “Rust 可以让 SQL 绝对正确”不成立。编译器可以证明契约、成员、类型、连接、策略、计划 allowlist 和确定性；它不能证明人类写的指标定义、数据质量或自然语言意图一定正确。
- “能解析 SQL 就安全”不成立。sqlparser-rs 明确区分 syntax 与 semantics；DataFusion 的 SQL 选项默认允许 DDL、DML 和 statements，宿主必须显式关闭并继续检查最终计划。
- “WrenAI 已经是我们需要的严格 LLM IR”不成立。其常规 agent 路径仍包含 modeled SQL；只能把其核心机制放在自有 contract/trait 后评估。
- “浏览器 WASM 应打包完整查询引擎”不划算。语义编译的主运行时是 N-API；v1 不增加浏览器编译目标。

### 语义方向推导

1. LLM 合约必须比 SQL 和通用关系 IR 更小。
2. 物理表、列、连接、函数、公式、方言、策略和凭据必须是 host-only。
3. Rust 输出必须包含 SQL 之外的参数、输出结构、血缘、已应用策略、预算、警告和计划哈希。
4. 修复循环只修改 IR，不允许模型补丁生成后的 SQL。
5. 编译器必须是纯函数式核心，不拥有网络、数据库或文件系统能力。

## ChatBI / BI 仓库快照

六个仓库使用 `--depth 1 --filter=blob:none --no-checkout` 真实克隆；只按需读取证据文件。

| 项目 | 克隆 HEAD | 许可证边界 | 官方来源 | 产品结论 |
|---|---|---|---|---|
| WrenAI | `60a934e10511f4446a03a184e759d1b072c8ce3b` | main 的 core/sdk 为 Apache-2.0；legacy UI 为 AGPL 且不维护 | [Canner/WrenAI](https://github.com/Canner/WrenAI) | 语义上下文是核心；旧聊天 UI 仅作模式研究，不能复制 |
| Vanna | `365d0617c1a4567ffee1b19b40c27feb4206bfcf` | MIT | [vanna-ai/vanna](https://github.com/vanna-ai/vanna) | `create/update/replace/remove/reorder` typed component lifecycle 值得独立实现；不移植大型 Lit/Python 栈 |
| DB-GPT | `209588ddd582e0501232a2bc5a3921997c2a5a7d` | MIT | [eosphoros-ai/DB-GPT](https://github.com/eosphoros-ai/DB-GPT) | 可研究 task plan 和 chart advisor；混用 AntD/MUI/Tailwind/Emotion 不是 UI 基础 |
| Chat2DB | `e7011fa75cf2795d8a841cd6cea5c5ec27662bba` | Apache 文本外叠加限制性补充许可；视为不可安全复用 | [OtterMind/Chat2DB](https://github.com/OtterMind/Chat2DB) | 证明数据库 IDE 路径成熟但与 Result-First 相反；只研究不可复制 |
| Lightdash | `32dfc0e940198a2d2c402d8ebc0b77036dda25e2` | core 多为 MIT；`packages/backend/src/ee/**` 为受限 source-available | [lightdash/lightdash](https://github.com/lightdash/lightdash) | 最佳语义查询/成熟 BI 状态参考之一；AI backend 不复制 |
| Metabase | `f7f8697947ea69907ce8598bfc21987df300d257` | core AGPL，`enterprise/**` 商业许可 | [metabase/metabase](https://github.com/metabase/metabase) | 最完整 BI 产品语法与状态参考；全部独立重做，不复制源码或资产 |

### 市场推导

1. **语义上下文是壁垒**：Wren、Lightdash、Cube 都把指标、维度、关系和政策变成可审查对象。
2. **Chat 应发 typed artifacts**：Vanna、DB-GPT 证明增量结构化组件优于 HTML 字符串；我们的 renderer 必须 schema 校验并 allowlist。
3. **成熟 BI 不是一张图**：Metabase、Lightdash 的空/载入/错误、筛选、表格、可视化配置和保存对象同样重要。
4. **技术密度不是专业感**：Chat2DB 的 IDE 布局适合数据库操作者，不适合作为业务结果的默认表面。
5. **当前空位**：真实克隆的项目中，没有一个同时做到纯本地双平台桌面、LLM 受限 IR、Rust 语义编译、一次性本地 Python 分析舱、Result Canvas、Inspector 与确定性重放。

## UI 与模板仓库快照

| 项目 | 克隆 HEAD | 许可证 | 官方来源 | 决策 |
|---|---|---|---|---|
| Vercel Chatbot | `c2f8235e1f3ea903ad8b7f61447c4f74164b5c58` | Apache-2.0 | [vercel/chatbot](https://github.com/vercel/chatbot) | 研究 typed stream、artifact panel、result-shaped skeleton；不作为应用模板，不引入其云依赖或复制整套源码 |
| shadcn/ui | `21e4ceb94418096e21a7f1990027741a8f9b085d` | MIT | [shadcn-ui/ui](https://github.com/shadcn-ui/ui) | 仅通过 CLI 选取 Radix base 的 Sidebar、Resizable、Sheet、Command、Skeleton、Chart 等 primitives，并记录来源 |
| Tremor | `ca4d588f47820ff3d514d37fa4ee08a4222dec11` | Apache-2.0 | [tremorlabs/tremor](https://github.com/tremorlabs/tremor) | 只研究图表交互；不引入，避免与 shadcn/Recharts 重复体系 |
| Motion | `61833240e899fbbe4f50484ec5f9f7fe688de843` | MIT | [motiondivision/motion](https://github.com/motiondivision/motion) | 只安装 `motion`，用 `LazyMotion` + `m`；不同时安装 `framer-motion` |
| Geist | `10dc7658f13c38a474cde201bb09a4617267545b` | OFL-1.1 | [vercel/geist-font](https://github.com/vercel/geist-font) | 字体随包本地分发；保留 OFL notice，不请求远程字体 |
| Vercel admin starter | `fe026711c19ac3ee4589c86a738f59b84e611559` | MIT | [vercel/nextjs-postgres-nextauth-tailwindcss-template](https://github.com/vercel/nextjs-postgres-nextauth-tailwindcss-template) | 只证明栈可行；传统 admin shell 和云依赖不适合作为产品基础 |

### UI 技术选择

研究快照建议的起始组合是 Next.js 15、React 19、Tailwind CSS 4、shadcn/ui v4 Radix base、react-resizable-panels 4、Recharts 3、Motion 12 和本地 Geist。实现时锁定同一兼容组合并由 lockfile/CI 固定；文档中的版本号不是自动追最新版指令。

选择规则：

- 一个 primitives 体系：shadcn/ui Radix base。
- 一个图表引擎：Recharts。
- 一个动画包：`motion`。
- 一个字体来源：包内 Geist。
- 不复制 Vercel Chatbot、完整 dashboard block、Tremor source set 或旧产品视觉资产。
- 每个引入的 shadcn 源文件记录组件名、CLI/registry 版本、上游路径、许可证和本地修改。

官方设计资料：

- [Next.js 15](https://nextjs.org/blog/next-15)
- [shadcn components](https://ui.shadcn.com/docs/components)
- [shadcn Sidebar](https://ui.shadcn.com/docs/components/radix/sidebar)
- [shadcn Resizable](https://ui.shadcn.com/docs/components/radix/resizable)
- [shadcn Chart](https://ui.shadcn.com/docs/components/radix/chart)
- [Motion bundle guidance](https://motion.dev/docs/react-reduce-bundle-size)
- [Motion reduced motion](https://motion.dev/docs/react-use-reduced-motion)

## 沙箱与本地运行时快照

| 项目 | 克隆 HEAD | 许可证 | 官方来源 | 决策 |
|---|---|---|---|---|
| Pyodide | `1ec895f00b8eb0c079b9cbfbb31cc385fc8661e4` | MPL-2.0 | [pyodide/pyodide](https://github.com/pyodide/pyodide) / [pyodide.org](https://pyodide.org/en/stable/) | 采用固定版本运行时和许可兼容的离线 wheels；隔离在一次性 sandboxed renderer/Web Worker |
| Firecracker | `bf433f8689e02893bf7345fbca1e21eda062db5c` | Apache-2.0 | [firecracker-microvm/firecracker](https://github.com/firecracker-microvm/firecracker) | 需要 Linux/KVM；拒绝用于 macOS+Windows 首发，不预留云端 MicroVM 路径 |
| E2B SDK | `0bd06d86d292816c10a942511b2f4a64a37337da` | Apache-2.0 | [e2b-dev/E2B](https://github.com/e2b-dev/E2B) | 云/服务型沙箱；拒绝运行时集成 |
| E2B infra | `6c442d49af3037e03bccfa96282caba1cdb90890` | Apache-2.0 | [e2b-dev/infra](https://github.com/e2b-dev/infra) | 基础设施复杂度与纯本地相反；只作隔离威胁模型参考 |
| Wasmtime | `66f269153d05db6d6209ac116d712703034f341c` | Apache-2.0 | [bytecodealliance/wasmtime](https://github.com/bytecodealliance/wasmtime) | 不作为首发第二套 Python/WASM 宿主；Pyodide 已由 Chromium WASM 执行 |

### 安全结论

Pyodide + Chromium/Electron sandbox **不是 MicroVM，也不是对宿主漏洞的绝对防护**。它适合单机单用户产品中隔离 LLM 生成的数据分析代码，因为：

- 没有 Node integration、数据库凭据、宿主文件系统或任意包安装。
- 分析运行在 Web Worker；主进程可以超时销毁整个 renderer。
- 独立、内存型 Electron session 可通过 CSP、请求拦截与 permission deny 阻断网络。
- 输入和输出受版本化 schema、行/字节/耗时预算约束。
- 每次执行后销毁 renderer、session 与虚拟文件系统。

如果未来威胁模型变成多租户或需要运行恶意第三方代码，这个方案不够；但本项目明确不建设云端/多租户升级路径，因此不为该场景提前引入 Firecracker。

## 复用规则

### 允许

- 以固定依赖方式使用 MIT、Apache-2.0、MPL-2.0、OFL-1.1 软件，履行各自 notice/source 义务。
- 通过 shadcn CLI 引入少量已登记 primitives，再由项目负责维护。
- 根据公开协议、交互行为和测试思想进行独立实现。
- 在自有 trait 和 wire contract 后评估 Wren/DataFusion 等引擎，不让上游 API 成为产品 ABI。

### 禁止

- 复制 AGPL、商业许可、source-available 或自定义限制仓库的源码、样式、图标、布局资产或文案。
- 整包复制 Vercel Chatbot、Wren legacy UI、Chat2DB、Metabase 或完整 dashboard 模板。
- 在没有逐路径许可证复核时从多许可证 monorepo 复制文件。
- 把调研克隆加入产品仓库、构建上下文或发布包。
- 为追求“像某产品”而复刻其独特视觉表达；只借鉴通用工作流和可验证行为。

## 实施前复核清单

每个第三方选择进入代码前都要产生一条 adoption record：

1. 官方 URL、固定版本/commit、包完整性哈希。
2. SPDX/路径许可证与 NOTICE 义务。
3. 实际引入范围，以及为何依赖优于独立实现。
4. macOS arm64、macOS x64、Windows x64 支持证据。
5. 网络、文件、子进程、原生 ABI 和动态代码能力审查。
6. 移除/替换方案，不允许成为无法控制的产品 wire contract。
7. 在 `THIRD_PARTY_NOTICES` 和 SBOM 中可追踪。
