[English](README.md) | [中文](README.zh.md)

<div align="center">

<img src="docs/images/logo.svg" width="400" alt="QueryGPT logo">

### 开源 AI 数据库助手

用自然语言提问，自动生成只读 SQL，获取结果、分析和图表。

[功能特性](#功能特性) | [工作原理](#工作原理) | [快速开始](#快速开始) | [技术栈](#技术栈)

</div>

<img src="docs/images/chat.png" alt="Chat workspace" width="100%">

## 功能特性

<table>
<tr>
<td width="50%">

**自然语言查询**

用自然语言描述你的需求——QueryGPT 会生成并执行只读 SQL，然后返回结构化结果。

</td>
<td width="50%">

**自动分析管道**

查询结果自动流入 Python 分析和图表生成，所以一个问题会得到完整答案。

</td>
</tr>
<tr>
<td>

**语义层**

定义业务术语（GMV、AOV 等），QueryGPT 会自动引用它们，消除查询中的歧义。

</td>
<td>

**Schema 关系图**

通过拖拽可视化连接表定义 JOIN 关系。QueryGPT 会自动选择正确的连接路径。

</td>
</tr>
</table>

## 工作原理

```mermaid
flowchart LR
    query["用自然语言提问"] --> context["使用语义层 + Schema 理解意图"]
    context --> sql["生成只读 SQL"]
    sql --> execute["执行查询"]
    execute --> result["返回结果和摘要"]
    result --> decision{"需要图表或进一步分析吗？"}
    decision -->|需要| python["Python 分析与图表"]
    decision -->|不需要| done["完成"]
    python --> done
    execute -->|SQL 错误| repair_sql["自动修复并重试"]
    sql -->|重试| repair_sql
    python -->|Python 错误| repair_py["自动修复并重试"]
    repair_sql --> sql
    repair_py --> python
```

## 截图

<img src="docs/images/schema.png" alt="Schema relationship view" width="100%">

<p align="center"><strong>Schema 关系图</strong></p>

<br>
<br>

<img src="docs/images/semantic.png" alt="Semantic layer config" width="100%">

<p align="center"><strong>语义层配置</strong></p>

## 快速开始

### 1. 克隆仓库

```bash
git clone git@github.com:MKY508/QueryGPT.git
cd QueryGPT
```

### 2. 选择你的平台

<table>
<tr>
<th width="33%">macOS</th>
<th width="33%">Linux</th>
<th width="33%">Windows</th>
</tr>
<tr>
<td>

**方案 A — 直接运行**

需要 Python 3.11+ 和 Node.js LTS

```bash
./start.sh
```

**方案 B — Docker**

需要 [Docker Desktop](https://www.docker.com/products/docker-desktop/)

```bash
docker compose up --build
```

</td>
<td>

**方案 A — 直接运行**

需要 Python 3.11+ 和 Node.js LTS

```bash
./start.sh
```

**方案 B — Docker**

需要 Docker Engine

```bash
docker compose up --build
```

</td>
<td>

**推荐 — Docker Desktop**

Windows 用户应该使用 Docker。`.bat` / `.ps1` 脚本不再维护。

安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/)，然后：

```bash
docker compose up --build
```

**替代方案 — WSL2**

安装 [WSL2](https://learn.microsoft.com/windows/wsl/install) 后，从 WSL 终端运行 `./start.sh`，就像在 Linux 上一样。

</td>
</tr>
</table>

### 3. 配置并启动

启动后，打开 `http://localhost:3000`：

1. 转到设置页面，添加一个模型（提供商 + API 密钥）
2. 使用内置的演示数据库，或连接你自己的 SQLite / MySQL / PostgreSQL
3. 可选：设置默认模型、默认连接和对话上下文轮数
4. 进入聊天页面，开始提问

> 项目自带内置 SQLite 演示数据库（`demo.db`）。如果没有工作区数据，首次启动时会自动创建一个示例连接。

## 技术栈

**项目**<br>
![License](https://img.shields.io/badge/License-MIT-F7DF1E?style=flat-square)

**前端**<br>
![Next.js](https://img.shields.io/badge/Next.js-15-000000?style=flat-square&logo=next.js&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?style=flat-square&logo=typescript&logoColor=white)
![Zustand](https://img.shields.io/badge/Zustand-5-764ABC?style=flat-square)
![TanStack Query](https://img.shields.io/badge/TanStack_Query-5-FF4154?style=flat-square)

**后端**<br>
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-D71F00?style=flat-square)
![LiteLLM](https://img.shields.io/badge/LiteLLM-latest-blue?style=flat-square)
![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)

**数据库**<br>
![SQLite](https://img.shields.io/badge/SQLite-3-003B57?style=flat-square&logo=sqlite&logoColor=white)
![MySQL](https://img.shields.io/badge/MySQL-8-4479A1?style=flat-square&logo=mysql&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat-square&logo=postgresql&logoColor=white)

<details>
<summary><strong>配置参考</strong></summary>

### 模型

支持 OpenAI 兼容、Anthropic、Ollama 和自定义网关。可配置字段：

| 字段 | 说明 |
|------|------|
| `provider` | 模型提供商 |
| `base_url` | API 端点 |
| `model_id` | 模型标识符 |
| `api_key` | API 密钥（Ollama 或未认证网关可选） |
| `extra headers` | 自定义请求头 |
| `query params` | 自定义查询参数 |
| `api_format` | API 格式 |
| `healthcheck_mode` | 健康检查模式 |

### 数据库

支持 SQLite、MySQL 和 PostgreSQL。系统只执行只读 SQL。

内置 SQLite 演示数据库：
- 路径：`apps/api/data/demo.db`
- 默认连接名称：`Sample Database`

</details>

<details>
<summary><strong>启动脚本</strong></summary>

```bash
./start.sh              # 主机模式：检查环境、安装依赖、初始化数据库、启动前后端
./start.sh setup        # 主机模式：仅安装依赖
./start.sh stop         # 停止主机模式服务
./start.sh restart      # 重启主机模式服务
./start.sh status       # 检查主机模式状态
./start.sh logs         # 查看主机模式日志
./start.sh doctor       # 诊断主机模式环境
./start.sh test all     # 在主机模式下运行所有测试
./start.sh cleanup      # 清理主机模式临时状态
```

安装分析扩展（`scikit-learn`, `scipy`, `seaborn`）：

```bash
./start.sh install analytics
```

可选环境变量：

```bash
QUERYGPT_BACKEND_RELOAD=1 ./start.sh     # 后端热重载
QUERYGPT_BACKEND_HOST=0.0.0.0 ./start.sh # 监听所有接口
```

</details>

<details>
<summary><strong>Docker 开发</strong></summary>

Windows 开发者应该使用 Docker；`start.ps1` / `start.bat` 不再维护。

默认开发栈启动：
- `web`: Next.js 开发服务器（HMR 启用）
- `api`: FastAPI 开发服务器（`--reload`）
- `db`: PostgreSQL 16

```bash
docker-compose up --build               # 在前台启动所有服务
docker-compose up -d --build            # 在后台启动所有服务
docker-compose down                     # 停止并删除容器
docker-compose down -v --remove-orphans # 同时删除数据卷
docker-compose ps                       # 查看状态
docker-compose logs -f api web          # 查看前后端日志
docker-compose restart api web          # 重启前后端
docker-compose up db                    # 仅启动数据库
docker-compose run --rm api ./run-tests.sh
docker-compose run --rm web npm run type-check
docker-compose run --rm web npm test
```

注意：
- 前端默认位置：`http://localhost:3000`
- 后端默认位置：`http://localhost:8000`
- PostgreSQL 暴露在 `localhost:5432`
- 更改依赖后运行 `docker-compose up --build`
- 如果已安装 Docker Compose 插件，用 `docker compose` 替换 `docker-compose`

</details>

<details>
<summary><strong>本地开发（主机模式）</strong></summary>

### 后端

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 前端

```bash
cd apps/web
npm install
npm run dev
```

### 环境变量

后端 `apps/api/.env`：

```env
DATABASE_URL=sqlite+aiosqlite:///./data/querygpt.db
ENCRYPTION_KEY=your-fernet-key
```

前端 `apps/web/.env.local`：

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
# 可选：仅在 Docker / 容器化 Next 重写时需要
# INTERNAL_API_URL=http://api:8000
```

### 测试

```bash
# 前端
cd apps/web && npm run type-check && npm test && npm run build

# 后端
./apps/api/run-tests.sh
```

### GitHub CI 分层

GitHub Actions 分为两层：

- **快速层**：后端 `ruff + mypy (chat/config 主路径) + pytest`，前端 `lint + type-check + vitest + build`
- **集成层**：Docker 全栈、Playwright 冒烟测试、`start.sh` 主机模式冒烟测试、SQLite / PostgreSQL / MySQL 连接测试、使用模拟网关的模型测试

本地运行：

```bash
# Docker 全栈
docker compose -f docker-compose.yml -f docker-compose.ci.yml up -d --build

# 后端集成测试（需要 PostgreSQL / MySQL / 模拟网关环境变量）
cd apps/api && pytest tests/test_config_integration.py -v

# 后端主路径类型检查
cd apps/api && mypy --config-file mypy.ini

# 前端浏览器冒烟测试（应用必须先运行）
cd apps/web && npm run test:e2e
```

</details>

<details>
<summary><strong>部署</strong></summary>

### 后端

仓库包含 [render.yaml](render.yaml) 供 Render Blueprint 直接部署。

### 前端

推荐在 Vercel 部署：

- 根目录：`apps/web`
- 环境变量：`NEXT_PUBLIC_API_URL=<your-api-url>`

</details>

## 已知局限

- 仅允许只读 SQL；写操作被阻止
- 自动修复覆盖 SQL、Python 和图表配置错误（可恢复的）
- `/chat/stop` 按单实例语义工作
- 开发时推荐 Node.js LTS；如果 `next dev` 表现异常，清除 `apps/web/.next`

## 许可证

MIT

---
> Built with ❤️
