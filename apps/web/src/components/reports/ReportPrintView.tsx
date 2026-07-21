"use client";

import type { CSSProperties } from "react";
import type { ReportBlock, ReportDocument, ReportPage } from "@/lib/reports";
import { ReportBlockCard } from "./ReportBlockCard";
import {
  applyStaticReportFilters,
  type ActiveReportFilter,
  type ReportFilterOperator,
} from "./report-blocks";

const FILTER_OPERATORS = new Set<ReportFilterOperator>([
  "contains",
  "equals",
  "not_equals",
  "greater_than",
  "greater_or_equal",
  "less_than",
  "less_or_equal",
]);

function blockStyle(block: ReportBlock): CSSProperties {
  return {
    "--report-column": `${block.layout.x + 1} / span ${block.layout.w}`,
    "--report-row": `${block.layout.y + 1} / span ${block.layout.h}`,
  } as CSSProperties;
}

function pageFilters(
  page: ReportPage,
  filterValues: Record<string, string>
): ActiveReportFilter[] {
  return page.blocks.flatMap((block) => {
    if (block.block_type !== "filter") return [];
    const field = typeof block.config.field === "string" ? block.config.field : "";
    const operator = block.config.operator;
    const value = filterValues[block.id] || "";
    if (!field || !value.trim()) return [];
    return [
      {
        field,
        operator:
          typeof operator === "string" &&
          FILTER_OPERATORS.has(operator as ReportFilterOperator)
            ? (operator as ReportFilterOperator)
            : "contains",
        value,
      },
    ];
  });
}

const noop = () => undefined;

export function ReportPrintView({
  report,
  filterValues,
}: {
  report: ReportDocument;
  filterValues: Record<string, string>;
}) {
  const pages = [...report.pages].sort(
    (left, right) => left.order_index - right.order_index
  );

  return (
    <section
      className="report-print-view"
      data-testid="report-print-view"
      aria-hidden="true"
    >
      {pages.map((page, pageIndex) => {
        const filters = pageFilters(page, filterValues);
        return (
          <article className="report-print-page" key={page.id}>
            <header className="report-print-header">
              <div>
                <p className="report-print-kicker">{page.title}</p>
                <h1>{report.title}</h1>
                {report.description && <p>{report.description}</p>}
              </div>
              <span>{pageIndex + 1} / {pages.length}</span>
            </header>

            <div className="report-print-grid">
              {page.blocks.map((block) => {
                const displayedBlock = applyStaticReportFilters(block, filters);
                return (
                  <div
                    key={block.id}
                    style={blockStyle(block)}
                    className="report-print-block"
                  >
                    <ReportBlockCard
                      block={displayedBlock}
                      editing={false}
                      selected={false}
                      staticRendering
                      onSelect={noop}
                      onMove={noop}
                      onResize={noop}
                      onDuplicate={noop}
                      onDelete={noop}
                      filterValue={filterValues[block.id] || ""}
                      onFilterValueChange={noop}
                    />
                  </div>
                );
              })}
            </div>
          </article>
        );
      })}
    </section>
  );
}
