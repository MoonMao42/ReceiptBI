import type { ReactNode } from "react";
import { render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";

import { ChartDisplay } from "@/components/chat/ChartDisplay";
import type { ChartSpec } from "@/lib/charts";
import messages from "@/messages/zh.json";

function renderChart(spec: ChartSpec) {
  return render(
    <NextIntlClientProvider locale="zh" messages={messages}>
      <ChartDisplay spec={spec} />
    </NextIntlClientProvider>
  );
}

vi.mock("recharts", () => {
  const Container = ({ children }: { children?: ReactNode }) => <>{children}</>;
  const Element = ({ children }: { children?: ReactNode }) => <>{children}</>;
  return {
    Area: Element,
    AreaChart: Container,
    Bar: ({ dataKey, name, stackId, fill }: Record<string, unknown>) => (
      <i
        data-testid={`bar-${String(dataKey)}`}
        data-name={String(name)}
        data-stack={String(stackId || "")}
        data-fill={String(fill)}
      />
    ),
    BarChart: ({ children, layout, stackOffset }: Record<string, unknown>) => (
      <div
        data-testid="bar-chart"
        data-layout={String(layout)}
        data-stack-offset={String(stackOffset)}
      >
        {children as ReactNode}
      </div>
    ),
    CartesianGrid: Element,
    Cell: Element,
    Legend: Element,
    Line: Element,
    LineChart: Container,
    Pie: Element,
    PieChart: Container,
    ResponsiveContainer: Container,
    Scatter: Element,
    ScatterChart: Container,
    Tooltip: ({ formatter }: Record<string, unknown>) => {
      const format = formatter as
        | ((value: number, name: string, item: { dataKey: string }) => unknown[])
        | undefined;
      const formatted = format?.(120, "收入", { dataKey: "revenue" });
      return (
        <span data-testid="tooltip-value">
          {Array.isArray(formatted) ? String(formatted[0]) : ""}
        </span>
      );
    },
    XAxis: Element,
    YAxis: Element,
  };
});

const horizontalSpec: ChartSpec = {
  version: 1,
  type: "horizontal_bar",
  title: "区域收入",
  data_ref: { result_name: "region_revenue", result_hash: "hash-1" },
  encoding: {
    x: { field: "region", label: "区域", kind: "category" },
    y: [
      {
        field: "revenue",
        label: "收入",
        kind: "number",
        format: "currency",
      },
      {
        field: "refund",
        label: "退款",
        kind: "number",
        format: "currency",
      },
    ],
  },
  presentation: {
    orientation: "horizontal",
    stack: "normal",
    palette: "monochrome",
  },
  data: [
    { region: "华东", revenue: 120, refund: 20 },
    { region: "华南", revenue: 80, refund: 10 },
  ],
};

describe("ChartDisplay", () => {
  it("renders the declared orientation, series, stacking, and approved palette", () => {
    renderChart(horizontalSpec);

    expect(screen.getByTestId("bar-chart")).toHaveAttribute(
      "data-layout",
      "vertical",
    );
    expect(screen.getByTestId("bar-revenue")).toHaveAttribute(
      "data-name",
      "收入",
    );
    expect(screen.getByTestId("bar-revenue")).toHaveAttribute(
      "data-stack",
      "series",
    );
    expect(screen.getByTestId("bar-revenue")).toHaveAttribute(
      "data-fill",
      "#0f4b3f",
    );
    expect(screen.getByTestId("bar-refund")).toHaveAttribute(
      "data-fill",
      "#166451",
    );
  });

  it("exposes a concise summary and the exact plotted values as an accessible table", () => {
    renderChart(horizontalSpec);

    expect(
      screen.getByRole("img", {
        name: /区域收入，横向柱状图，按区域展示，指标为收入和退款，共 2 条记录/,
      }),
    ).toBeInTheDocument();

    const table = screen.getByRole("table", { name: /区域收入，横向柱状图/ });
    expect(within(table).getByRole("columnheader", { name: "区域" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "收入" })).toBeInTheDocument();
    expect(within(table).getByRole("rowheader", { name: "华东" })).toBeInTheDocument();
    expect(within(table).getByText("¥120.00")).toBeInTheDocument();
    expect(within(table).getByText("¥20.00")).toBeInTheDocument();
  });

  it("keeps the declared value format when a series has a display label", () => {
    renderChart(horizontalSpec);

    expect(screen.getByTestId("tooltip-value")).toHaveTextContent("¥120.00");
  });
});
