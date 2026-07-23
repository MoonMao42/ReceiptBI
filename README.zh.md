<div align="center">

<img src="docs/images/receiptbi-icon.png" width="200" alt="ReceiptBI logo">

与你的数据对话。专为凌乱文件和只读数据库打造的本地优先分析工具。

[English](README.md) | [中文](README.zh.md)

</div>

## 功能特点

- **对话式分析** — 用自然语言提问，由 ReceiptBI 安全地查询、关联并分析数据
- **数据清洗与准备** — 提供可视化的文件清洗功能，非破坏性地处理类型和异常值
- **可治理的业务语义** — 将已确认的业务背景、指标、维度和表关系放在它们真正适用的数据层级下
- **可编辑报告** — 将对话分析结果转化为持久可验证的图表、指标和报告页面

## 工作原理

```mermaid
flowchart LR
    data["凌乱文件 / 数据库"] --> prep["清洗与特征提取"]
    prep --> semantic["语义层理解"]
    semantic --> ask["自然语言提问"]
    ask --> run["执行 SQL / Python"]
    run --> validate["结果验证"]
    validate -->|需要修复| run
    validate --> report["生成带证据支持的报告"]
```

## 产品一览

### 从一个业务问题开始调查

ReceiptBI 把问题、依据、发现、图表和后续调查放在同一个工作区里。

![包含核心指标、关键发现和图表的数据调查报告](docs/images/zh/workspace-analysis.png)

### 把调查结果整理成可编辑报表

先选择调查并核对整理方案，再生成草稿；你已经手动编辑的报表内容不会被直接覆盖。

![将一次调查智能整理为报表前的来源确认](docs/images/zh/report-organizing.png)

### 预览并导出分页报表

报表采用稳定的页面布局，让指标、图表和核查依据在打印或导出时仍然清楚。

![多页报表的打印预览](docs/images/zh/report-print-preview.png)

### 让业务定义留在它真正适用的数据下面

业务背景按照“项目 → 数据来源 → 表”组织。只有进入已经确认的范围后，模型才能采用该层级的指标与维度，避免把其他表里的同名字段混在一起。

![按数据表分层治理的业务语义](docs/images/zh/semantic-governance.png)

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/MoonMao42/ReceiptBI.git
cd ReceiptBI
```

### 2. 运行项目

**macOS / Linux** — 需要 Python 3.11+ 和 Node.js LTS：

```bash
./start.sh
```

或者使用 Docker：

```bash
docker compose up --build
```

**Windows** — 推荐使用 Docker Desktop，或在 WSL2 环境下执行 `./start.sh`。提供了基于 Electron 的桌面客户端支持。

### 3. 配置使用

打开 `http://localhost:3000`：

1. 进入设置页面，配置你偏好的模型服务（支持 OpenAI 兼容接口、Anthropic、DeepSeek、Ollama 等）
2. 上传文件（CSV/XLSX/Parquet/JSON）或连接数据库（SQLite/MySQL/PostgreSQL）
3. 开始探索你的数据

## 技术栈

- **前端**: Next.js 15, React 19, TypeScript
- **后端**: FastAPI, Python 3.11+, PydanticAI
- **桌面端**: Electron, Rust（用于 SQLite 安全执行的 Sidecar）
- **数据引擎**: DuckDB（文件处理）, 原生数据库适配器

<details>
<summary><strong>配置参考</strong></summary>

### 支持模型
支持 OpenAI 兼容格式、Anthropic、DeepSeek、Ollama 以及自定义网关。

### 数据连接
- **文件**: CSV, XLS, XLSX, Parquet, JSON（通过本地 DuckDB 处理）
- **数据库**: SQLite, MySQL, PostgreSQL（仅限只读执行）

### 环境变量
- `RECEIPTBI_BACKEND_HOST`: 后端监听地址（默认：127.0.0.1）
- `RECEIPTBI_BACKEND_RELOAD`: 开启后端热更新
- `RECEIPTBI_SQLITE_EXECUTOR_PATH`: Rust SQLite sidecar 路径（桌面端使用）

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
桌面端基于 Electron 构建，并打包了一个 Rust sidecar 用于安全执行 SQLite 查询。
具体的打包配置请参考 `apps/desktop/electron-builder.yml`。

</details>

## 已知限制

- 系统严格限制对数据库进行只读操作，写入语句将被拦截
- Python 分析执行依赖本地环境，并在项目级别进行隔离
- 桌面端打包（如 macOS 签名、Windows 安装程序）目前仍处于开发者预览阶段

## 开源协议

MIT

## 历史版本

| 版本 | 基于 | 分支 |
|------|------|------|
| v2 | [gptme](https://github.com/ErikBjare/gptme) | [v2](https://github.com/MoonMao42/ReceiptBI/tree/v2) |
| v1 | 初代架构 | [v1](https://github.com/MoonMao42/ReceiptBI/tree/v1) |
