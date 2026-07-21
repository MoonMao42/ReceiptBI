# ReceiptBI 数据库参考

ReceiptBI 使用一个应用数据库保存本地工作区状态。源码模式默认可使用
`sqlite+aiosqlite:///./data/receiptbi.db`，Docker 开发模式默认使用
`postgresql+asyncpg://postgres:postgres@localhost:5432/receiptbi`。桌面版把数据库放在
`~/.receiptbi-desktop/data/receiptbi.db`，并通过 Alembic 迁移维护结构。

完整字段和约束以 [`apps/api/app/db/tables.py`](../../apps/api/app/db/tables.py) 为准。

## 当前表

| 表 | 用途 |
|---|---|
| `connections` | 用户配置的只读 SQLite、MySQL 或 PostgreSQL 数据源；凭据加密存储 |
| `models` | PydanticAI 使用的模型提供商、模型标识与加密 API 凭据 |
| `conversations` / `messages` | 对话与流式调查历史 |
| `app_settings` | 单工作区默认模型、默认连接与当前执行偏好 |
| `projects` | 项目边界与项目级状态 |
| `project_data_sources` | 项目内文件或数据库来源、工作副本、指纹和画像 |
| `preflight_reports` | 非破坏性预检、结构和有预算的值画像证据 |
| `sanitation_recipes` / `sanitation_recipe_revisions` | 数据整理方法及不可变版本历史 |
| `semantic_entries` / `semantic_entry_revisions` | 项目语义层的候选、确认、锁定知识及不可变版本历史 |
| `analysis_corrections` | 绑定调查证据的用户纠正 |
| `analysis_runs` | 调查状态、报告、检查点和错误 |
| `artifacts` | 表格、图表与其他报告产物及其技术依据 |

## 已退役结构

旧版全局 `prompts`、`semantic_terms`、`table_relationships` 和独立
`metadata.db/schema_layouts` 不再属于运行时。升级时，非示例的旧术语和关系会作为待核对的
项目语义候选迁入 `semantic_entries` 并写入首个 revision；旧提示词只作为 inactive、blocked
归档候选保留，不会进入 Agent system prompt。自动注入的示例数据库及其未确认派生候选会被清理。

## 关键边界

- 项目知识按 `project_id` 隔离；候选不能覆盖 confirmed 或 locked 定义。
- 文件预检生成工作副本，不改写用户选择的原文件。
- 数据库执行路径校验只读语句；生产使用时仍应配置服务器侧只读账号。
- 连接密码和模型 API key 使用本地 `ENCRYPTION_KEY` 加密。数据库、`.env`、
  `encryption.key` 和桌面数据目录都不应上传或分享。
- 迁移链遇到未知、混合或损坏结构时应停止，而不是用 `create_all` 隐藏问题。

更多运行边界见 [`../DATA_AND_PRIVACY.md`](../DATA_AND_PRIVACY.md) 和
[`../STATUS.md`](../STATUS.md)。
