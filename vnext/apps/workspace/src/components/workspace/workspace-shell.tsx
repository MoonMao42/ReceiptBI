"use client";

import { BarChart3, Command, MessageSquareText, PanelRightOpen } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { CommandDialog } from "@/components/ui/command-dialog";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { cn } from "@/lib/cn";

import { ConversationRail } from "./conversation-rail";
import { InspectorSheet } from "./inspector-sheet";
import { LibrarySidebar } from "./library-sidebar";
import { ResultCanvas } from "./result-canvas";

type MobileView = "conversation" | "result";
type LayoutMode = "desktop" | "mobile";

export function WorkspaceShell() {
  const [commandOpen, setCommandOpen] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [layoutMode, setLayoutMode] = useState<LayoutMode | null>(null);
  const [loading, setLoading] = useState(false);
  const [mobileView, setMobileView] = useState<MobileView>("result");
  const [question, setQuestion] = useState("");
  const loadingTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const mediaQuery = window.matchMedia("(min-width: 768px)");
    const syncLayoutMode = () => {
      setLayoutMode(mediaQuery.matches ? "desktop" : "mobile");
    };

    syncLayoutMode();
    mediaQuery.addEventListener("change", syncLayoutMode);
    return () => mediaQuery.removeEventListener("change", syncLayoutMode);
  }, []);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setCommandOpen((current) => !current);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  useEffect(
    () => () => {
      if (loadingTimer.current) {
        clearTimeout(loadingTimer.current);
      }
    },
    [],
  );

  const regenerate = useCallback(() => {
    if (loadingTimer.current) {
      clearTimeout(loadingTimer.current);
    }
    setLoading(true);
    setMobileView("result");
    loadingTimer.current = setTimeout(() => setLoading(false), 1400);
  }, []);

  const prepareDrilldown = useCallback((month: string) => {
    setQuestion(`分析 ${month} 的利润驱动因素，并解释异常变化。`);
    setMobileView("conversation");
  }, []);

  return (
    <div className="h-dvh overflow-hidden bg-background">
      {layoutMode === null ? (
        <div aria-label="正在准备工作区" className="grid h-full place-items-center">
          <div className="h-2 w-32 animate-pulse rounded-full bg-border" />
        </div>
      ) : layoutMode === "desktop" ? (
        <>
          <a className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[100] focus:rounded-lg focus:bg-canvas focus:px-3 focus:py-2" href="#result">
            跳到分析结果
          </a>
          <div className="flex h-full">
            <LibrarySidebar onOpenCommand={() => setCommandOpen(true)} />
            <div className="min-w-0 flex-1">
              <ResizablePanelGroup orientation="horizontal">
                <ResizablePanel defaultSize="34%" maxSize="44%" minSize="27%">
                  <ConversationRail
                    inputId="question-desktop"
                    onQuestionChange={setQuestion}
                    onRegenerate={regenerate}
                    question={question}
                    sectionId="ask"
                  />
                </ResizablePanel>
                <ResizableHandle />
                <ResizablePanel defaultSize="66%" minSize="46%">
                  <ResultCanvas
                    loading={loading}
                    onOpenInspector={() => setInspectorOpen(true)}
                    onPrepareDrilldown={prepareDrilldown}
                    resultId="result"
                  />
                </ResizablePanel>
              </ResizablePanelGroup>
            </div>
          </div>
        </>
      ) : (
        <>
          <a className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[100] focus:rounded-lg focus:bg-canvas focus:px-3 focus:py-2" href="#result-mobile">
            跳到分析结果
          </a>
          <div className="flex h-full flex-col">
            <header className="flex h-14 items-center justify-between border-b bg-canvas px-4">
              <div className="flex items-center gap-2.5">
                <div className="grid size-8 place-items-center rounded-xl bg-foreground text-canvas">
                  <BarChart3 aria-hidden="true" className="size-4" />
                </div>
                <span className="font-semibold">QueryGPT</span>
              </div>
              <div className="flex items-center gap-1">
                <button aria-label="打开快捷命令" className="grid size-9 place-items-center rounded-lg hover:bg-surface" onClick={() => setCommandOpen(true)} type="button">
                  <Command aria-hidden="true" className="size-4" />
                </button>
                <button aria-label="打开结果依据" className="grid size-9 place-items-center rounded-lg hover:bg-surface" onClick={() => setInspectorOpen(true)} type="button">
                  <PanelRightOpen aria-hidden="true" className="size-4" />
                </button>
              </div>
            </header>

            <div aria-label="移动视图" className="grid grid-cols-2 border-b bg-canvas p-1.5" role="tablist">
              {([
                ["conversation", "对话", MessageSquareText],
                ["result", "结果", BarChart3],
              ] as const).map(([value, label, Icon]) => (
                <button
                  aria-selected={mobileView === value}
                  className={cn(
                    "flex items-center justify-center gap-2 rounded-lg py-2 text-sm text-muted",
                    mobileView === value && "bg-surface font-medium text-foreground",
                  )}
                  key={value}
                  onClick={() => setMobileView(value)}
                  role="tab"
                  type="button"
                >
                  <Icon aria-hidden="true" className="size-4" />
                  {label}
                </button>
              ))}
            </div>

            <div className="min-h-0 flex-1">
              {mobileView === "conversation" ? (
                <ConversationRail
                  inputId="question-mobile"
                  onQuestionChange={setQuestion}
                  onRegenerate={regenerate}
                  question={question}
                  sectionId="ask-mobile"
                />
              ) : (
                <ResultCanvas
                  loading={loading}
                  onOpenInspector={() => setInspectorOpen(true)}
                  onPrepareDrilldown={prepareDrilldown}
                  resultId="result-mobile"
                />
              )}
            </div>
          </div>
        </>
      )}

      <CommandDialog onOpenChange={setCommandOpen} open={commandOpen} />
      <InspectorSheet onOpenChange={setInspectorOpen} open={inspectorOpen} />
    </div>
  );
}
