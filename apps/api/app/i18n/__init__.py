"""Backend i18n support for SSE messages and repair prompts."""

from __future__ import annotations

LANG = {"en", "zh"}


def _t(key: str, lang: str) -> str:
    """Translate a key to the requested language."""
    if lang not in LANG:
        lang = "zh"
    return MESSAGES[lang].get(key, MESSAGES["zh"].get(key, key))


# SSE progress messages
MESSAGES: dict[str, dict[str, str]] = {
    "zh": {
        # SSE progress
        "progress.start": "开始处理请求...",
        "progress.context_ready": "执行上下文已准备",
        "progress.analyzing": "正在分析...",
        "progress.routing": "正在路由...",
        "progress.generating_sql": "正在生成 SQL...",
        "progress.executing": "正在执行...",
        "progress.processing": "正在处理...",
        "progress.visualizing": "正在生成图表...",
        "progress.summarizing": "正在总结...",
        # SSE error
        "error.not_found": "对话不存在",
        "error.cancelled": "查询已取消",
        "error.execution": "执行出错",
        # SSE stop
        "stop.sent": "查询停止请求已发送",
        "stop.not_found": "没有找到正在执行的查询",
        # Repair prompts
        "repair.sql.title": "上一步生成的 SQL 无法执行，请修复后重新给出完整答复。",
        "repair.sql.original_query": "原始问题：",
        "repair.sql.failed": "失败 SQL：",
        "repair.sql.error": "数据库错误：",
        "repair.sql.requirements": "要求：",
        "repair.sql.req1": "1. 必须基于已提供的真实表结构和字段名修复。",
        "repair.sql.req2": "2. 返回完整答复，并且必须包含一个新的 ```sql 代码块。",
        "repair.sql.req3": "3. 如果原先的分析、图表或 Python 思路仍有效，可以保留；否则一起修正。",
        "repair.sql.req4": "4. 只给最终版本，不要给多个候选 SQL。",
        "repair.missing.title": "上一步回答没有提供可执行的 SQL，请重新给出完整答复。",
        "repair.missing.original_query": "原始问题：",
        "repair.missing.requirements": "要求：",
        "repair.missing.req1": "1. 必须包含一个 ```sql 代码块。",
        "repair.missing.req2": "2. SQL 只能使用已提供的真实表和字段。",
        "repair.missing.req3": "3. 可以保留必要的分析说明，但不要省略 SQL。",
        "repair.python.title": "上一步 Python 执行失败，请修复后重新给出完整答复。",
        "repair.python.original_query": "原始问题：",
        "repair.python.current_sql": "当前 SQL：",
        "repair.python.failed_python": "失败 Python：",
        "repair.python.error": "Python 错误：",
        "repair.python.requirements": "要求：",
        "repair.python.req1": "1. 若 SQL 无需修改，请保留原 SQL；若确实有问题，也一并修正。",
        "repair.python.req2": "2. 如果还需要 Python 分析，必须返回新的 ```python 代码块。",
        "repair.python.req3": "3. 代码只能使用这些当前可用库：{libraries}，并直接使用已注入的 df。",
        "repair.python.req4": "4. 不要访问文件、网络或系统资源。",
        "repair.no_sql": "未生成 SQL",
        "repair.no_python": "未提供 Python",
        "repair.analytics_not_installed_zh": "当前未安装高级分析扩展，不要使用 `sklearn`、`scipy`、`seaborn`。",
        "db_context.type": "类型",
        "db_context.database": "数据库",
        "db_context.schema": "数据库表结构",
        "db_context.instruction": "请根据用户的问题生成合适的 SQL 查询语句。",
        "db_context.rules_title": "重要规则:",
        "db_context.rule1": "只生成只读 SQL (SELECT, SHOW, DESCRIBE)",
        "db_context.rule2": "使用 ```sql 代码块包裹 SQL 语句",
        "db_context.rule3": "必须使用上面提供的真实表名和字段名，不要猜测",
        "db_context.rule4": "简洁明了地解释查询结果",
        # Diagnostic messages
        "diag.model_failed": "模型生成失败: {error}",
        "diag.model_retry": "模型调用失败，正在自动重试。",
        "diag.missing_sql_retry": "模型回复缺少可执行 SQL，正在自动补全。",
        "diag.no_executable_sql": "模型没有生成可执行 SQL。",
        "diag.sql_auto_complete": "已触发 SQL 自动补全。",
        "diag.sql_success": "SQL 执行成功，返回 {count} 行。",
        "diag.sql_failed": "SQL 执行失败: {error}",
        "diag.sql_repair": "SQL 失败可恢复，正在自动修复并重试。",
        "diag.python_disabled": "Python 分析已在设置中关闭，已跳过 Python 执行。",
        "diag.python_done": "Python 分析执行完成。",
        "diag.python_failed": "Python 执行失败: {error}",
        "diag.python_repair": "Python 失败可恢复，正在自动修复并重试。",
        "diag.chart_generated": "已按模型提供的图表配置生成可视化。",
        "diag.chart_fallback": "模型图表配置无效，已回退到自动图表生成。",
        "diag.analysis_done": "分析完成",
        "diag.cancelled": "查询已取消",
    },
    "en": {
        # SSE progress
        "progress.start": "Processing request...",
        "progress.context_ready": "Execution context ready",
        "progress.analyzing": "Analyzing...",
        "progress.routing": "Routing...",
        "progress.generating_sql": "Generating SQL...",
        "progress.executing": "Executing...",
        "progress.processing": "Processing...",
        "progress.visualizing": "Generating chart...",
        "progress.summarizing": "Summarizing...",
        # SSE error
        "error.not_found": "Conversation not found",
        "error.cancelled": "Query cancelled",
        "error.execution": "Execution error",
        # SSE stop
        "stop.sent": "Stop request sent",
        "stop.not_found": "No active query found",
        # Repair prompts
        "repair.sql.title": "The SQL generated in the previous step failed to execute. Please fix and provide a complete response.",
        "repair.sql.original_query": "Original question:\n",
        "repair.sql.failed": "Failed SQL:\n",
        "repair.sql.error": "Database error:\n",
        "repair.sql.requirements": "Requirements:\n",
        "repair.sql.req1": "1. Fix based on the actual table structures and column names provided.",
        "repair.sql.req2": "2. Provide a complete response with a new ```sql code block.",
        "repair.sql.req3": "3. Keep the previous analysis, chart, or Python approach if still valid; otherwise fix them too.",
        "repair.sql.req4": "4. Only provide the final version, not multiple candidate SQLs.",
        "repair.missing.title": "The previous response did not include executable SQL. Please provide a complete response.",
        "repair.missing.original_query": "Original question:\n",
        "repair.missing.requirements": "Requirements:\n",
        "repair.missing.req1": "1. Must include a ```sql code block.",
        "repair.missing.req2": "2. SQL can only use the actual tables and columns provided.",
        "repair.missing.req3": "3. You may keep analysis explanations, but do not omit the SQL.",
        "repair.python.title": "The Python execution in the previous step failed. Please fix and provide a complete response.",
        "repair.python.original_query": "Original question:\n",
        "repair.python.current_sql": "Current SQL:\n",
        "repair.python.failed_python": "Failed Python:\n",
        "repair.python.error": "Python error:\n",
        "repair.python.requirements": "Requirements:\n",
        "repair.python.req1": "1. Keep the original SQL if it doesn't need changes; fix it along with Python if needed.",
        "repair.python.req2": "2. If Python analysis is still needed, provide a new ```python code block.",
        "repair.python.req3": "3. Only use these available libraries: {libraries}. Use the injected `df` directly.",
        "repair.python.req4": "4. Do not access files, network, or system resources.",
        "repair.no_sql": "No SQL generated",
        "repair.no_python": "No Python provided",
        "repair.analytics_not_installed_zh": "Advanced analytics extras are not installed, so do not use `sklearn`, `scipy`, or `seaborn`.",
        "db_context.type": "Type",
        "db_context.database": "Database",
        "db_context.schema": "Database Schema",
        "db_context.instruction": "Generate appropriate SQL queries based on the user's question.",
        "db_context.rules_title": "Important Rules:",
        "db_context.rule1": "Only generate read-only SQL (SELECT, SHOW, DESCRIBE)",
        "db_context.rule2": "Wrap SQL statements in ```sql code blocks",
        "db_context.rule3": "Use the actual table and column names provided above; do not guess",
        "db_context.rule4": "Explain the query results concisely and clearly",
        # Diagnostic messages
        "diag.model_failed": "Model generation failed: {error}",
        "diag.model_retry": "Model call failed, auto-retrying.",
        "diag.missing_sql_retry": "Model response missing executable SQL, auto-completing.",
        "diag.no_executable_sql": "Model did not generate executable SQL.",
        "diag.sql_auto_complete": "SQL auto-complete triggered.",
        "diag.sql_success": "SQL executed successfully, returned {count} rows.",
        "diag.sql_failed": "SQL execution failed: {error}",
        "diag.sql_repair": "SQL failure is recoverable, auto-repairing.",
        "diag.python_disabled": "Python analysis disabled in settings, skipped.",
        "diag.python_done": "Python analysis completed.",
        "diag.python_failed": "Python execution failed: {error}",
        "diag.python_repair": "Python failure is recoverable, auto-repairing.",
        "diag.chart_generated": "Chart generated from model config.",
        "diag.chart_fallback": "Model chart config invalid, fell back to auto-chart.",
        "diag.analysis_done": "Analysis complete",
        "diag.cancelled": "Query cancelled",
    },
}


def t(key: str, lang: str = "zh") -> str:
    """Translate a message key to the requested language."""
    return _t(key, lang)


def get_progress_message(stage: str, lang: str = "zh") -> str:
    """Get a localized progress message for a given stage."""
    key = f"progress.{stage}"
    msg = _t(key, lang)
    # Fallback to the stage name itself if not found
    if msg == key:
        return stage.replace("_", " ").title()
    return msg
