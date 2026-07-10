# vNext 原子需求与验收追踪

状态：Baseline v1
范围：纯本地 macOS arm64、macOS x64、Windows x64 首发
优先级：`MUST` 为切换/发布硬门；`SHOULD` 未满足时必须有书面延期决策，不能静默省略。

## 证据规则

- “有代码”“能构建”“有测试文件”都不是完成证据；证据必须运行并覆盖需求所声明的平台和边界。
- 静态规则用 lint/typecheck/compile 证明；行为用 focused integration/E2E 证明；UI 用真实 Electron 截图与键盘验收证明；发布用目标安装包和干净机器证明。
- 跨平台要求不能用 macOS 单机测试外推到 Windows，反之亦然。
- 安全拒绝必须有负向语料；只证明 happy path 不算满足。
- 每个证据记录 commit SHA、目标 triple、命令、退出码、产物/hash 和必要截图。
- 阶段编号 `P0`–`P6` 对应 [ROADMAP.md](./ROADMAP.md)。

## A. 产品与本地边界

| ID | Pri | 原子需求 | 验收证据 | Phase | 来源 |
|---|---|---|---|---|---|
| LOC-01 | MUST | 安装后的应用在网络完全断开时可完成打开 SQLite、提问、编译、执行、渲染和保存结果。 | 三目标干净机断网 E2E。 | P5 | PROJECT |
| LOC-02 | MUST | 首次启动不要求账号、登录或激活服务器。 | 三目标首次启动录屏/自动化；运行时网络捕获为空。 | P5 | PROJECT |
| LOC-03 | MUST | 应用不发送遥测、分析事件或崩溃报告。 | 依赖/源码 endpoint 扫描 + 代理抓包负向测试。 | P5 | PROJECT/ARCH |
| LOC-04 | MUST | 配置 schema 不包含云模型 provider、API key 或任意远程 base URL 字段。 | 配置 schema snapshot + forbidden-field test。 | P2 | PROJECT/ARCH |
| LOC-05 | MUST | Renderer 不请求远程字体、图片、脚本、样式或 CDN 资源。 | 打包资产扫描 + CSP + 断网 UI E2E。 | P3 | ARCH/UI |
| LOC-06 | MUST | 产品不包含云同步、共享链接、远程队列或 hosted update client。 | package graph/route/endpoint audit。 | P5 | PROJECT |
| LOC-07 | MUST | 所有自然语言分析均调用真实本地 LLM。 | mock-free local model integration log + model-unavailable E2E。 | P2 | PROJECT |
| LOC-08 | MUST | 本地 LLM 不可用时运行以明确错误终止。 | 关闭模型进程 E2E；断言没有 query/result artifact。 | P2 | PROJECT/ARCH |
| LOC-09 | MUST | 应用不以规则 planner 或 canned answer 替代失败的 LLM。 | 故障注入 + artifact/event assertion + forbidden fallback search。 | P2 | PROJECT |
| LOC-10 | SHOULD | 用户可在 app-owned local model runtime 与 loopback Ollama 间选择。 | 两种本地 runtime E2E。 | P2 | ARCH |

## B. Clean-room 与依赖所有权

| ID | Pri | 原子需求 | 验收证据 | Phase | 来源 |
|---|---|---|---|---|---|
| CLR-01 | MUST | vNext 拥有独立 package manifest、lockfile、Rust workspace 和 build output。 | 路径/依赖图审计。 | P0 | PROJECT |
| CLR-02 | MUST | vNext 源码不 import 或 link 旧实现模块。 | dependency graph + forbidden import check。 | P0/P6 | PROJECT |
| CLR-03 | MUST | vNext 不复制旧 CSS tokens、components、assets 或状态 schema。 | clean-room provenance review + file/hash audit。 | P0/P6 | PROJECT |
| CLR-04 | MUST | vNext 使用新的 Electron user-data profile 名称和数据库 schema。 | 首次启动路径与 schema evidence。 | P1 | PROJECT/ARCH |
| CLR-05 | MUST | 每个复制进入项目的第三方源文件都有 adoption record。 | adoption manifest validation。 | P0–P5 | RESEARCH |
| CLR-06 | MUST | 发布包包含准确的第三方 notices 和 SBOM。 | package extraction + notice/SBOM validator。 | P5 | RESEARCH |
| CLR-07 | MUST | 调研用临时 clone 不进入 Git tree、build context 或发布包。 | Git/package file-list check。 | P0/P5 | RESEARCH |

## C. 平台、路径与原生边界

| ID | Pri | 原子需求 | 验收证据 | Phase | 来源 |
|---|---|---|---|---|---|
| PLT-01 | MUST | macOS arm64 安装包在 Apple Silicon 干净系统安装并启动。 | signed/notarized installer E2E。 | P5 | PROJECT |
| PLT-02 | MUST | macOS x64 安装包在 Intel Mac 干净系统安装并启动。 | signed/notarized installer E2E。 | P5 | PROJECT |
| PLT-03 | MUST | Windows x64 安装包在干净 Windows x64 安装并启动。 | signed installer E2E。 | P5 | PROJECT |
| PLT-04 | MUST | 三个目标安装包都能加载匹配架构的 Rust N-API addon。 | packaged `hello/version` doctor smoke。 | P0/P5 | PROJECT/ARCH |
| PTH-01 | MUST | TypeScript 宿主路径组合只使用 `node:path` API。 | ESLint/AST rule 阻断字符串路径拼接 fixture。 | P0 | PROJECT/ARCH |
| PTH-02 | MUST | Rust 宿主路径组合只使用 `Path`/`PathBuf`/`OsStr`/`OsString`。 | Clippy/custom source rule + negative fixture。 | P0 | PROJECT/ARCH |
| PTH-03 | MUST | Host path 与 URL 的转换只使用 `pathToFileURL`、`fileURLToPath` 或 `URL`。 | AST rule + unit fixtures。 | P0 | ARCH |
| PTH-04 | MUST | 受控目录 containment 检查拒绝 `..`、跨盘符和 symlink/junction escape。 | macOS/Windows integration matrix。 | P1 | ARCH |
| PTH-05 | MUST | 模型、SQLite、userData、temp、Pyodide 和 `.node` 路径支持空格与中文。 | 三目标 packaged path smoke。 | P0/P5 | USER/ARCH |
| PTH-06 | MUST | Windows 路径测试覆盖 UNC 与长路径。 | Windows CI integration evidence。 | P0/P5 | USER/ARCH |
| PTH-07 | MUST | 逻辑路径比较不依赖 Rust `to_string_lossy()` round-trip。 | custom lint/review check + non-UTF fixture where supported。 | P0 | ARCH |
| PTH-08 | MUST | 默认日志不输出用户数据库和模型的绝对路径。 | log snapshot redaction tests。 | P1 | ARCH |

## D. Rust Semantic Compiler

| ID | Pri | 原子需求 | 验收证据 | Phase | 来源 |
|---|---|---|---|---|---|
| SEM-01 | MUST | `SemanticQuery@1` 是版本化 discriminated union。 | generated JSON Schema snapshot + validation corpus。 | P1 | ARCH |
| SEM-02 | MUST | `SemanticQuery@1` schema 不存在 raw SQL 字段。 | schema assertion + malicious payload rejection。 | P1 | PROJECT/ARCH |
| SEM-03 | MUST | `SemanticQuery@1` schema 不存在物理 table/column 字段。 | schema assertion + malicious payload rejection。 | P1 | PROJECT/ARCH |
| SEM-04 | MUST | `SemanticQuery@1` schema 不存在 join 或 join predicate 字段。 | schema assertion + malicious payload rejection。 | P1 | PROJECT/ARCH |
| SEM-05 | MUST | `SemanticQuery@1` schema 不允许 LLM 定义指标公式或任意函数。 | schema assertion + expression/function attack corpus。 | P1 | PROJECT/ARCH |
| SEM-06 | MUST | filter operator 和 value type 都来自闭集枚举。 | property/negative tests。 | P1 | ARCH |
| SEM-07 | MUST | SQL filter 值全部生成绑定参数。 | golden AST/SQL tests；禁止值出现在 SQL text。 | P1 | ARCH |
| SEM-08 | MUST | 指标公式只从 active `SemanticManifest` revision 解析。 | changed-manifest integration tests。 | P1 | ARCH |
| SEM-09 | MUST | join path 只从 manifest relationships 选择。 | invented-join rejection corpus。 | P1 | ARCH |
| SEM-10 | MUST | 编译器检测声明 cardinality 下的 fanout/additivity 风险。 | one-to-many/many-to-many golden + rejection tests。 | P1 | RESEARCH/ARCH |
| SEM-11 | MUST | host policy 由 TS host 传入且 IR 无 policy claim 字段。 | schema assertion + policy-injection plan tests。 | P1 | ARCH |
| SEM-12 | MUST | final logical plan 只包含 allowlisted read-only nodes。 | malicious plan corpus + AST visitor evidence。 | P1 | ARCH |
| SEM-13 | MUST | 编译器对 rows、joins、time span、plan nodes 和 output bytes 执行结构预算。 | boundary/property tests。 | P1 | ARCH |
| SEM-14 | MUST | 相同 canonical inputs 生成相同 SQL、parameters、lineage 和 `planHash`。 | repeat/property tests on all three native targets。 | P1 | ARCH |
| SEM-15 | MUST | diagnostics 包含稳定 code 和 JSON path。 | diagnostic snapshots。 | P1 | ARCH |
| SEM-16 | MUST | diagnostics 明确标记 `safeToRepair`。 | repairable/non-repairable corpus。 | P1 | ARCH |
| SEM-17 | MUST | Rust core 不包含 network client 或 database driver dependency。 | `cargo tree`/capability audit。 | P0/P1 | PROJECT/ARCH |
| SEM-18 | MUST | Rust core 的公开 compile API 不接收文件路径。 | Rust public API inspection test。 | P1 | ARCH |
| SEM-19 | MUST | N-API adapter 对输入字节、嵌套深度和超时设上限。 | boundary/fuzz tests。 | P1 | ARCH |
| SEM-20 | MUST | N-API adapter 把 Rust panic 转换为稳定错误而不终止宿主。 | forced-panic child-process test。 | P0/P1 | ARCH |

## E. 本地 LLM、调度与数据库

| ID | Pri | 原子需求 | 验收证据 | Phase | 来源 |
|---|---|---|---|---|---|
| LLM-01 | MUST | LLM 只能接收暴露的 scope/member 业务元数据。 | prompt/context snapshot redaction tests。 | P2 | ARCH |
| LLM-02 | MUST | LLM 输出在进入 Rust 前通过 `SemanticQuery@1` runtime validation。 | invalid-output integration tests。 | P2 | ARCH |
| LLM-03 | MUST | IR repair 只接收 diagnostics 与原 IR，不接收生成 SQL。 | prompt snapshot assertions。 | P2 | ARCH |
| LLM-04 | MUST | 一个 run 最多执行两次 LLM IR repair。 | repeated-invalid model fixture。 | P2 | ARCH |
| LLM-05 | MUST | Ollama adapter 拒绝所有非 loopback 地址和 redirect。 | URL/redirect/proxy attack tests。 | P2 | ARCH |
| LLM-06 | MUST | Stop 终止本地 LLM producer。 | token-stream cancellation integration test。 | P2 | ARCH/UI |
| ORC-01 | MUST | 每个 run 具有唯一 `runId` 和单调 event sequence。 | concurrency/event property tests。 | P2 | ARCH |
| ORC-02 | MUST | run terminal state 只能提交一次。 | cancel/complete race tests。 | P2 | ARCH |
| ORC-03 | MUST | 首发同一 Workspace 同时只允许一个 active analysis run。 | UI/orchestrator integration test。 | P2 | UI |
| ORC-04 | MUST | 历史打开不会自动执行 LLM、SQL 或 Python。 | reopen network/DB spy E2E。 | P2 | ARCH/UI |
| DAT-01 | MUST | 数据源只能通过原生 file picker 选择本地 SQLite 文件。 | renderer capability test + E2E。 | P1 | PROJECT/ARCH |
| DAT-02 | MUST | 用户 SQLite 以只读 flags 打开。 | driver flag assertion + write-attempt rejection。 | P1 | ARCH |
| DAT-03 | MUST | introspection 只创建 draft semantic manifest。 | state transition test。 | P1 | ARCH/UI |
| DAT-04 | MUST | 未经用户确认的 draft manifest 不进入 LLM context。 | prompt/context test。 | P1/P2 | ARCH/UI |
| DAT-05 | MUST | SQL 在执行前成功 prepare。 | malformed/dialect fixture。 | P1 | ARCH |
| DAT-06 | MUST | SQL 在执行前通过 `EXPLAIN QUERY PLAN` budget gate。 | high-cost fixture rejection。 | P1 | ARCH |
| DAT-07 | MUST | 查询结果在 persistence/render 前通过 output schema 校验。 | type/schema mismatch integration test。 | P1 | ARCH |
| DAT-08 | MUST | 查询结果受 row 与 byte cap 限制。 | boundary tests。 | P1 | ARCH |
| DAT-09 | MUST | Stop 调用 SQLite interrupt 并停止 producer。 | long recursive query cancellation test。 | P1/P2 | ARCH |
| DAT-10 | MUST | cooperative interrupt 超期后 DB worker 被销毁。 | uncooperative-driver fault injection。 | P1/P2 | ARCH |
| DAT-11 | MUST | 应用 metadata SQLite 与用户 SQLite 使用不同连接/文件。 | process/connection integration assertion。 | P1 | ARCH |

## F. Typed artifacts、持久化与重放

| ID | Pri | 原子需求 | 验收证据 | Phase | 来源 |
|---|---|---|---|---|---|
| ART-01 | MUST | Renderer 只接受 allowlisted `ArtifactEvent@1` operation/version。 | unknown operation/version rejection tests。 | P2 | ARCH |
| ART-02 | MUST | Renderer 拒绝倒序或重复 sequence。 | event reducer property tests。 | P2 | ARCH |
| ART-03 | MUST | Artifact protocol 不存在任意 HTML/SVG/JS operation。 | schema assertion + malicious payload tests。 | P2 | ARCH/UI |
| ART-04 | MUST | 成功结果保存 semantic query、manifest/compiler/policy version 和 plan hash。 | persistence integration snapshot。 | P2 | ARCH |
| ART-05 | MUST | terminal artifact snapshot 可在重启后恢复而不重新执行。 | kill/restart E2E。 | P2 | ARCH/UI |
| ART-06 | MUST | Exact replay 仅在固定输入与 data fingerprint 满足时可用。 | fingerprint match/mismatch tests。 | P2 | ARCH/UI |
| ART-07 | MUST | data fingerprint 变化后的动作标记为 Run on current data。 | stale-history UI E2E。 | P3 | UI |
| ART-08 | MUST | 保存图表持久化 artifact spec 与 provenance，而非截图。 | reopen/edit integration test。 | P3 | UI |
| ART-09 | MUST | dashboard tile 引用 saved artifact version。 | dashboard persistence test。 | P3 | UI |

## G. Isolated Analysis Capsule

| ID | Pri | 原子需求 | 验收证据 | Phase | 来源 |
|---|---|---|---|---|---|
| SBX-01 | MUST | Python 运行前展示完整 source、输入行/字节、包版本、timeout、seed 和输出上限。 | approval UI E2E。 | P4 | ARCH/UI |
| SBX-02 | MUST | 每个 Python run 都需要一次明确用户批准。 | approval state-machine tests。 | P4 | PROJECT/UI |
| SBX-03 | MUST | source hash 或 dataset hash 变化后旧批准失效。 | mutation/reapproval test。 | P4 | UI |
| SBX-04 | MUST | Python 只在 `sandbox: true`、`nodeIntegration: false` 的 disposable renderer 内运行。 | runtime webPreferences assertion + process audit。 | P4 | ARCH |
| SBX-05 | MUST | Python 代码实际在 renderer 内的 Web Worker 执行。 | process/worker instrumentation test。 | P4 | ARCH |
| SBX-06 | MUST | Analysis capsule 的 CSP 禁止网络连接。 | CSP assertion + fetch/WebSocket attack tests。 | P4 | ARCH |
| SBX-07 | MUST | Electron session 拦截并拒绝 analysis capsule 的所有网络请求。 | HTTP/DNS/redirect attack integration tests。 | P4 | ARCH |
| SBX-08 | MUST | Analysis job 不包含数据库凭据、路径或 handle。 | schema assertion + IPC capture。 | P4 | PROJECT/ARCH |
| SBX-09 | MUST | Pyodide 与允许的 wheels 全部来自签名发布包资源。 |断网 package load + package file-list/hash。 | P4/P5 | ARCH |
| SBX-10 | MUST | 分析舱禁止运行时安装任意 Python 包。 | micropip/pip/network/import attack tests。 | P4 | ARCH |
| SBX-11 | MUST | timeout 或 Stop 会销毁整个 analysis renderer。 | infinite-loop cancellation E2E。 | P4 | ARCH |
| SBX-12 | MUST | 每次 terminal state 后销毁 renderer、session 和虚拟文件系统。 | lifecycle/process/session assertion。 | P4 | ARCH |
| SBX-13 | MUST | Analysis output 只有通过 `AnalysisResult@1` validation 才能进入 Canvas。 | malicious output corpus。 | P4 | ARCH |
| SBX-14 | MUST | Analysis output 拒绝 HTML、SVG、JavaScript、pickle 和文件路径。 | schema/attack corpus。 | P4 | ARCH |
| SBX-15 | MUST | 分析失败时已完成的 SQL 结果仍保持成功可用。 | partial-failure UI E2E。 | P4 | UI |
| SBX-16 | MUST | 发布包不依赖宿主 CPython。 | clean machine process/file dependency audit。 | P5 | PROJECT |

## H. Result-First UI

| ID | Pri | 原子需求 | 验收证据 | Phase | 来源 |
|---|---|---|---|---|---|
| UI-01 | MUST | 桌面主视图把 Result Canvas 作为最大可用内容区域。 | 1440×900 screenshot geometry assertion。 | P1/P3 | UI |
| UI-02 | MUST | Conversation Rail 与 Result Canvas 可由键盘调整宽度。 | keyboard E2E。 | P3 | UI |
| UI-03 | MUST | Library Sidebar 只显示导航/保存对象，不显示执行日志。 | component/UI review。 | P3 | UI |
| UI-04 | MUST | Inspector 默认关闭。 | fresh-state E2E。 | P2 | PROJECT/UI |
| UI-05 | MUST | Inspector 以 overlay Sheet 打开而不改变 Canvas artifact 宽度。 | geometry screenshot test。 | P2/P3 | UI |
| UI-06 | MUST | Inspector 提供 Semantic、SQL、Lineage、Timing tabs。 | UI E2E。 | P2 | UI |
| UI-07 | MUST | 存在 sandbox artifact 时 Inspector 提供 Sandbox tab。 | P4 UI E2E。 | P4 | UI |
| UI-08 | MUST | Cmd/Ctrl+K 可以打开 Command Palette。 | macOS/Windows keyboard E2E。 | P3 | USER/UI |
| UI-09 | MUST | 图表 drill-down 操作生成结构化 intent 而不直接改 SQL。 | interaction/IPC assertion。 | P3 | UI/ARCH |
| UI-10 | MUST | Loading 主状态使用结果形状 skeleton 而非单一 spinner。 | screenshot test。 | P2 | USER/UI |
| UI-11 | MUST | 每张图表都有文本 takeaway。 | artifact contract/UI test。 | P1 | UI |
| UI-12 | MUST | 每张图表都有可访问 table alternative。 | keyboard/screen-reader DOM assertion。 | P1/P3 | UI |
| UI-13 | MUST | Recharts chart 开启 accessibility layer。 | component test/DOM assertion。 | P1 | UI |
| UI-14 | MUST | 390 px viewport 的 document 无横向溢出。 | real Electron screenshot + width assertion。 | P3 | UI |
| UI-15 | MUST | 320 px viewport 的核心提问/结果/Inspector 流程可完成。 | real Electron E2E。 | P3 | UI |
| UI-16 | MUST | 200% zoom 不隐藏核心动作或造成页面双向滚动。 | real Electron E2E/screenshots。 | P3/P5 | UI |
| UI-17 | MUST | 所有关键流程可只用键盘完成。 | macOS/Windows keyboard script。 | P3/P5 | UI |
| UI-18 | MUST | reduced-motion 下关闭非必要位移、缩放和 shimmer。 | media emulation screenshot/DOM test。 | P3 | UI |
| UI-19 | MUST | light 与 dark theme 的正文/控件满足 WCAG AA。 | automated contrast + visual review。 | P3/P5 | UI |
| UI-20 | MUST | Error state 显示阶段、保留成果、主恢复动作和稳定 code。 | fault-injection screenshot suite。 | P2/P3 | UI |
| UI-21 | MUST | 默认业务界面不显示 raw IR、SQL、Python 日志或 stack trace。 | fresh/success/failure screenshot review。 | P2/P3 | PROJECT/UI |
| UI-22 | MUST | 运行中 Stop 始终可见。 | viewport matrix E2E。 | P2 | UI |
| UI-23 | SHOULD | primary chart 首屏可用内容不等待 Inspector evidence render。 | performance timeline assertion。 | P3 | PRODUCT/UI |

## I. IPC、内容与安全

| ID | Pri | 原子需求 | 验收证据 | Phase | 来源 |
|---|---|---|---|---|---|
| SEC-01 | MUST | 每个 renderer→host IPC payload 都经过 runtime schema validation。 | channel inventory + invalid-payload tests。 | P0/P1 | ARCH |
| SEC-02 | MUST | Electron main 拒绝非预期 webContents 发出的 IPC。 | hostile-window test。 | P1 | ARCH |
| SEC-03 | MUST | Workspace renderer 启用 sandbox、context isolation 并关闭 Node integration。 | packaged runtime assertion。 | P0 | ARCH |
| SEC-04 | MUST | Workspace CSP 不允许远程 script/style/font/image。 | CSP and network tests。 | P0/P3 | ARCH |
| SEC-05 | MUST | Markdown、数据库文本、SQL 和日志显示前被 escape/sanitize。 | XSS payload corpus。 | P2 | ARCH/UI |
| SEC-06 | MUST | LLM 不能控制 chart component 名称、CSS 或颜色 token。 | artifact schema attack corpus。 | P1/P2 | ARCH/UI |
| SEC-07 | MUST | 外部链接只有在用户明确点击并确认后交给 OS。 | navigation/window-open E2E。 | P3 | ARCH |
| SEC-08 | MUST | 敏感参数在 Inspector、日志和复制证据中按 policy 脱敏。 | snapshot/redaction tests。 | P2 | ARCH/UI |
| SEC-09 | MUST | production package 不读取 proxy environment 来访问模型。 | injected proxy env integration test。 | P2/P5 | ARCH |
| SEC-10 | MUST | 发布候选在运行时网络捕获中只出现用户明确启用的 loopback 模型流量。 | proxy/pcap evidence。 | P5 | PROJECT/ARCH |

## J. CI、打包与发布

| ID | Pri | 原子需求 | 验收证据 | Phase | 来源 |
|---|---|---|---|---|---|
| CI-01 | MUST | 第一个 Rust N-API `hello()` 提交同时包含 macOS arm64 build/load job。 | GitHub Actions check + artifact/load log。 | P0 | USER/ARCH |
| CI-02 | MUST | 同一提交同时包含 macOS x64 build/load job。 | GitHub Actions check + artifact/load log。 | P0 | USER/ARCH |
| CI-03 | MUST | 同一提交同时包含 Windows x64 MSVC build/load job。 | GitHub Actions check + artifact/load log。 | P0 | USER/ARCH |
| CI-04 | MUST | 每个 native job 断言 runner 实际架构、Rust triple 和 Node ABI。 | CI log assertions。 | P0 | ARCH |
| CI-05 | MUST | 交叉编译结果不替代目标架构 Node load smoke。 | workflow structure check。 | P0 | ARCH |
| CI-06 | MUST | 每个 PR 运行 TypeScript typecheck 与 lint。 | required check。 | P0 | ARCH |
| CI-07 | MUST | 每个 PR 运行 Rust fmt/clippy 与受影响测试。 | required check。 | P0 | ARCH |
| CI-08 | MUST | 每个 PR 运行路径拼接静态门。 | required check + failing fixture。 | P0 | USER/ARCH |
| CI-09 | MUST | 每个 PR 运行 SemanticQuery negative corpus。 | required check。 | P1 | ARCH |
| CI-10 | MUST | Next production build 是静态导出且无 server route 依赖。 | build manifest validator。 | P0/P3 | ARCH |
| CI-11 | MUST | 发布 workflow 产出三个目标安装包并保留 checksums/SBOM/notices。 | release artifact manifest。 | P5 | ARCH |
| CI-12 | MUST | macOS release 通过签名与 notarization 验证。 | `codesign`/`spctl`/notary evidence。 | P5 | ARCH |
| CI-13 | MUST | Windows release 通过 Authenticode 验证。 | PowerShell signature evidence。 | P5 | ARCH |
| CI-14 | MUST | 三目标安装包在干净环境执行 install→launch→query→uninstall smoke。 | release E2E evidence。 | P5 | PROJECT/ARCH |
| CI-15 | SHOULD | 开发机默认验证脚本只运行静态检查与受影响测试。 | documented command/timing review。 | P0 | USER/ARCH |

## K. Cutover 与删除

| ID | Pri | 原子需求 | 验收证据 | Phase | 来源 |
|---|---|---|---|---|---|
| CUT-01 | MUST | vNext 在删除旧实现前满足本文件全部 MUST 需求。 | requirement-by-requirement audit with current evidence。 | P6 | PROJECT |
| CUT-02 | MUST | vNext 不读取、导入或转换旧 profile 数据。 | empty-profile E2E + forbidden schema/path check。 | P6 | PROJECT |
| CUT-03 | MUST | 切换提交删除旧实现源码和旧运行入口。 | Git tree/dependency graph evidence。 | P6 | PROJECT |
| CUT-04 | MUST | 切换后仓库只存在一个可启动产品运行路径。 | command/workflow/package entry inventory。 | P6 | PROJECT |
| CUT-05 | MUST | 切换后 CI 不构建、测试或打包旧实现。 | workflow/job/package manifest audit。 | P6 | PROJECT |
| CUT-06 | MUST | 删除后重新运行三个目标的 required checks 与安装包 smoke。 | post-delete same-commit CI evidence。 | P6 | PROJECT |
| CUT-07 | MUST | 旧实现删除没有兼容 wrapper、feature flag 或隐藏 fallback。 | forbidden dependency/symbol/config audit。 | P6 | PROJECT |

## Phase 追踪汇总

| Phase | 纵向结果 | 主要 requirement IDs |
|---|---|---|
| P0 | Clean-room shell + 三平台 N-API Hello World + CI | CLR-01–03, CLR-05/07, PTH-01–03/05–07, SEM-17/20, SEC-01/03/04, CI-01–08/10/15 |
| P1 | 手工受限 IR → Rust compile → read-only SQLite → Result Canvas | CLR-04, PTH-04/08, SEM-01–20, DAT-01–11, UI-01/11–13, SEC-02/06, CI-09 |
| P2 | 本地 LLM 自然语言 → IR repair → durable typed result + Inspector | LOC-04/07–10, LLM-01–06, ORC-01–04, ART-01–06, UI-04–06/10/20–22, SEC-05/08/09 |
| P3 | 完整 Workspace：Library、Cmd+K、drill-down、保存与响应式 | LOC-05, ART-07–09, UI-02/03/05/08/09/14–19/23, SEC-07 |
| P4 | 明确批准的本地 Pyodide 分析舱 | SBX-01–15, UI-07 |
| P5 | 三平台签名安装包、断网、安全、视觉与可访问性验收 | LOC-01–03/06, CLR-06, PLT-01–04, PTH-05/06, SBX-09/16, UI-16/17/19, SEC-09/10, CI-11–14 |
| P6 | 通过全需求审计后切换并删除旧实现 | CLR-02/03, CUT-01–07 |

## Release completion rule

只有当：

1. 每个 `MUST` 行都有与该行范围相同的当前证据；
2. 三平台证据来自同一 release commit；
3. 负向/故障/取消/重启证据齐全；
4. 真实安装包 UI 截图与键盘验收通过；
5. 切换删除后的 commit 再次全绿；

项目才可标记完成。缺少证据等同于未完成，不以“代码看起来支持”推断。
