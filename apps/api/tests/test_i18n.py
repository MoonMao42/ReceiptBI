from app.i18n import get_progress_message, t


def test_progress_messages_follow_requested_language_and_hide_unknown_steps():
    assert get_progress_message("read_files", "en") == "Reading the relevant file data"
    assert get_progress_message("read_files", "zh") == "正在读取与问题相关的文件资料"
    assert get_progress_message("internal_future_step", "en") == "Processing..."
    assert get_progress_message("internal_future_step", "zh") == "正在处理..."


def test_backend_messages_format_locale_specific_templates():
    assert t(
        "analysis.fallback_table_shape",
        "en",
        rows=1,
        columns=2,
        row_unit="row",
        column_unit="columns",
    ) == "The verified table contains 1 row and 2 columns."
    assert t(
        "analysis.fallback_table_shape",
        "zh",
        rows=1,
        columns=2,
        row_unit="row",
        column_unit="columns",
    ) == "已验证的表格包含 1 行、2 列。"
