import { describe, expect, it } from "vitest";

import {
  getChartPalette,
  normalizeChartSpec,
  RECEIPTBI_CHART_PALETTES,
} from "@/lib/charts";

describe("ChartSpec v1", () => {
  it("preserves validated v1 bindings instead of guessing from row order", () => {
    const spec = normalizeChartSpec({
      version: 1,
      type: "bar",
      title: "月度销售",
      data_ref: { result_name: "monthly_sales", result_hash: "hash-1" },
      encoding: {
        x: { field: "month", label: "月份", kind: "temporal" },
        y: [
          {
            field: "sales",
            label: "销售额",
            kind: "number",
            aggregate: "sum",
            format: "currency",
          },
        ],
      },
      presentation: {
        orientation: "vertical",
        stack: "normal",
        palette: "categorical",
      },
      data: [
        { misleading_label: "华东", misleading_number: 999, month: "一月", sales: 12 },
        { misleading_label: "华南", misleading_number: 888, month: "二月", sales: 18 },
      ],
    });

    expect(spec).toMatchObject({
      version: 1,
      type: "bar",
      data_ref: { result_name: "monthly_sales", result_hash: "hash-1" },
      encoding: {
        x: { field: "month", label: "月份", kind: "temporal" },
        y: [
          {
            field: "sales",
            label: "销售额",
            aggregate: "sum",
            format: "currency",
          },
        ],
      },
      presentation: { stack: "none", palette: "categorical" },
    });
  });

  it("rejects invalid v1 field bindings instead of falling back to another column", () => {
    expect(
      normalizeChartSpec({
        version: 1,
        type: "line",
        encoding: {
          x: { field: "missing_month" },
          y: [{ field: "missing_sales" }],
        },
        presentation: {},
        data: [{ month: "一月", sales: 12 }],
      }),
    ).toBeNull();
  });

  it("accepts only system palettes and never consumes model-authored colors", () => {
    const spec = normalizeChartSpec({
      version: 1,
      type: "area",
      encoding: { x: { field: "month" }, y: [{ field: "sales" }] },
      presentation: {
        palette: ["#ffffff", "#000000"],
        colors: ["#ff00ff"],
      },
      colors: ["#ff0000"],
      data: [{ month: "一月", sales: 12 }],
    });

    expect(spec?.presentation.palette).toBe("receiptbi");
    expect(getChartPalette("receiptbi")).toEqual(
      RECEIPTBI_CHART_PALETTES.receiptbi,
    );
    expect(spec).not.toHaveProperty("colors");
    expect(spec?.presentation).not.toHaveProperty("colors");
  });

  it("adapts historical xKey and yKeys without widening them to every number", () => {
    const spec = normalizeChartSpec({
      type: "bar",
      title: "区域收入",
      xKey: "region",
      yKeys: ["revenue"],
      stack: true,
      data: [
        { region: "华东", revenue: 120, internal_id: 9001 },
        { region: "华南", revenue: 80, internal_id: 9002 },
      ],
    });

    expect(spec?.encoding.x?.field).toBe("region");
    expect(spec?.encoding.y.map((item) => item.field)).toEqual(["revenue"]);
    expect(spec?.presentation.stack).toBe("none");
  });

  it("uses a narrow compatibility fallback only for legacy payloads", () => {
    const spec = normalizeChartSpec({
      type: "pie",
      data: [
        { name: "华东", value: 120, internal_id: 9001 },
        { name: "华南", value: 80, internal_id: 9002 },
      ],
    });

    expect(spec?.encoding.x?.field).toBe("name");
    expect(spec?.encoding.y.map((item) => item.field)).toEqual(["value"]);
  });

  it("forces horizontal_bar to use horizontal orientation", () => {
    const spec = normalizeChartSpec({
      version: 1,
      type: "horizontal_bar",
      encoding: { x: { field: "region" }, y: [{ field: "revenue" }] },
      presentation: {
        orientation: "vertical",
        stack: "none",
        palette: "monochrome",
      },
      data: [{ region: "华东", revenue: 120 }],
    });

    expect(spec?.presentation).toEqual({
      orientation: "horizontal",
      stack: "none",
      palette: "monochrome",
    });
  });

  it("removes unsupported orientation and stacking from non-bar chart types", () => {
    for (const type of ["line", "pie", "scatter"] as const) {
      const spec = normalizeChartSpec({
        version: 1,
        type,
        encoding: {
          x: { field: "month" },
          y: [{ field: "sales" }, { field: "profit" }],
        },
        presentation: {
          orientation: "horizontal",
          stack: "percent",
          palette: "receiptbi-muted",
        },
        data: [{ month: "一月", sales: 12, profit: 3 }],
      });

      expect(spec?.presentation).toEqual({
        orientation: "vertical",
        stack: "none",
        palette: "receiptbi-muted",
      });
      expect(spec?.encoding.y).toHaveLength(
        type === "pie" || type === "scatter" ? 1 : 2,
      );
    }
  });

  it("keeps only the rendered series for legacy pie and scatter payloads", () => {
    for (const type of ["pie", "scatter"] as const) {
      const spec = normalizeChartSpec({
        type,
        xKey: "region",
        yKeys: ["revenue", "profit"],
        orientation: "horizontal",
        stack: true,
        data: [{ region: "华东", revenue: 120, profit: 20 }],
      });

      expect(spec?.encoding.y.map((item) => item.field)).toEqual(["revenue"]);
      expect(spec?.presentation.orientation).toBe("vertical");
      expect(spec?.presentation.stack).toBe("none");
    }
  });

  it("does not keep stacking for a single-series bar or area", () => {
    for (const type of ["bar", "area"] as const) {
      const spec = normalizeChartSpec({
        version: 1,
        type,
        encoding: { x: { field: "month" }, y: [{ field: "sales" }] },
        presentation: {
          orientation: "horizontal",
          stack: "percent",
          palette: "receiptbi",
        },
        data: [{ month: "一月", sales: 12 }],
      });
      expect(spec?.presentation.stack).toBe("none");
      expect(spec?.presentation.orientation).toBe(
        type === "bar" ? "horizontal" : "vertical",
      );
    }
  });
});
