"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface StatusChipProps {
  tone?: "default" | "success" | "warning";
  children: ReactNode;
}

export function StatusChip({ tone = "default", children }: StatusChipProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-3 py-1 text-xs",
        tone === "default" && "border-border bg-background text-muted-foreground",
        tone === "success" && "border-success/25 bg-success/10 text-success",
        tone === "warning" && "border-warning/25 bg-warning/10 text-warning"
      )}
    >
      {children}
    </span>
  );
}
