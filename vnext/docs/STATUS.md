# QueryGPT vNext 实施状态

日期：2026-07-10
当前阶段：P0 — Clean-room shell 与跨平台原生地基（进行中）

## 已落地

- 新工程只位于 `vnext/`，没有导入、包装或复制旧实现。
- Rust `semantic-core` 与 N-API 边界已经建立；`hello()` 返回版本化 doctor payload：`contract`、真实编译 target 与 compiler version。
- TypeScript 宿主路径统一从 `node:path` 进入；Rust 路径统一从 `Path`/`PathBuf` 进入。两端都拒绝父目录、双平台分隔符、盘符/ADS、Windows 保留名和尾随点/空格。
- path-policy 使用 TypeScript AST 与 Rust 负例扫描，并有 `.cjs`、多行 template、named `format!`、array join 的失败 fixtures。
- GitHub Actions 已定义真实目标矩阵：macOS arm64、macOS Intel、Windows x64；每个 job 会断言 runner 架构、Node ABI、Rust target，运行 Clippy、目标机路径用例、Rust 测试、N-API build/load smoke。
- Next.js renderer 已切到静态导出，并完成全新 Result-First Workspace：Conversation Rail、Result Canvas、Inspector、Cmd/Ctrl+K、桌面/移动布局、可访问图表数据表与显式下钻确认。
- 原型界面明确标为示例数据和未执行状态；不会把静态演示冒充真实 LLM、SQLite 或语义编译结果。

## 当前本地证据

- path-policy 正向门禁通过，4 类反模式 fixtures 能让门禁失败。
- TypeScript strict typecheck 通过。
- 20 个跨平台路径边界用例通过。
- Next.js production static export 通过。
- Rustfmt 与 Clippy `-D warnings` 通过。
- Apple Silicon `aarch64-apple-darwin` N-API release build 与 Node load smoke 通过。
- 浏览器实测 desktop 与 390 px mobile：Inspector、Command Palette、responsive tabs、图表节点、确认后仅写入追问草稿均正常；新会话无 console error/warning。

## 尚未完成，因此不能宣称 P0 通过

1. workflow 还没有在 GitHub 的三个真实 runner 上产生绿色结果与 artifact 证据。
2. Electron main/preload/utility-process 尚未建立；当前只有 static renderer，而不是可安装桌面应用。
3. Electron 还没有从打包资源加载对应 `.node`，也没有用版本化 IPC 把 doctor payload 送到 renderer。
4. TypeScript 常规 lint、SBOM/notices 生成骨架和 packaged-path smoke 仍需补齐。
5. 旧实现仍保留；只有 P0–P5 与最终 cutover 审计全部通过后才删除。

## 下一步（严格顺序）

1. 将当前第一切片作为独立变更提交并触发 `vnext-ci.yml`；只处理真实 macOS/Windows 失败，不在本机反复跑全量矩阵。
2. 三个 N-API job 绿色后，建立最小 Electron native frame：只加载 `apps/workspace/out`、加载目标 `.node`、展示 doctor 状态，不接 LLM/SQLite/Python。
3. 补齐 P0 的 lint、packaged path、artifact/SBOM 证据并做 P0 gate 审计。
4. P0 真正通过后进入 P1：手工受限 `SemanticQuery@1` → Rust compile → read-only SQLite → Result Canvas。不要提前接 LLM，也不要先做 Python 分析舱。
