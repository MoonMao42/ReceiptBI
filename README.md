<div align="center">

<img src="docs/images/receiptbi-icon.png" width="144" alt="ReceiptBI logo">

# ReceiptBI

**把 CSV、Excel 和只读数据库变成可核查、可编辑的业务报表。**

用自然语言调查数据，保留结论依据，再把确认过的结果整理成报表。

[下载桌面版](https://github.com/MoonMao42/ReceiptBI/releases/latest) · [用示例数据试一遍](#用示例数据试一遍) · [English](README.en.md)

[![CI](https://github.com/MoonMao42/ReceiptBI/actions/workflows/ci.yml/badge.svg)](https://github.com/MoonMao42/ReceiptBI/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/MoonMao42/ReceiptBI?label=release)](https://github.com/MoonMao42/ReceiptBI/releases/latest)
[![License](https://img.shields.io/github/license/MoonMao42/ReceiptBI)](LICENSE)

</div>

![查看报表分页并进入编辑布局](docs/images/demo/receiptbi-report-demo.gif)

ReceiptBI 会把问题、使用的数据、生成的图表和结论留在同一次调查中。你也可以把已经确认的结果继续整理成一份报表。

## 用示例数据试一遍

1. 安装 [ReceiptBI 桌面版](https://github.com/MoonMao42/ReceiptBI/releases/latest)，或从源码启动。
2. 下载仓库中的 [咖啡零售订单示例](examples/retail/orders.csv)。
3. 在设置中选择模型服务，然后把示例文件加入项目。
4. 输入下面的问题：

> 请分析最近一个月的销售额、毛利和退款，并按地区和渠道比较。


## 下载

当前桌面版本为 [ReceiptBI 1.0.0](https://github.com/MoonMao42/ReceiptBI/releases/tag/v1.0.0)。

| 系统 | 安装包 |
|---|---|
| macOS，Apple 芯片 | [下载 DMG](https://github.com/MoonMao42/ReceiptBI/releases/download/v1.0.0/ReceiptBI-1.0.0-mac-arm64.dmg) |
| macOS，Intel 芯片 | [下载 DMG](https://github.com/MoonMao42/ReceiptBI/releases/download/v1.0.0/ReceiptBI-1.0.0-mac-x64.dmg) |
| Windows x64 | [下载安装程序](https://github.com/MoonMao42/ReceiptBI/releases/download/v1.0.0/ReceiptBI-1.0.0-win-x64.exe) |

安装包校验值见 [SHA256SUMS](https://github.com/MoonMao42/ReceiptBI/releases/download/v1.0.0/SHA256SUMS)。

<details>
<summary><strong>macOS 首次打开</strong></summary>

1. 打开 DMG，将 ReceiptBI 拖入“应用程序”。
2. 当前 1.0.0 版本尚未签名。如果 macOS 阻止首次打开，请运行：

```bash
xattr -cr /Applications/ReceiptBI.app
```

</details>

### 自然对话

每次调查都保留最初的问题、相关数据、发现、图表和后续工作。

![包含核心指标、关键发现和图表的数据调查](docs/images/zh/workspace-analysis.png)

### 业务定义智能识别

表的用途、字段含义、指标和关系按数据来源保存。表级定义只在所属表内生效；跨表分析时，再按照已经确认的关系组合使用。

![按数据表查看和治理业务定义](docs/images/zh/semantic-governance.png)

### 调查结果可以做成报表

选择一次调查，核对建议的内容和顺序，再生成报表草稿。报表支持继续编辑、翻页、预览和导出

![将一次调查整理为报表前的内容确认](docs/images/zh/report-organizing.png)

### 预览分页

预览会显示实际分页位置。指标、图表和来源在打印或导出后仍然保持清楚。

![多页报表的打印预览](docs/images/zh/report-print-preview.png)

<div align="center">

**如果 ReceiptBI 已经帮你少做一次手工拼表，欢迎点个 Star。**

[⭐ Star ReceiptBI](https://github.com/MoonMao42/ReceiptBI)

</div>

## 工作方式

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

确认过的数据准备步骤和业务定义可以继续使用。数据更新但结构不变时，可以沿用同一套口径重新调查和刷新报表。

## 支持范围

| 内容 | 当前支持 |
|---|---|
| 文件 | CSV、XLS、XLSX、Parquet、JSON |
| 数据库 | SQLite、MySQL、PostgreSQL，只读连接 |
| 模型服务 | OpenAI 兼容接口、Anthropic、DeepSeek、Ollama、自定义网关 |
| 报表内容 | 指标、文本、表格、图表、来源和多页预览 |

## 从源码运行

macOS 和 Linux 需要 Python 3.11+ 与 Node.js LTS：

```bash
git clone https://github.com/MoonMao42/ReceiptBI.git
cd ReceiptBI
./start.sh
```

也可以使用 Docker：

```bash
docker compose up --build
```

打开 `http://localhost:3000`，选择模型服务，然后添加数据。

<details>
<summary><strong>开发说明</strong></summary>

### 常用命令

```bash
./start.sh              # 启动前后端
./start.sh setup        # 安装依赖
./start.sh stop         # 停止服务
./start.sh test         # 运行测试
```

### 技术栈

| 部分 | 技术 |
|---|---|
| 前端 | Next.js 15、React 19、TypeScript |
| 后端 | FastAPI、Python 3.11+、PydanticAI |
| 桌面端 | Electron、Rust |
| 数据处理 | DuckDB、原生数据库适配器 |

</details>

## 参与项目

- [提交问题](https://github.com/MoonMao42/ReceiptBI/issues/new/choose)
- [参与讨论](https://github.com/MoonMao42/ReceiptBI/discussions)
- [贡献指南](CONTRIBUTING.md)
- [安全策略](SECURITY.md)
- [行为准则](CODE_OF_CONDUCT.md)

## 历史版本

| 版本 | 基于 | 分支 |
|---|---|---|
| v2 | [gptme](https://github.com/gptme/gptme) | [v2](https://github.com/MoonMao42/ReceiptBI/tree/v2) |
| v1 | [Open Interpreter 0.4.3](https://github.com/OpenInterpreter/open-interpreter) | [v1](https://github.com/MoonMao42/ReceiptBI/tree/v1) |

## 开源协议

[MIT](LICENSE)
