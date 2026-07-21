"use client";

import { useParams } from "next/navigation";
import { ReportIndexPage } from "@/components/reports/ReportIndexPage";

export default function ProjectReportsPage() {
  const params = useParams<{ projectId: string }>();
  return <ReportIndexPage projectId={params.projectId} />;
}
