"use client";

import { GripVertical } from "lucide-react";
import * as ResizablePrimitive from "react-resizable-panels";

import { cn } from "@/lib/cn";

export function ResizablePanelGroup({ className, ...props }: ResizablePrimitive.GroupProps) {
  return (
    <ResizablePrimitive.Group
      className={cn("flex h-full w-full aria-[orientation=vertical]:flex-col", className)}
      {...props}
    />
  );
}

export const ResizablePanel = ResizablePrimitive.Panel;

export function ResizableHandle({ className, ...props }: ResizablePrimitive.SeparatorProps) {
  return (
    <ResizablePrimitive.Separator
      className={cn(
        "group relative flex w-px items-center justify-center bg-border outline-none after:absolute after:inset-y-0 after:left-1/2 after:w-3 after:-translate-x-1/2 focus-visible:bg-accent",
        className,
      )}
      {...props}
    >
      <div className="z-10 grid h-8 w-4 place-items-center rounded-full border bg-canvas opacity-0 shadow-sm transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">
        <GripVertical aria-hidden="true" className="size-3 text-muted" />
      </div>
    </ResizablePrimitive.Separator>
  );
}
