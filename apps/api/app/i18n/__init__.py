"""Backend i18n support for user-visible SSE messages."""

from __future__ import annotations

LANG = {"en", "zh"}

MESSAGES: dict[str, dict[str, str]] = {
    "zh": {
        "progress.start": "开始处理请求...",
        "progress.context_ready": "执行上下文已准备",
        "progress.analyzing": "正在分析...",
        "progress.routing": "正在路由...",
        "progress.generating_sql": "正在生成 SQL...",
        "progress.executing": "正在执行...",
        "progress.processing": "正在处理...",
        "progress.visualizing": "正在生成图表...",
        "progress.summarizing": "正在总结...",
        "progress.restore_saved_steps": "正在恢复上次已保存的调查步骤",
        "progress.understand_data": "正在理解数据和业务口径",
        "progress.confirmation_required": "有一个会影响结论的业务口径需要确认",
        "progress.check_saved_method": "正在按已保存的方法核对当前数据",
        "progress.investigate": "正在调查数据并核对结论",
        "progress.project_context_checked": "已检查当前项目的数据和业务口径",
        "progress.prepare_materials": "正在按真实数据结构整理调查所需资料",
        "progress.read_database": "正在读取与问题相关的数据库资料",
        "progress.read_files": "正在读取与问题相关的文件资料",
        "progress.validate_results": "正在验证最终结果",
        "progress.relate_sources": "正在关联不同来源的数据",
        "progress.aggregate_results": "正在汇总关键结果",
        "progress.check_confirmed_definitions": "正在按已确认的业务口径核对数据",
        "progress.render_chart": "正在生成并核对结果图",
        "progress.validate_relationships": "正在核对数据之间的关联是否可靠",
        "progress.supplemental_analysis": "正在执行补充分析",
        "progress.prepare_capabilities": "正在准备这次分析需要的能力",
        "progress.record_understanding": "正在记录可复用的业务理解",
        "progress.more_data_required": "还需要补充少量相关数据才能继续",
        "progress.complete_report": "调查完成，正在整理报告",
        "progress.business_explanation_unavailable": "数据结果已经核对，业务解释未能补充",
        "analysis.confirmation_title": "需要确认一个业务口径",
        "analysis.confirmation_action": "确认业务口径",
        "analysis.confirmation_heading": "需要你确认",
        "analysis.preflight_refund_question": "计算收入时，退款订单需要扣除吗？",
        "analysis.preflight_refund_reason": "数据同时包含金额和退款字段，不同口径会改变收入结论。",
        "analysis.preflight_excel_question": "这次分析应该使用哪个工作表？",
        "analysis.preflight_excel_question_selected": "这次先分析工作表“{sheet}”，是否正确？",
        "analysis.preflight_excel_reason": "文件里有多个工作表，选择不同工作表可能改变分析范围。",
        "analysis.fallback_title": "已验证的数据结果",
        "analysis.fallback_summary": "系统已经保存并核对当前表格结果。模型未能补充业务解释，因此这里仅展示可核对的数据证据。",
        "analysis.fallback_table_shape": "已验证的表格包含 {rows} 行、{columns} 列。",
        "analysis.fallback_columns": "可核对字段：{columns}。",
        "analysis.fallback_more_columns": "{columns}等 {count} 个字段",
        "analysis.fallback_evidence": "最终表格内容、行数和字段均与本次校验记录一致。",
        "error.not_found": "对话不存在",
        "error.cancelled": "查询已取消",
        "error.execution": "执行出错",
        "stop.sent": "查询停止请求已发送",
        "stop.not_found": "没有找到正在执行的查询",
    },
    "en": {
        "progress.start": "Processing request...",
        "progress.context_ready": "Execution context ready",
        "progress.analyzing": "Analyzing...",
        "progress.routing": "Routing...",
        "progress.generating_sql": "Generating SQL...",
        "progress.executing": "Executing...",
        "progress.processing": "Processing...",
        "progress.visualizing": "Generating chart...",
        "progress.summarizing": "Summarizing...",
        "progress.restore_saved_steps": "Restoring the saved investigation steps",
        "progress.understand_data": "Understanding the data and business definitions",
        "progress.confirmation_required": "A business definition that affects the conclusion needs confirmation",
        "progress.check_saved_method": "Checking current data with the saved analysis method",
        "progress.investigate": "Investigating the data and verifying the findings",
        "progress.project_context_checked": "Project data and business definitions checked",
        "progress.prepare_materials": "Preparing the investigation materials from the real data structure",
        "progress.read_database": "Reading the relevant database data",
        "progress.read_files": "Reading the relevant file data",
        "progress.validate_results": "Validating the final results",
        "progress.relate_sources": "Relating data from different sources",
        "progress.aggregate_results": "Summarizing the key results",
        "progress.check_confirmed_definitions": "Checking data with the confirmed business definitions",
        "progress.render_chart": "Generating and checking the result chart",
        "progress.validate_relationships": "Checking whether the data relationships are reliable",
        "progress.supplemental_analysis": "Running the additional analysis",
        "progress.prepare_capabilities": "Preparing the capabilities needed for this investigation",
        "progress.record_understanding": "Recording reusable business understanding",
        "progress.more_data_required": "A small amount of related data is still needed to continue",
        "progress.complete_report": "Investigation complete; preparing the report",
        "progress.business_explanation_unavailable": "Data verified; the business explanation could not be completed",
        "analysis.confirmation_title": "A business definition needs confirmation",
        "analysis.confirmation_action": "Confirm business definition",
        "analysis.confirmation_heading": "Confirmation needed",
        "analysis.preflight_refund_question": "Should refunded orders be deducted when calculating revenue?",
        "analysis.preflight_refund_reason": "The data contains both amount and refund fields, so the selected definition can change the revenue result.",
        "analysis.preflight_excel_question": "Which worksheet should this analysis use?",
        "analysis.preflight_excel_question_selected": "Should this analysis use the “{sheet}” worksheet?",
        "analysis.preflight_excel_reason": "This file contains multiple worksheets, and choosing a different worksheet can change the analysis scope.",
        "analysis.fallback_title": "Verified data result",
        "analysis.fallback_summary": "The current table result was saved and verified. The model could not complete the business explanation, so only reviewable data evidence is shown here.",
        "analysis.fallback_table_shape": "The verified table contains {rows} {row_unit} and {columns} {column_unit}.",
        "analysis.fallback_columns": "Reviewable fields: {columns}.",
        "analysis.fallback_more_columns": "{columns}, {count} fields total",
        "analysis.fallback_evidence": "The final table contents, row count, and fields match this investigation's validation record.",
        "error.not_found": "Conversation not found",
        "error.cancelled": "Query cancelled",
        "error.execution": "Execution error",
        "stop.sent": "Stop request sent",
        "stop.not_found": "No active query found",
    },
}


def _t(key: str, lang: str) -> str:
    """Translate a key to the requested language."""

    if lang not in LANG:
        lang = "zh"
    return MESSAGES[lang].get(key, MESSAGES["zh"].get(key, key))


def t(key: str, lang: str = "zh", **values: object) -> str:
    """Translate a message key."""

    message = _t(key, lang)
    return message.format(**values) if values else message


def get_progress_message(stage: str, lang: str = "zh") -> str:
    """Get a localized progress message for a given stage."""

    key = f"progress.{stage}"
    message = _t(key, lang)
    return _t("progress.processing", lang) if message == key else message
