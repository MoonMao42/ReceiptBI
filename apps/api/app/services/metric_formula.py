"""Safe, deterministic metric formulas over retained result rows.

The formula contract deliberately contains data, not code.  It is small enough
to validate recursively and is interpreted with :class:`decimal.Decimal`; no
``eval``, Python snippets, pandas expressions, or model-authored callables are
accepted here.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation, localcontext
from typing import Any, Literal, TypeAlias, TypedDict, cast

MAX_FORMULA_DEPTH = 8
MAX_FORMULA_NODES = 31
MAX_FORMULA_COLUMNS = 8
DECIMAL_PRECISION = 38
MAX_DECIMAL_SCALE = 18
MAX_DECIMAL_DIGITS = 38
MAX_DECIMAL_MAGNITUDE = Decimal("1e28")
_MAX_DECIMAL_CHARACTERS = 128
_MAX_COLUMN_CHARACTERS = 128


class DecimalNode(TypedDict):
    op: Literal["decimal"]
    value: str


class ColumnNode(TypedDict):
    op: Literal["column"]
    name: str


class NegateNode(TypedDict):
    op: Literal["negate"]
    operand: MetricExpression


class BinaryNode(TypedDict):
    op: Literal["add", "subtract", "multiply", "divide"]
    left: MetricExpression
    right: MetricExpression


MetricExpression: TypeAlias = DecimalNode | ColumnNode | NegateNode | BinaryNode


class MetricFormulaAction(TypedDict):
    kind: Literal["metric_formula"]
    output_column: str
    expression: MetricExpression
    evaluation_order: Literal["row_then_aggregate"]
    null_policy: Literal["propagate", "zero", "error"]
    divide_by_zero: Literal["error", "null"]


DecimalAggregateOperation = Literal["sum", "average", "min", "max"]


def _stable_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _rows_hash(rows: Sequence[Mapping[str, Any]]) -> str:
    serialized = sorted(
        json.dumps(dict(row), sort_keys=True, ensure_ascii=False, default=str) for row in rows
    )
    return hashlib.sha256("\n".join(serialized).encode("utf-8")).hexdigest()


def canonical_decimal_string(value: Decimal | int | float | str) -> str:
    """Return the sole JSON representation accepted for a finite Decimal.

    Scientific notation, insignificant zeroes, and negative zero are removed.
    A modest character bound prevents a source value such as ``1e1000000`` from
    expanding into an unbounded string during evidence generation.
    """

    if isinstance(value, bool):
        raise ValueError("布尔值不能作为公式数值")
    raw = str(value).strip()
    if not raw or len(raw) > _MAX_DECIMAL_CHARACTERS:
        raise ValueError("公式数值为空或过长")
    try:
        decimal_value = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError("公式包含无效数值") from exc
    if not decimal_value.is_finite():
        raise ValueError("公式只支持有限数值")
    if abs(decimal_value) >= MAX_DECIMAL_MAGNITUDE:
        raise ValueError("公式数值超出安全幅度")
    if decimal_value.is_zero():
        return "0"
    # Fixed-point output is deterministic and never depends on locale.
    rendered = format(decimal_value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    if len(rendered) > _MAX_DECIMAL_CHARACTERS:
        raise ValueError("公式数值超出受支持范围")
    unsigned = rendered.lstrip("-")
    integer, _, fraction = unsigned.partition(".")
    significant_digits = len((integer.lstrip("0") + fraction).lstrip("0")) or 1
    if significant_digits > MAX_DECIMAL_DIGITS:
        raise ValueError(f"公式数值最多支持 {MAX_DECIMAL_DIGITS} 位有效数字")
    if len(fraction) > MAX_DECIMAL_SCALE:
        raise ValueError(f"公式数值最多支持 {MAX_DECIMAL_SCALE} 位小数")
    return rendered


def _bounded_computed_decimal(value: Decimal) -> Decimal:
    """Round computed division tails, then enforce the public Decimal bounds."""

    scale = max(-value.as_tuple().exponent, 0)
    if scale > MAX_DECIMAL_SCALE:
        quantum = Decimal(1).scaleb(-MAX_DECIMAL_SCALE)
        with localcontext() as context:
            context.prec = DECIMAL_PRECISION
            context.rounding = ROUND_HALF_EVEN
            try:
                value = value.quantize(quantum)
            except InvalidOperation as exc:
                raise ValueError("指标公式结果超出安全精度") from exc
    return Decimal(canonical_decimal_string(value))


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{label}字段不完整或包含额外字段")


def validate_metric_expression(expression: Any) -> tuple[MetricExpression, tuple[str, ...]]:
    """Validate an expression and return it plus its sorted source columns."""

    node_count = 0
    columns: set[str] = set()

    def visit(raw: Any, depth: int) -> MetricExpression:
        nonlocal node_count
        if depth > MAX_FORMULA_DEPTH:
            raise ValueError(f"指标公式最多支持 {MAX_FORMULA_DEPTH} 层")
        node_count += 1
        if node_count > MAX_FORMULA_NODES:
            raise ValueError(f"指标公式最多支持 {MAX_FORMULA_NODES} 个节点")
        if not isinstance(raw, Mapping):
            raise ValueError("指标公式节点必须是对象")
        operation = raw.get("op")
        if operation == "decimal":
            _require_exact_keys(raw, {"op", "value"}, "常量节点")
            value = raw.get("value")
            if not isinstance(value, str) or canonical_decimal_string(value) != value:
                raise ValueError("公式常量必须使用规范十进制字符串")
            return {"op": "decimal", "value": value}
        if operation == "column":
            _require_exact_keys(raw, {"op", "name"}, "字段节点")
            name = raw.get("name")
            if (
                not isinstance(name, str)
                or name != name.strip()
                or not name
                or len(name) > _MAX_COLUMN_CHARACTERS
            ):
                raise ValueError("公式字段名无效")
            columns.add(name)
            if len(columns) > MAX_FORMULA_COLUMNS:
                raise ValueError(f"指标公式最多引用 {MAX_FORMULA_COLUMNS} 个字段")
            return {"op": "column", "name": name}
        if operation == "negate":
            _require_exact_keys(raw, {"op", "operand"}, "取负节点")
            return {"op": "negate", "operand": visit(raw.get("operand"), depth + 1)}
        if operation in {"add", "subtract", "multiply", "divide"}:
            _require_exact_keys(raw, {"op", "left", "right"}, "二元运算节点")
            return {
                "op": cast(Literal["add", "subtract", "multiply", "divide"], operation),
                "left": visit(raw.get("left"), depth + 1),
                "right": visit(raw.get("right"), depth + 1),
            }
        raise ValueError("指标公式包含不支持的运算")

    validated = visit(expression, 1)
    return validated, tuple(sorted(columns))


def validate_metric_formula_action(action: Any) -> MetricFormulaAction:
    """Validate the complete metric-formula action with strict extra rejection."""

    if not isinstance(action, Mapping):
        raise ValueError("指标公式动作必须是对象")
    _require_exact_keys(
        action,
        {
            "kind",
            "output_column",
            "expression",
            "evaluation_order",
            "null_policy",
            "divide_by_zero",
        },
        "指标公式动作",
    )
    if action.get("kind") != "metric_formula":
        raise ValueError("指标公式动作类型无效")
    output_column = action.get("output_column")
    if (
        not isinstance(output_column, str)
        or output_column != output_column.strip()
        or not output_column
        or len(output_column) > _MAX_COLUMN_CHARACTERS
    ):
        raise ValueError("指标公式输出字段无效")
    if action.get("evaluation_order") != "row_then_aggregate":
        raise ValueError("指标公式必须先逐行计算，再执行汇总")
    if action.get("null_policy") not in {"propagate", "zero", "error"}:
        raise ValueError("指标公式空值策略无效")
    if action.get("divide_by_zero") not in {"error", "null"}:
        raise ValueError("指标公式除零策略无效")
    expression, columns = validate_metric_expression(action.get("expression"))
    if output_column in columns:
        raise ValueError("指标公式不能覆盖自己引用的字段")
    return {
        "kind": "metric_formula",
        "output_column": output_column,
        "expression": expression,
        "evaluation_order": "row_then_aggregate",
        "null_policy": cast(Literal["propagate", "zero", "error"], action.get("null_policy")),
        "divide_by_zero": cast(Literal["error", "null"], action.get("divide_by_zero")),
    }


def metric_formula_columns(action: Any) -> tuple[str, ...]:
    validated = validate_metric_formula_action(action)
    _expression, columns = validate_metric_expression(validated["expression"])
    return columns


def _source_decimal(value: Any, *, column: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"字段“{column}”包含非数值")
    try:
        canonical = canonical_decimal_string(value)
        return Decimal(canonical)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"字段“{column}”包含非数值") from exc


def evaluate_metric_expression(
    expression: Any,
    row: Mapping[str, Any],
    *,
    null_policy: Literal["propagate", "zero", "error"],
    divide_by_zero: Literal["error", "null"],
) -> Decimal | None:
    """Interpret one validated expression against one row deterministically."""

    validated, _columns = validate_metric_expression(expression)

    def evaluate(node: MetricExpression) -> Decimal | None:
        operation = node["op"]
        if operation == "decimal":
            return Decimal(node["value"])
        if operation == "column":
            name = node["name"]
            value = row.get(name)
            if value is None or (isinstance(value, str) and not value.strip()):
                if null_policy == "zero":
                    return Decimal(0)
                if null_policy == "propagate":
                    return None
                raise ValueError(f"字段“{name}”包含空值")
            return _source_decimal(value, column=name)
        if operation == "negate":
            operand = evaluate(node["operand"])
            return None if operand is None else _bounded_computed_decimal(-operand)

        left = evaluate(node["left"])
        right = evaluate(node["right"])
        if left is None or right is None:
            return None
        if operation == "divide" and right.is_zero():
            if divide_by_zero == "null":
                return None
            raise ValueError("指标公式发生除零")
        with localcontext() as context:
            context.prec = DECIMAL_PRECISION
            context.rounding = ROUND_HALF_EVEN
            try:
                if operation == "add":
                    result = left + right
                elif operation == "subtract":
                    result = left - right
                elif operation == "multiply":
                    result = left * right
                else:
                    result = left / right
            except (InvalidOperation, ZeroDivisionError) as exc:
                raise ValueError("指标公式计算失败") from exc
        return _bounded_computed_decimal(result)

    return evaluate(validated)


def apply_metric_formula(
    rows: Iterable[Mapping[str, Any]],
    *,
    rule_key: str,
    rule_value: str,
    action: Any,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Add a formula column without changing row count or mutating input rows."""

    key = rule_key.strip()
    selected_value = rule_value.strip()
    if not key or not selected_value:
        raise ValueError("规则标识和规则值不能为空")
    validated = validate_metric_formula_action(action)
    materialized = [dict(row) for row in rows]
    output_column = validated["output_column"]
    if any(output_column in row for row in materialized):
        raise ValueError(f"指标公式输出字段已存在: {output_column}")
    columns = metric_formula_columns(validated)
    if materialized:
        missing_everywhere = [
            column for column in columns if not any(column in row for row in materialized)
        ]
        if missing_everywhere:
            raise ValueError("当前结果缺少指标公式字段: " + "、".join(missing_everywhere))

    output: list[dict[str, Any]] = []
    null_rows = 0
    for row in materialized:
        result = evaluate_metric_expression(
            validated["expression"],
            row,
            null_policy=validated["null_policy"],
            divide_by_zero=validated["divide_by_zero"],
        )
        rendered = None if result is None else canonical_decimal_string(result)
        if rendered is None:
            null_rows += 1
        output.append({**row, output_column: rendered})

    if len(output) != len(materialized):  # pragma: no cover - defensive invariant
        raise RuntimeError("指标公式不能改变结果行数")
    evidence = {
        "kind": "business_rule_application",
        "action_kind": "metric_formula",
        "rule_key": key,
        "rule_value": selected_value,
        # Compatibility fields keep formula receipts consumable by the same
        # completion/golden journal readers as filters and single-column metrics.
        "column": output_column,
        "operator": None,
        "values": [],
        "output_column": output_column,
        "referenced_columns": list(columns),
        "evaluation_order": "row_then_aggregate",
        "null_policy": validated["null_policy"],
        "divide_by_zero": validated["divide_by_zero"],
        "formula_hash": _stable_hash(validated),
        "before_rows": len(materialized),
        "after_rows": len(output),
        "excluded_rows": 0,
        "computed_rows": len(output) - null_rows,
        "null_rows": null_rows,
        "input_hash": _rows_hash(materialized),
        "output_hash": _rows_hash(output),
    }
    return output, evidence


def aggregate_decimal_column(
    rows: Iterable[Mapping[str, Any]],
    *,
    column: str,
    operation: DecimalAggregateOperation,
    null_policy: Literal["propagate", "zero", "error"] = "propagate",
) -> tuple[str | None, dict[str, Any]]:
    """Aggregate a computed Decimal column with stable ordering and evidence."""

    selected_column = column.strip()
    if not selected_column:
        raise ValueError("汇总字段不能为空")
    if operation not in {"sum", "average", "min", "max"}:
        raise ValueError("不支持的十进制汇总方式")
    if null_policy not in {"propagate", "zero", "error"}:
        raise ValueError("十进制汇总空值策略无效")
    materialized = [dict(row) for row in rows]
    if materialized and not any(selected_column in row for row in materialized):
        raise ValueError(f"汇总字段不存在: {selected_column}")

    values: list[Decimal] = []
    null_rows = 0
    for row in materialized:
        value = row.get(selected_column)
        if value is None or (isinstance(value, str) and not value.strip()):
            null_rows += 1
            if null_policy == "error":
                raise ValueError(f"汇总字段“{selected_column}”包含空值")
            if null_policy == "zero":
                values.append(Decimal(0))
            continue
        values.append(_source_decimal(value, column=selected_column))

    result: Decimal | None
    if null_policy == "propagate" and null_rows:
        result = None
    elif not values:
        result = None
    elif operation == "min":
        result = min(values)
    elif operation == "max":
        result = max(values)
    else:
        with localcontext() as context:
            context.prec = DECIMAL_PRECISION
            context.rounding = ROUND_HALF_EVEN
            total = sum(values, start=Decimal(0))
            result = total if operation == "sum" else total / Decimal(len(values))
        result = _bounded_computed_decimal(result)
    rendered = None if result is None else canonical_decimal_string(result)
    evidence = {
        "kind": "decimal_aggregate",
        "column": selected_column,
        "operation": operation,
        "null_policy": null_policy,
        "input_rows": len(materialized),
        "value_rows": len(values),
        "null_rows": null_rows,
        "input_hash": _rows_hash(materialized),
        "result": rendered,
    }
    return rendered, evidence


def aggregate_decimal_metric(
    rows: Iterable[Mapping[str, Any]],
    *,
    value_column: str,
    operation: Literal["sum", "mean", "min", "max"],
    group_by: Iterable[str] = (),
    output_column: str | None = None,
    limit: int = 200,
    null_policy: Literal["propagate", "zero", "error"] = "propagate",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Group and aggregate formula output without converting it to binary float."""

    selected_value = value_column.strip()
    groups = tuple(str(column).strip() for column in group_by)
    if not selected_value or any(not column for column in groups):
        raise ValueError("十进制汇总字段不能为空")
    if len(set(groups)) != len(groups):
        raise ValueError("十进制汇总分组字段不能重复")
    if operation not in {"sum", "mean", "min", "max"}:
        raise ValueError("不支持的十进制分组汇总方式")
    if type(limit) is not int or not 1 <= limit <= 10_000:
        raise ValueError("十进制汇总结果上限必须在 1 到 10000 之间")
    metric_name = (output_column or f"{operation}_{selected_value}").strip()
    if not metric_name or metric_name in groups:
        raise ValueError("十进制汇总输出字段与分组字段冲突")

    materialized = [dict(row) for row in rows]
    if materialized and not any(selected_value in row for row in materialized):
        raise ValueError(f"汇总字段不存在: {selected_value}")
    for column in groups:
        if materialized and not any(column in row for row in materialized):
            raise ValueError(f"分组字段不存在: {column}")

    buckets: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in materialized:
        key = tuple(row.get(column) for column in groups)
        buckets.setdefault(key, []).append(row)
    if not groups and not buckets:
        buckets[()] = []

    ordered_keys = sorted(
        buckets,
        key=lambda key: json.dumps(key, ensure_ascii=False, default=str, separators=(",", ":")),
    )
    output: list[dict[str, Any]] = []
    aggregate_operation: DecimalAggregateOperation = "average" if operation == "mean" else operation
    for key in ordered_keys[:limit]:
        aggregate, _aggregate_evidence = aggregate_decimal_column(
            buckets[key],
            column=selected_value,
            operation=aggregate_operation,
            null_policy=null_policy,
        )
        output.append(
            {
                **{column: value for column, value in zip(groups, key, strict=True)},
                metric_name: aggregate,
            }
        )

    evidence = {
        "kind": "decimal_aggregate",
        "value_column": selected_value,
        "operation": operation,
        "group_by": list(groups),
        "output_column": metric_name,
        "null_policy": null_policy,
        "input_rows": len(materialized),
        "total_groups": len(ordered_keys),
        "returned_groups": len(output),
        "limit": limit,
        "truncated": len(ordered_keys) > limit,
        "input_hash": _rows_hash(materialized),
        "output_hash": _rows_hash(output),
    }
    return output, evidence


_NUMBER_PATTERN = re.compile(r"(?:\d+(?:\.\d*)?|\.\d+)")


class _FormulaParser:
    def __init__(self, text: str, columns: Sequence[str]):
        self.text = text
        self.columns = sorted(set(columns), key=lambda item: (-len(item), item))
        self.position = 0

    def _skip_space(self) -> None:
        while self.position < len(self.text) and self.text[self.position].isspace():
            self.position += 1

    def _take(self, token: str) -> bool:
        self._skip_space()
        if self.text.startswith(token, self.position):
            self.position += len(token)
            return True
        return False

    def _primary(self) -> MetricExpression:
        self._skip_space()
        if self._take("("):
            expression = self._additive()
            if not self._take(")"):
                raise ValueError("指标公式括号不完整")
            return expression
        number = _NUMBER_PATTERN.match(self.text, self.position)
        if number is not None:
            self.position = number.end()
            return {"op": "decimal", "value": canonical_decimal_string(number.group(0))}
        for column in self.columns:
            if self.text.startswith(column, self.position):
                self.position += len(column)
                return {"op": "column", "name": column}
        raise ValueError("指标公式包含未知字段或符号")

    def _unary(self) -> MetricExpression:
        if self._take("-"):
            return {"op": "negate", "operand": self._unary()}
        if self._take("+"):
            return self._unary()
        return self._primary()

    def _multiplicative(self) -> MetricExpression:
        expression = self._unary()
        while True:
            if self._take("*"):
                expression = {
                    "op": "multiply",
                    "left": expression,
                    "right": self._unary(),
                }
            elif self._take("/"):
                expression = {"op": "divide", "left": expression, "right": self._unary()}
            else:
                return expression

    def _additive(self) -> MetricExpression:
        expression = self._multiplicative()
        while True:
            if self._take("+"):
                expression = {
                    "op": "add",
                    "left": expression,
                    "right": self._multiplicative(),
                }
            elif self._take("-"):
                expression = {
                    "op": "subtract",
                    "left": expression,
                    "right": self._multiplicative(),
                }
            else:
                return expression

    def parse(self) -> MetricExpression:
        expression = self._additive()
        self._skip_space()
        if self.position != len(self.text):
            raise ValueError("指标公式包含未知字段或符号")
        return expression


def parse_explicit_metric_formula(
    text: str,
    *,
    known_numeric_columns: Iterable[str],
    existing_columns: Iterable[str],
    null_policy: Literal["propagate", "zero", "error"] = "propagate",
    divide_by_zero: Literal["error", "null"] = "error",
) -> MetricFormulaAction | None:
    """Parse only an exact, unambiguous ``new_column = arithmetic`` statement."""

    normalized = unicodedata.normalize("NFKC", text).strip()
    if normalized.count("=") != 1:
        return None
    output_column, raw_expression = (part.strip() for part in normalized.split("=", 1))
    if (
        not output_column
        or not raw_expression
        or len(output_column) > _MAX_COLUMN_CHARACTERS
        or any(character in output_column for character in "=()+-*/")
    ):
        return None
    existing = [str(column).strip() for column in existing_columns if str(column).strip()]
    normalized_output = unicodedata.normalize("NFKC", output_column).casefold()
    if normalized_output in {
        unicodedata.normalize("NFKC", column).casefold() for column in existing
    }:
        return None
    numeric_columns = [
        str(column).strip() for column in known_numeric_columns if str(column).strip()
    ]
    if not numeric_columns:
        return None
    try:
        expression = _FormulaParser(raw_expression, numeric_columns).parse()
        action = validate_metric_formula_action(
            {
                "kind": "metric_formula",
                "output_column": output_column,
                "expression": expression,
                "evaluation_order": "row_then_aggregate",
                "null_policy": null_policy,
                "divide_by_zero": divide_by_zero,
            }
        )
    except ValueError:
        return None
    # A constant-only expression is not learned from data and is therefore not
    # a useful metric definition for this compiler.
    if not metric_formula_columns(action):
        return None
    return action
