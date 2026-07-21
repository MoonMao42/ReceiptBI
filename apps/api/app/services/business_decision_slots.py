"""Stable system-owned identities for material business confirmations.

Models may phrase the same decision differently.  ReceiptBI owns the durable key,
but deliberately uses a tiny explicit registry instead of fuzzy matching that could
merge unrelated business rules.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

REVENUE_REFUND_POLICY = "revenue_refund_policy"

_ALIASES = {
    REVENUE_REFUND_POLICY: REVENUE_REFUND_POLICY,
    "refund_policy": REVENUE_REFUND_POLICY,
    "refund_handling": REVENUE_REFUND_POLICY,
}

_REFUND_SIGNALS = ("refund", "refunded", "退款", "退单")
_REVENUE_SIGNALS = (
    "revenue",
    "income",
    "sales amount",
    "net sales",
    "收入",
    "营收",
    "销售额",
    "实收",
)
_INCLUSION_SIGNALS = (
    "include",
    "exclude",
    "deduct",
    "subtract",
    "reduce",
    "count as",
    "included in",
    "计入",
    "算入",
    "算作",
    "包含",
    "纳入",
    "排除",
    "扣除",
    "冲减",
)


def _normalize_key(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().casefold()).strip("_")
    return normalized or value.strip()


def _contains_any(text: str, signals: Iterable[str]) -> bool:
    return any(signal in text for signal in signals)


def infer_decision_slot(*texts: str | None) -> str | None:
    """Infer a slot only when three independent business signals are present."""

    text = " ".join(value.strip().casefold() for value in texts if value and value.strip())
    if not text:
        return None
    if (
        _contains_any(text, _REFUND_SIGNALS)
        and _contains_any(text, _REVENUE_SIGNALS)
        and _contains_any(text, _INCLUSION_SIGNALS)
    ):
        return REVENUE_REFUND_POLICY
    return None


def canonicalize_decision_key(
    key: str,
    *,
    question: str | None = None,
    reason: str | None = None,
    options: Iterable[str] | None = None,
) -> str:
    """Return a stable known slot, or preserve the caller's unknown key.

    Explicit aliases are safe without prose.  Prose inference is intentionally
    conservative and never uses substring similarity, embeddings, or a model.
    """

    normalized = _normalize_key(key)
    explicit = _ALIASES.get(normalized)
    if explicit is not None:
        return explicit
    inferred = infer_decision_slot(question, reason, *(options or ()))
    return inferred or key.strip()


def same_decision_slot(
    left: str,
    right: str,
    *,
    left_text: str | None = None,
    right_text: str | None = None,
) -> bool:
    return canonicalize_decision_key(left, question=left_text) == canonicalize_decision_key(
        right,
        question=right_text,
    )
