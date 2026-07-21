"use client";

import { useParams, useSearchParams } from "next/navigation";
import { ReportWorkspace } from "@/components/reports/ReportWorkspace";

export default function ProjectReportPage() {
  const params = useParams<{ projectId: string; reportId: string }>();
  const searchParams = useSearchParams();
  return (
    <ReportWorkspace
      projectId={params.projectId}
      reportId={params.reportId}
      initialRunId={searchParams.get("fromRun")?.trim() || undefined}
    />
  );
}
