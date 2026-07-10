"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";

import { cn } from "@/lib/cn";

export const Sheet = Dialog.Root;
export const SheetTrigger = Dialog.Trigger;

export function SheetContent({
  children,
  className,
  description,
  title,
}: Readonly<{
  children: React.ReactNode;
  className?: string;
  description: string;
  title: string;
}>) {
  return (
    <Dialog.Portal>
      <Dialog.Overlay className="fixed inset-0 z-40 bg-black/30 backdrop-blur-[2px]" />
      <Dialog.Content
        className={cn(
          "fixed inset-y-0 right-0 z-50 w-[min(92vw,440px)] overflow-y-auto border-l bg-canvas p-6 shadow-2xl",
          className,
        )}
      >
        <div className="pr-10">
          <Dialog.Title className="text-lg font-semibold">{title}</Dialog.Title>
          <Dialog.Description className="mt-1 text-sm text-muted">{description}</Dialog.Description>
        </div>
        <Dialog.Close
          aria-label="关闭检查器"
          className="absolute right-4 top-4 grid size-9 place-items-center rounded-lg hover:bg-surface"
        >
          <X aria-hidden="true" className="size-4" />
        </Dialog.Close>
        <div className="mt-6">{children}</div>
      </Dialog.Content>
    </Dialog.Portal>
  );
}
