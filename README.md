<div align="center">

<img src="docs/images/receiptbi-icon.png" width="200" alt="ReceiptBI logo">

ReceiptBI 用来调查文件和数据库,用自然语言来提供你需要的信息和内容.

[中文](README.md) | [English](README.en.md)

</div>

## 功能特点

### 1.自建适合数据处理流程的Agent 

基于 Python 与 PydanticAI 构建
- **语义隔离**：业务指标、维度与关联规则直接绑定在对应数据表下方。当不同表含有相同字段名时，仅在当前表的作用域内解析，避免同名字段含义混淆。
- **数据预检**：导入数据库时会自动检查字段数据类型与离群值，清洗规则单独保存，不修改原始数据文件。

### 2.Rust 限制运行SQLite

- **查询计划预算审查**：运行 SQL 前审查,防止整表查询卡死数据库。
- **只读防御模式**：对LLM产生的破坏性指令拒绝执行或者清洗。


### 3.智能语义层项目理解

- **LLM分析语义层**：高级model（类似gpt或claude前沿模型）分析一次语义层，存储后，可用弱model来进行查询
- **分层语义层**：在agent探索到具体某个表的时候，表下的语义层信息才会提供给model


## 工作原理

```mermaid
flowchart LR
    data["文件 / 只读数据库"] --> prep["准备数据"]
    prep --> semantic["确认业务背景"]
    semantic --> ask["提出问题"]
    ask --> run["进行分析"]
    run --> validate["核查依据"]
    validate -->|还需调整| run
    validate --> report["可编辑报表"]
```

## 产品一览

### 业务问题调查

调查把最初的问题、相关数据、发现、图表和后续工作放在一起。并且模块化提供给报表

![包含关键发现和图表的数据调查报告](docs/images/zh/workspace-analysis.png)

### 把调查结果整理成可编辑报表

选择调查内容，再生成草稿。

![将一次调查智能整理为报表前的来源确认](docs/images/zh/report-organizing.png)

### 预览并导出分页报表

页面预览会提前显示分页位置，让指标、图表和来源在打印或导出后仍然清楚。

![多页报表的打印预览](docs/images/zh/report-print-preview.png)

### 项目理解

每条定义都留在它描述的数据来源或表下面。分层而治，节省token，越用越准确

![按数据表分层治理的业务语义](docs/images/zh/semantic-governance.png)

## 快速开始

可以直接下载桌面版使用

### 1. 克隆项目

```bash
git clone https://github.com/MoonMao42/ReceiptBI.git
cd ReceiptBI
```

### 2. 运行项目

macOS / Linux 需要 Python 3.11+ 和 Node.js LTS：

```bash
./start.sh
```

也可以用 Docker 运行：

```bash
docker compose up --build
```

Windows 推荐使用 Docker Desktop，或在 WSL2 中运行 `./start.sh`。

### 3. 配置使用

打开 `http://localhost:3000`：

1. 在设置中选择模型服务（OpenAI 兼容接口、Anthropic、DeepSeek 或 Ollama）
2. 添加文件（CSV/XLSX/Parquet/JSON）或只读数据库连接（SQLite/MySQL/PostgreSQL）
3. 提出第一个希望数据回答的问题

## 技术栈

| 部分 | 技术 |
|------|------|
| 前端 | Next.js 15、React 19、TypeScript |
| 后端 | FastAPI、Python 3.11+、PydanticAI |
| 桌面端 | Electron、Rust（SQLite 执行 sidecar） |
| 数据引擎 | DuckDB（文件处理）、原生数据库适配器 |

<details>
<summary><strong>配置参考</strong></summary>

### 支持模型

ReceiptBI 支持 OpenAI 兼容格式、Anthropic、DeepSeek、Ollama 以及自定义网关。

### 数据连接

- CSV、XLS、XLSX、Parquet 和 JSON 文件通过本地 DuckDB 处理
- SQLite、MySQL 和 PostgreSQL 数据库仅支持只读查询


</details>

<details>
<summary><strong>本地开发</strong></summary>

### 工作区管理

使用提供的 `start.sh` 进行标准 Web 开发：
```bash
./start.sh              # 启动前后端服务
./start.sh setup        # 安装依赖
./start.sh stop         # 停止服务
./start.sh test         # 运行测试
```

### 桌面端

桌面端基于 Electron 构建，并打包了一个 Rust sidecar 用于执行只读 SQLite 查询。
具体的打包配置请参考 `apps/desktop/electron-builder.yml`。

</details>

## 开源协议

MIT

## 历史版本

| 版本 | 基于 | 分支 |
|------|------|------|
| v2 | [gptme](https://github.com/gptme/gptme) | [v2](https://github.com/MoonMao42/ReceiptBI/tree/v2) |
| v1 | [open interpreter 0.4.3](https://github.com/OpenInterpreter/open-interpreter) | [v1](https://github.com/MoonMao42/ReceiptBI/tree/v1) |
