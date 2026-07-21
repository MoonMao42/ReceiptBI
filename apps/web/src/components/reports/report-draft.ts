import type { AnalysisArtifact, AnalysisRunSummary } from "@/lib/types/api";
import type { ReportBlock, ReportPage } from "@/lib/reports";
import {
  analysisSummaryToReportBlock,
  artifactToReportBlock,
  createReportPage,
  reflowBlocks,
} from "./report-blocks";

export interface InvestigationReportDraft {
  title: string;
  description: string;
  pages: ReportPage[];
}

function runTitle(run: AnalysisRunSummary): string {
  return run.report.title?.trim() || run.query.trim() || "调查报告";
}

function runSummary(run: AnalysisRunSummary): string {
  return (
    (typeof run.report.summary === "string" && run.report.summary.trim()) ||
    run.query.trim()
  );
}

function withLayout(
  block: ReportBlock,
  layout: Partial<ReportBlock["layout"]>
): ReportBlock {
  return {
    ...block,
    layout: { ...block.layout, ...layout },
  };
}

function hasUserFacingEvidence(artifact: AnalysisArtifact): boolean {
  if (artifact.kind !== "evidence" && artifact.kind !== "file") return false;
  for (const key of ["text", "summary", "description", "value", "message"]) {
    const value = artifact.payload[key];
    if ((typeof value === "string" || typeof value === "number") && String(value).trim()) {
      return true;
    }
  }
  return ["validations", "correction_applications", "evidence", "checks", "items"].some(
    (key) => Array.isArray(artifact.payload[key]) && artifact.payload[key].length > 0
  );
}

function draftPage(
  title: string,
  orderIndex: number,
  blocks: ReportBlock[],
  runId: string
): ReportPage {
  return {
    ...createReportPage(title, orderIndex),
    config: { source_analysis_run_id: runId, generated_draft: true },
    blocks: reflowBlocks(blocks),
  };
}

/**
 * Build a complete, editable first draft from already persisted investigation
 * output. The composition is deterministic so report creation never depends on
 * another model call and every imported block keeps its original provenance.
 */
export function createInvestigationReportDraft(
  run: AnalysisRunSummary,
  artifacts: AnalysisArtifact[],
  startOrderIndex = 0
): InvestigationReportDraft {
  const imported = artifacts
    .filter((artifact) => artifact.kind !== "report")
    .map(artifactToReportBlock);
  const metrics = imported.filter((block) => block.block_type === "metric");
  const charts = imported.filter((block) => block.block_type === "chart");
  const tables = imported.filter((block) => block.block_type === "table");
  const evidenceArtifactIds = new Set(
    artifacts.filter(hasUserFacingEvidence).map((artifact) => artifact.id)
  );
  const evidence = imported.filter(
    (block) =>
      block.block_type === "evidence" &&
      Boolean(block.artifact_id && evidenceArtifactIds.has(block.artifact_id))
  );
  const narrative = imported.filter((block) => block.block_type === "text");

  const summary = withLayout(analysisSummaryToReportBlock(run), {
    w: 12,
    h: 3,
  });
  summary.title = "结论摘要";

  const overviewBlocks = [
    summary,
    ...metrics.map((block) => withLayout(block, { w: 3, h: 2 })),
    ...charts.slice(0, 1).map((block) => withLayout(block, { w: 12, h: 5 })),
    ...narrative.map((block) => withLayout(block, { w: 12, h: 3 })),
  ];
  const detailBlocks = [
    ...tables.map((block) => withLayout(block, { w: 12, h: 6 })),
    ...charts.slice(1).map((block) => withLayout(block, { w: 12, h: 5 })),
  ];
  const evidenceBlocks = evidence.map((block) =>
    withLayout(block, { w: 12, h: Math.max(3, block.layout.h) })
  );

  const sections = [
    { title: "概览", blocks: overviewBlocks },
    { title: "明细", blocks: detailBlocks },
    { title: "依据", blocks: evidenceBlocks },
  ].filter((section, index) => index === 0 || section.blocks.length > 0);

  return {
    title: runTitle(run),
    description: runSummary(run),
    pages: sections.map((section, index) =>
      draftPage(section.title, startOrderIndex + index, section.blocks, run.id)
    ),
  };
}
