# ReceiptBI API 参考

> 本文记录当前维护的项目、调查、模型与连接接口。完整请求字段以运行时 OpenAPI 为准；产品边界见 [`../STATUS.md`](../STATUS.md)。

> 注: 当前应用已全面收口为**单工作区、本地优先、无账号密码认证**模式。旧版多用户认证和 JWT 接口已完全移除。

## 基础信息

- **Base URL**: `http://localhost:8000/api/v1`
- **认证方式**: 无（本地优先访问）
- **内容类型**: `application/json`

---

## 通用响应格式

### 成功响应

```json
{
  "success": true,
  "data": { ... },
  "message": "操作成功"
}
```

### 错误响应

```json
{
  "success": false,
  "error": {
    "code": "NOT_FOUND",
    "message": "资源不存在",
    "details": { ... }
  }
}
```

## 当前项目工作区关键接口

下面列出当前 `projects.py` 中与数据可信链直接相关的接口；完整字段仍以运行时 OpenAPI 为准。

| 方法 | 路径 | 当前合同 |
|---|---|---|
| `POST` | `/projects/{project_id}/sources/{source_id}/preflight` | 文件生成非破坏性工作副本；数据库读取可用的 PK/FK/unique/nullability 目录并执行有预算、只读且脱敏的值画像，声明外键仍是待验证依据 |
| `GET` | `/projects/{project_id}/recipes` | 列出当前项目的整理方法及其 active revision |
| `GET` | `/projects/{project_id}/recipe-templates` | 列出从 ProjectBundle 导入、尚未自动绑定的数据整理方法及可选择的文件来源 |
| `POST` | `/projects/{project_id}/recipe-templates/{template_id}/preview` | 在可丢弃目录中试运行导入方法；返回业务化前后规模和问题，不改 source、recipe 或正式预检记录 |
| `POST` | `/projects/{project_id}/recipe-templates/{template_id}/bind` | 重新运行并核对原文件、当前工作副本、recipe head、template head 和输出证明；一致时才追加修订并切换分析副本 |
| `POST` | `/projects/{project_id}/recipes/{recipe_id}/reapply` | 只重放现有整理方法；不会把待确认漂移视作用户接受 |
| `POST` | `/projects/{project_id}/sources/{source_id}/accept-replacement` | 用户明确接受待确认的新一期版本，并把上一可信版本保留为历史 |
| `POST` | `/projects/{project_id}/recipes/{recipe_id}/undo` | 撤销当前整理；若存在上一可信版本则恢复它为运行时当前来源 |
| `GET` | `/projects/{project_id}/recipes/{recipe_id}/revisions` | 按新到旧查看整理方法的不可变修订历史；缺失或破损的 active head 会拒绝继续 |
| `POST` | `/projects/{project_id}/recipes/{recipe_id}/revisions/{revision_id}/restore` | 用 `expected_active_revision_id` 做并发检查并追加一个恢复修订；只切换方法 head，重新应用后才影响当前分析 |
| `POST` | `/projects/{project_id}/corrections` | 记录报告纠正；类型可为业务判断、指标、筛选、关系或解释，默认仅作用于本次运行 |
| `GET` | `/projects/{project_id}/analysis-runs/{run_id}/correction-targets` | 返回已完成报告中可安全纠正的业务项及 opaque `target_ref`；不返回内部语义 key |
| `GET` | `/projects/{project_id}/knowledge/{entry_id}/revisions` | 查看某项项目理解的不可变版本历史 |
| `POST` | `/projects/{project_id}/knowledge/{entry_id}/revisions/{revision_id}/restore` | 以新版本恢复旧定义，不改写历史 |
| `GET` | `/projects/{project_id}/analysis-playbooks` | 列出项目中的可复用分析方法及其 `schema_version`、`execution_mode` 和结构指纹 |
| `POST` | `/projects/{project_id}/analysis-playbooks` | 从一份已完成且仍新鲜的调查提取 AnalysisPlaybook v3；只保存逻辑来源角色、类型化意图和校验合同，不把旧结果当作新结果 |
| `DELETE` | `/projects/{project_id}/analysis-playbooks/{playbook_id}` | 删除一项可复用分析方法 |
| `GET` | `/projects/{project_id}/export` | 导出 ProjectBundle v3；包含完整语义与整理方法修订历史，不包含可假定为可移植的来源文件 |
| `POST` | `/projects/import` | 导入 ProjectBundle v1/v2/v3；v3 整理历史按新 ID 重建为未绑定模板，不会自动执行 |

报告修正目标只从已完成运行中的系统执行证据产生，并绑定原运行和当时的语义 active revision。普通客户端提交 `target_ref`，显式空值表示“整体结论 / 其他”并且不会触发旧式单目标推断；跨运行、篡改、失效或落后于当前语义版本的引用返回冲突。关系纠正只有在当前纠正运行中通过关联验收、真实 Join 到达最终结果并在 Join 后重新校验，才会成为普通运行可复用的关系。可复用证明必须绑定两端明确的 source/table，并来自完整、未截断的系统检查；筛选、聚合、派生或表级血缘不明的结果只构成本次运行证据。数据库声明的外键只是目录证据；预检的行数和分布也是抽样画像，不是精确全表统计。整理历史的“恢复”只恢复方法定义，不会偷偷替换当前报告使用的工作数据。导入方法的 preview 也只是一次隔离试运行；bind 必须携带并重新核对预览时的状态，普通界面不会展示这些内部指纹。

AnalysisPlaybook v3 明确区分两种执行模式。`system_structured_query` 只用于“一个逻辑来源 + 一个严格类型化查询 + 一个最终校验、且没有隐藏语义或关系副作用”的方法；运行时会把它重新绑定到当前唯一来源，核对 schema，重新编译只读查询、执行并校验，再生成不含 SQL 的 `analysis_playbook_execution` 回执。回执绑定 playbook id/shape、当前 source id/schema、计划哈希、结果哈希、画像和最终校验；高级工具依据仍可保留真实查询，但回执本身不携带 SQL。复杂、未知、包含原始 SQL/Python/Join/多步变换的方法以及所有 v2 方法都使用 `agent_replan_required`。这表示 Agent 必须依据当前数据重新规划，不表示旧 SQL、Python 或结果会被自动复跑。

---

## 1. 聊天 API

### GET /chat/stream
SSE 流式调查接口。Agent 可按任务自主选择结构化查询、原始只读查询、Python、关系检查和结果验证；它不是固定的 `SQL -> Python -> 图表` 阶段机，也不强制每次生成图表。

**查询参数**

| 参数 | 类型 | 必填 | 描述 |
|---|---|---|---|
| `query` | string | ✅ | 自然语言问题描述 |
| `model` | string | ❌ | 指定模型配置 ID，缺省时使用全局默认模型 |
| `conversation_id` | string | ❌ | 关联对话 UUID，不传则自动创建新会话 |
| `connection_id` | string | ❌ | 关联的数据库连接 ID，缺省时使用全局默认连接 |
| `language` | string | ❌ | 语言种类 ('zh' 或 'en')，默认 'zh' |
| `context_rounds` | int | ❌ | 上下文轮数 (1-20)，默认从全局设置读取 |

**SSE 事件类型及格式**

事件通过标准 EventStream 返回，每个事件的 data 为 JSON。

- `event: progress` — 进度更新
  ```json
  {"type": "progress", "data": {"stage": "start", "message": "正在初始化...", "conversation_id": "..."}}
  {"type": "progress", "data": {"stage": "context_ready", "message": "上下文装载完毕", "conversation_id": "...", "execution_context": {...}}}
  ```
- `event: thinking` — 模型思考步骤
  ```json
  {"type": "thinking", "data": {"stage": "sql_generating", "detail": "..."}}
  ```
- `event: result` — SQL 执行结果或生成的代码
  ```json
  {"type": "result", "data": {"content": "查询到以下数据", "sql": "SELECT ...", "data": [...], "rows_count": 10, "execution_time": 0.12}}
  ```
- `event: python_output` — Python 执行控制台输出
  ```json
  {"type": "python_output", "data": {"output": "DataFrame shape: ...", "stream": "stdout"}}
  ```
- `event: python_image` — Python matplotlib 绘制的图表 Base64 编码
  ```json
  {"type": "python_image", "data": {"image": "iVBORw0KG...", "format": "png"}}
  ```
- `event: visualization` — 前端结构化图表渲染配置
  ```json
  {"type": "visualization", "data": {"chart": {"type": "bar", "data": [...], "xKey": "name", "yKeys": ["value"], "title": "图表标题"}}}
  ```
- `event: error` — 执行过程中的错误中断
  ```json
  {"type": "error", "data": {"code": "EXECUTION_ERROR", "message": "错误详情..."}}
  ```
- `event: done` — 执行完毕标志
  ```json
  {"type": "done", "data": {"conversation_id": "...", "message_id": "..."}}
  ```

### POST /chat/stop
停止当前会话正在执行中的 SSE 流或 AI 工作流。

**请求体**
```json
{
  "conversation_id": "uuid"
}
```

### GET /chat/{conversation_id}/messages
分页获取指定对话的消息列表。

**查询参数**

| 参数 | 类型 | 必填 | 描述 |
|---|---|---|---|
| `cursor` | string | ❌ | ISO 时间戳游标，用于获取该时间之前的历史消息 |
| `limit` | int | ❌ | 返回数量限制（1-100），默认 50 |

---

## 2. 对话历史 API

### GET /conversations
获取有至少2条消息的对话列表。

**查询参数**

| 参数 | 类型 | 描述 |
|---|---|---|
| `limit` | int | 返回数量，默认 20 |
| `offset` | int | 偏移量，默认 0 |
| `favorites` | bool | 仅返回标记收藏的对话 |
| `q` | string | 过滤标题关键词 |

### GET /conversations/{conversation_id}
获取单个对话的详细信息及其下的全部消息。

### DELETE /conversations/{conversation_id}
物理删除该对话以及关联的所有历史消息。

### POST /conversations/{conversation_id}/favorite
切换对话的收藏状态（收藏/取消收藏）。

---

## 3. 工作区设置 API

### GET /settings
获取工作区全局设置（默认模型、默认连接、上下文轮数、分析/诊断/修复开关）。

**响应示例**
```json
{
  "success": true,
  "data": {
    "default_model_id": "uuid",
    "default_connection_id": "uuid",
    "context_rounds": 5,
    "python_enabled": true,
    "diagnostics_enabled": true,
    "auto_repair_enabled": true
  }
}
```

### PUT /settings
更新工作区全局设置。

**请求体**
```json
{
  "default_model_id": "uuid",
  "default_connection_id": "uuid",
  "context_rounds": 5,
  "python_enabled": true,
  "diagnostics_enabled": true,
  "auto_repair_enabled": true
}
```

---

## 4. 模型配置 API

### GET /config/models
获取已配置的 LLM 模型列表。

### POST /config/models
添加新的大模型配置。

**请求体**
```json
{
  "name": "GPT-4o",
  "provider": "openai",
  "model_id": "gpt-4o",
  "base_url": "https://api.openai.com/v1",
  "api_key": "sk-...",
  "is_default": true,
  "extra_options": {}
}
```

### PUT /config/models/{model_id}
修改现有 LLM 配置。

### DELETE /config/models/{model_id}
删除指定的 LLM 配置。

### POST /config/models/{model_id}/test
使用简单提示词发起请求，测试模型配置连通性。

---

## 5. 数据库连接 API

### GET /config/connections
获取所有数据库连接。

### POST /config/connections
新增数据库连接。

**请求体**
```json
{
  "name": "Operations warehouse",
  "driver": "sqlite",
  "host": null,
  "port": null,
  "username": null,
  "password": null,
  "database": "/path/to/read-only-source.db",
  "is_default": true,
  "extra_options": {}
}
```

### PUT /config/connections/{connection_id}
修改已配置的数据库连接。

### DELETE /config/connections/{connection_id}
删除指定的数据库连接。

### POST /config/connections/{connection_id}/test
测试特定连接的可连接性及版本、包含的表数。

---

## 6. 系统状态 API

### GET /system/capabilities
获取当前的系统能力状态（如 Python 执行沙箱是否可用，及 `scikit-learn`, `scipy`, `seaborn` 等科学计算包的安装就绪情况）。
