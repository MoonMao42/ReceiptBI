import type { HTMLAttributes } from "react";

import { cn } from "@/lib/cn";

export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        "animate-pulse rounded-lg bg-gradient-to-r from-surface via-accent-soft to-surface bg-[length:220%_100%]",
        className,
      )}
      {...props}
    />
  );
}
