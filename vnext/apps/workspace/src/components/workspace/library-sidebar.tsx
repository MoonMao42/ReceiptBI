"use client";

import { BarChart3, Command, Database, Library, MessageSquareText, Moon, Plus, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";

import { savedItems } from "./sample-data";

export function LibrarySidebar({ onOpenCommand }: Readonly<{ onOpenCommand: () => void }>) {
  const { resolvedTheme, setTheme } = useTheme();
  const [shortcutLabel, setShortcutLabel] = useState("Ctrl K");

  useEffect(() => {
    setShortcutLabel(navigator.platform.toLowerCase().includes("mac") ? "⌘K" : "Ctrl K");
  }, []);

  return (
    <aside className="hidden h-dvh w-60 shrink-0 flex-col border-r bg-surface/70 p-3 lg:flex">
      <div className="flex items-center justify-between px-2 py-2">
        <div className="flex items-center gap-2.5">
          <div className="grid size-8 place-items-center rounded-xl bg-foreground text-canvas">
            <BarChart3 aria-hidden="true" className="size-4" />
          </div>
          <span className="font-semibold tracking-tight">QueryGPT</span>
        </div>
        <Button aria-label="新建分析" size="icon" variant="ghost">
          <Plus aria-hidden="true" className="size-4" />
        </Button>
      </div>

      <nav aria-label="主导航" className="mt-4 space-y-1">
        <a className="flex items-center gap-3 rounded-xl bg-canvas px-3 py-2.5 text-sm font-medium shadow-sm" href="#ask">
          <MessageSquareText aria-hidden="true" className="size-4" />
          分析
        </a>
        <a className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-muted hover:bg-canvas" href="#library">
          <Library aria-hidden="true" className="size-4" />
          资料库
        </a>
        <a className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-muted hover:bg-canvas" href="#data">
          <Database aria-hidden="true" className="size-4" />
          数据
        </a>
      </nav>

      <button
        className="mt-3 flex items-center justify-between rounded-xl px-3 py-2.5 text-sm text-muted hover:bg-canvas"
        onClick={onOpenCommand}
        type="button"
      >
        <span className="flex items-center gap-3">
          <Command aria-hidden="true" className="size-4" />
          快捷命令
        </span>
        <kbd className="rounded border bg-canvas px-1.5 py-0.5 font-sans text-[10px]">{shortcutLabel}</kbd>
      </button>

      <div className="mt-8 px-2 text-xs font-medium uppercase tracking-[0.16em] text-muted">最近分析</div>
      <div className="mt-2 space-y-1">
        {savedItems.map((item) => (
          <button className="w-full rounded-xl px-3 py-2.5 text-left hover:bg-canvas" key={item.label} type="button">
            <div className="truncate text-sm font-medium">{item.label}</div>
            <div className="mt-1 text-xs text-muted">{item.meta}</div>
          </button>
        ))}
      </div>

      <div className="mt-auto rounded-2xl border bg-canvas p-3">
        <div className="text-xs text-muted">本地数据源</div>
        <div className="mt-1 text-sm font-medium">尚未连接</div>
        <div className="mt-2 flex items-center gap-2 text-xs text-muted">
          <span aria-hidden="true" className="size-1.5 rounded-full bg-muted" />
          连接后仅在此设备使用
        </div>
        <button
          className="mt-3 flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-xs text-muted hover:bg-surface"
          onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
          type="button"
        >
          {resolvedTheme === "dark" ? <Sun aria-hidden="true" className="size-3.5" /> : <Moon aria-hidden="true" className="size-3.5" />}
          切换外观
        </button>
      </div>
    </aside>
  );
}
