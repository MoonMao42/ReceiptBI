"use client";

import { useParams } from "next/navigation";
import { ProjectUnderstandingWorkspace } from "@/components/semantic/ProjectUnderstandingWorkspace";

export default function ProjectUnderstandingPage() {
  const params = useParams<{ projectId: string }>();
  return <ProjectUnderstandingWorkspace projectId={params.projectId} />;
}
