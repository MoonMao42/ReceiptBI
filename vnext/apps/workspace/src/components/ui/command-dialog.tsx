"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { Command } from "cmdk";
import { Database, LayoutDashboard, Search, Settings2 } from "lucide-react";

type CommandDialogProps = {
  onOpenChange: (open: boolean) => void;
  open: boolean;
};

const items = [
  { icon: LayoutDashboard, label: "打开本月经营分析" },
  { icon: Database, label: "切换到销售数据" },
  { icon: Search, label: "搜索已保存的图表" },
  { icon: Settings2, label: "管理业务口径" },
];

export function CommandDialog({ onOpenChange, open }: CommandDialogProps) {
  return (
    <Dialog.Root onOpenChange={onOpenChange} open={open}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/30 backdrop-blur-[2px]" />
        <Dialog.Content className="fixed left-1/2 top-[18%] z-50 w-[min(92vw,620px)] -translate-x-1/2 overflow-hidden rounded-2xl border bg-canvas shadow-2xl">
          <Dialog.Title className="sr-only">快捷命令</Dialog.Title>
          <Dialog.Description className="sr-only">搜索分析、数据和设置。</Dialog.Description>
          <Command label="快捷命令">
            <Command.Input
              autoFocus
              className="h-14 w-full border-b bg-transparent px-5 text-base outline-none placeholder:text-muted"
              placeholder="搜索分析、数据或命令…"
            />
            <Command.List className="max-h-80 overflow-y-auto p-2">
              <Command.Empty className="p-6 text-center text-sm text-muted">没有匹配项</Command.Empty>
              <Command.Group heading="建议" className="text-xs text-muted">
                {items.map(({ icon: Icon, label }) => (
                  <Command.Item
                    className="mt-1 flex cursor-default items-center gap-3 rounded-xl px-3 py-3 text-sm text-foreground aria-selected:bg-surface"
                    key={label}
                    onSelect={() => onOpenChange(false)}
                  >
                    <Icon aria-hidden="true" className="size-4 text-muted" />
                    {label}
                  </Command.Item>
                ))}
              </Command.Group>
            </Command.List>
          </Command>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
