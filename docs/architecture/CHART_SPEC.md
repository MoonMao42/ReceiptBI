# ChartSpec v1

ReceiptBI stores a library-independent chart description. The model may recommend a chart and bind fields, but it never supplies renderer code, arbitrary colors, or trusted rows.

```json
{
  "version": 1,
  "type": "bar",
  "title": "月度销售趋势",
  "data_ref": {
    "result_name": "monthly_sales",
    "result_hash": "system-owned"
  },
  "encoding": {
    "x": {
      "field": "month",
      "label": "月份",
      "kind": "temporal"
    },
    "y": [
      {
        "field": "total_sales",
        "label": "销售额",
        "aggregate": "sum",
        "format": "currency"
      }
    ]
  },
  "presentation": {
    "orientation": "vertical",
    "stack": "none",
    "palette": "receiptbi"
  },
  "data": []
}
```

## Contract

- `type` is one of `bar`, `horizontal_bar`, `line`, `area`, `pie`, or `scatter`.
- `data_ref` and `data` are system-owned. The API replaces model-authored rows with the current validated result and records its stable hash.
- `encoding.x` and every `encoding.y` field must exist in the bound result. Measures must contain finite numeric values; scatter plots also require a numeric X field.
- `presentation.stack` is `none`, `normal`, or `percent`. Stacking is retained only for `bar`, `horizontal_bar`, and `area` charts with at least two measures; other combinations are canonicalized to `none`.
- `horizontal_bar` is always horizontal. Only bar charts retain a horizontal orientation; the other chart families are canonicalized to vertical.
- `pie` and `scatter` use one measure. Additional measures are discarded by the compatibility boundary instead of being silently advertised but not rendered.
- `presentation.palette` is one of `receiptbi`, `receiptbi-muted`, `categorical`, or `monochrome`. Raw color arrays and renderer options are rejected.
- New clients render declared field bindings exactly. Column guessing exists only in the one-way adapter for historical saved charts.
- Manual report edits can change chart family, axes, series names and formats, stacking, labels, and an approved palette without changing the retained investigation provenance or metric meaning.

The current React renderer uses Recharts behind this contract. A future renderer may be added as an adapter without changing stored ChartSpec documents.
