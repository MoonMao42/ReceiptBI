"""Prompt builders used by the chat execution engine."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.i18n import t

from typing import Any


def build_initial_messages(
    *,
    query: str,
    system_prompt: str,
    db_context: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    messages = [{"role": "system", "content": system_prompt}]

    if db_context:
        messages.append({"role": "system", "content": db_context})

    if history:
        for message in history:
            if message.get("role") in {"user", "assistant"} and message.get("content"):
                messages.append({"role": message["role"], "content": message["content"]})

    messages.append({"role": "user", "content": query})
    return messages


def build_sql_repair_prompt(
    query: str,
    failed_sql: str | None,
    error_message: str,
    lang: str = "zh",
) -> str:
    from app.i18n import t

    no_sql = t("repair.no_sql", lang)
    sql_block = failed_sql or no_sql
    return f"""{t("repair.sql.title", lang)}

{t("repair.sql.original_query", lang)}
{query}

{t("repair.sql.failed", lang)}
```sql
{sql_block}
```

{t("repair.sql.error", lang)}
{error_message}

{t("repair.sql.requirements", lang)}
{t("repair.sql.req1", lang)}
{t("repair.sql.req2", lang)}
{t("repair.sql.req3", lang)}
{t("repair.sql.req4", lang)}
"""


def build_missing_sql_prompt(query: str, lang: str = "zh") -> str:
    from app.i18n import t

    return f"""{t("repair.missing.title", lang)}

{t("repair.missing.original_query", lang)}
{query}

{t("repair.missing.requirements", lang)}
{t("repair.missing.req1", lang)}
{t("repair.missing.req2", lang)}
{t("repair.missing.req3", lang)}
"""


def build_python_repair_prompt(
    *,
    query: str,
    failed_sql: str | None,
    failed_python: str | None,
    error_message: str,
    available_python_libraries: list[str],
    lang: str = "zh",
) -> str:
    from app.i18n import t

    no_sql = t("repair.no_sql", lang)
    no_python = t("repair.no_python", lang)
    sql_block = failed_sql or no_sql
    python_block = failed_python or no_python
    libraries = ", ".join(available_python_libraries)
    return f"""{t("repair.python.title", lang)}

{t("repair.python.original_query", lang)}
{query}

{t("repair.python.current_sql", lang)}
```sql
{sql_block}
```

{t("repair.python.failed_python", lang)}
```python
{python_block}
```

{t("repair.python.error", lang)}
{error_message}

{t("repair.python.requirements", lang)}
{t("repair.python.req1", lang)}
{t("repair.python.req2", lang)}
{t("repair.python.req3", lang).format(libraries=libraries)}
{t("repair.python.req4", lang)}
"""


def build_repair_messages(
    *,
    query: str,
    system_prompt: str,
    previous_content: str,
    repair_prompt: str,
    db_context: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    messages = build_initial_messages(
        query=query,
        system_prompt=system_prompt,
        db_context=db_context,
        history=history,
    )
    messages.append({"role": "assistant", "content": previous_content})
    messages.append({"role": "user", "content": repair_prompt})
    return messages


def build_db_context(db_config: dict[str, Any], schema_info: str, lang: str = "zh") -> str:
    """Build database context injected into the model prompt."""
    from app.i18n import t

    driver = db_config.get("driver", "mysql")
    db_type_label = t("db_context.type", lang) if lang == "en" else "类型"
    db_label = t("db_context.database", lang) if lang == "en" else "数据库"
    schema_label = t("db_context.schema", lang) if lang == "en" else "数据库表结构"
    instruction = t("db_context.instruction", lang) if lang == "en" else "请根据用户的问题生成合适的 SQL 查询语句。"
    rules_title = t("db_context.rules_title", lang) if lang == "en" else "重要规则:"
    rule1 = t("db_context.rule1", lang) if lang == "en" else "只生成只读 SQL (SELECT, SHOW, DESCRIBE)"
    rule2 = t("db_context.rule2", lang) if lang == "en" else "使用 ```sql 代码块包裹 SQL 语句"
    rule3 = t("db_context.rule3", lang) if lang == "en" else "必须使用上面提供的真实表名和字段名，不要猜测"
    rule4 = t("db_context.rule4", lang) if lang == "en" else "简洁明了地解释查询结果"

    return f"""
{db_type_label}: {driver}
{db_label}: {db_config.get("database", "")}

{schema_label}:
{schema_info}

{instruction}
{rules_title}
1. {rule1}
2. {rule2}
3. {rule3}
4. {rule4}
"""
