"""Shared, conservative field-role inference for semantic recommendations.

Mature semantic layers model entities, dimensions, and measures as distinct
objects.  A column name may support a suggestion, but it must never override
the physical type or an explicit key/time role.  Name matching is therefore
token based: ``sales`` matches ``sales_amount`` but not ``presales_owner``.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

SemanticFieldRole = Literal["identifier", "time", "measure", "dimension"]
SEMANTIC_ROLE_INFERENCE_VERSION = 3

_IDENTIFIER_TOKENS = frozenset({"id", "key", "code", "uuid", "guid"})
_IDENTIFIER_SUFFIX_TOKENS = frozenset({"number", "no"})
_TIME_TOKENS = frozenset(
    {
        "date",
        "time",
        "datetime",
        "timestamp",
        "year",
        "quarter",
        "month",
        "week",
        "day",
    }
)
_TIMESTAMP_EVENT_TOKENS = frozenset(
    {"created", "updated", "modified", "deleted", "inserted", "loaded"}
)
_TIMESTAMP_SUFFIX_TOKENS = frozenset({"at", "on"})
_MONETARY_TOKENS = frozenset(
    {
        "amount",
        "revenue",
        "sales",
        "gmv",
        "price",
        "cost",
        "profit",
        "margin",
        "refund",
        "discount",
        "paid",
        "payment",
    }
)
_QUANTITATIVE_TOKENS = frozenset(
    {
        *_MONETARY_TOKENS,
        "quantity",
        "qty",
        "count",
        "volume",
        "units",
        "rate",
        "ratio",
        "percent",
        "percentage",
        "pct",
    }
)
_NON_ADDITIVE_TOKENS = frozenset(
    {
        "rank",
        "ranking",
        "status",
        "sequence",
        "seq",
        "latitude",
        "longitude",
        "lat",
        "lon",
        "lng",
        "balance",
        "inventory",
        "stock",
        "headcount",
    }
)
_REFUND_TOKENS = frozenset({"refund", "refunded", "return", "returned"})
_AVERAGE_TOKENS = frozenset(
    {"avg", "average", "mean", "rate", "ratio", "percent", "percentage", "pct"}
)

_COMPACT_IDENTIFIER_NAMES = frozenset(
    {
        "recordid",
        "rowid",
        "uuid",
        "guid",
        "编号",
        "编码",
        "单号",
        "序号",
        "标识",
        "客户编号",
        "订单编号",
        "订单号",
        "商品编号",
        "产品编号",
        "用户编号",
        "客户编码",
        "商品编码",
        "产品编码",
    }
)
_COMPACT_TIME_NAMES = frozenset(
    {
        "createdat",
        "updatedat",
        "orderdate",
        "transactiondate",
        "eventdate",
        "eventtime",
        "日期",
        "时间",
        "年度",
        "年份",
        "季度",
        "月份",
        "下单日期",
        "订单日期",
        "创建时间",
        "更新时间",
        "交易时间",
        "支付时间",
    }
)
_COMPACT_MONETARY_NAMES = frozenset(
    {
        "amount",
        "revenue",
        "sales",
        "salesamount",
        "gmv",
        "price",
        "unitprice",
        "priceperunit",
        "cost",
        "unitcost",
        "costperunit",
        "profit",
        "grossprofit",
        "netamount",
        "grossamount",
        "refundamount",
        "discountamount",
        "paidamount",
        "paymentamount",
        "金额",
        "销售额",
        "营收",
        "收入",
        "实付",
        "实付金额",
        "应付金额",
        "支付金额",
        "订单金额",
        "商品金额",
        "价格",
        "单价",
        "成本",
        "利润",
        "毛利",
        "退款金额",
        "优惠金额",
        "折扣金额",
    }
)
_COMPACT_QUANTITATIVE_NAMES = frozenset(
    {
        *_COMPACT_MONETARY_NAMES,
        "quantity",
        "qty",
        "count",
        "数量",
        "销量",
        "销售量",
        "件数",
        "订单数",
        "客户数",
        "用户数",
        "退款率",
        "毛利率",
        "转化率",
    }
)
_COMPACT_AVERAGE_NAMES = frozenset(
    {
        "unitprice",
        "priceperunit",
        "unitcost",
        "costperunit",
        "averagesales",
        "平均值",
        "平均销售额",
        "均价",
        "比率",
        "比例",
        "退款率",
        "毛利率",
        "转化率",
    }
)

_COMPACT_REFUND_NAMES = frozenset(
    {
        "refund",
        "refunded",
        "return",
        "returned",
        "退款",
        "退款金额",
        "退款状态",
        "是否退款",
        "退货",
        "退货金额",
        "退货状态",
        "是否退货",
    }
)


def normalized_field_name(value: object) -> str:
    """Return a stable compact form for exact alias matching."""

    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", normalized)


def field_name_tokens(value: object) -> tuple[str, ...]:
    """Split snake/kebab/space/camel names without splitting inside words."""

    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", text)
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
    return tuple(
        token.casefold() for token in re.findall(r"[A-Za-z]+|[0-9]+|[\u4e00-\u9fff]+", text)
    )


def has_identifier_semantics(value: object) -> bool:
    tokens = field_name_tokens(value)
    compact = normalized_field_name(value)
    return (
        bool(set(tokens) & _IDENTIFIER_TOKENS)
        or bool(tokens and tokens[-1] in _IDENTIFIER_SUFFIX_TOKENS)
        or compact in _COMPACT_IDENTIFIER_NAMES
    )


def has_time_semantics(value: object) -> bool:
    tokens = field_name_tokens(value)
    compact = normalized_field_name(value)
    return (
        bool(set(tokens) & _TIME_TOKENS)
        or compact in _COMPACT_TIME_NAMES
        or (
            len(tokens) >= 2
            and tokens[-1] in _TIMESTAMP_SUFFIX_TOKENS
            and tokens[-2] in _TIMESTAMP_EVENT_TOKENS
        )
    )


def has_monetary_semantics(value: object) -> bool:
    tokens = set(field_name_tokens(value))
    compact = normalized_field_name(value)
    return bool(tokens & _MONETARY_TOKENS) or compact in _COMPACT_MONETARY_NAMES


def has_quantitative_semantics(value: object) -> bool:
    """Return whether a name explicitly denotes an aggregatable value.

    Numeric storage alone is not enough: ranks, statuses, coordinates, and
    snapshot values are numeric dimensions until a user defines their intended
    aggregation.
    """

    tokens = set(field_name_tokens(value))
    compact = normalized_field_name(value)
    if tokens & _NON_ADDITIVE_TOKENS or {"head", "count"} <= tokens:
        return False
    return bool(tokens & _QUANTITATIVE_TOKENS) or compact in _COMPACT_QUANTITATIVE_NAMES


def has_refund_semantics(value: object) -> bool:
    tokens = set(field_name_tokens(value))
    compact = normalized_field_name(value)
    return bool(tokens & _REFUND_TOKENS) or compact in _COMPACT_REFUND_NAMES


def infer_semantic_field_role(
    value: object,
    *,
    is_numeric: bool,
    is_datetime: bool,
    mostly_numeric: bool = False,
    is_grain: bool = False,
) -> SemanticFieldRole:
    """Infer a candidate role with type evidence as the measure hard gate."""

    if has_identifier_semantics(value):
        return "identifier"
    if is_datetime or has_time_semantics(value):
        return "time"
    if is_grain:
        return "identifier"
    if (is_numeric or mostly_numeric) and has_quantitative_semantics(value):
        return "measure"
    return "dimension"


def suggested_metric_operation(value: object) -> Literal["sum", "avg"]:
    tokens = set(field_name_tokens(value))
    compact = normalized_field_name(value)
    if tokens & _AVERAGE_TOKENS or compact in _COMPACT_AVERAGE_NAMES:
        return "avg"
    return "sum"
