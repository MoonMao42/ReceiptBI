"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import { useLocale } from "next-intl";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  ExternalLink,
  Github,
  MessageCircleQuestion,
  Scale,
} from "lucide-react";
import { formatDesktopPlatform, readDesktopAppInfo } from "@/lib/desktop-app-info";
import { RECEIPTBI_BRAND_ICON_SRC } from "@/lib/brand";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const REPOSITORY_URL = "https://github.com/MoonMao42/QueryGPT";
const LICENSE_URL = "https://github.com/MoonMao42/QueryGPT/blob/main/LICENSE";
const ISSUES_URL = "https://github.com/MoonMao42/QueryGPT/issues";

interface RuntimeInfo {
  version: string;
  isPackaged: boolean;
  platform?: string;
}

function formatDisplayVersion(version: string) {
  return version.replace(/^(\d+\.\d+)\.0$/, "$1");
}

type WindowWithExternalBridge = Window & {
  electronAPI?: {
    openExternal?: (url: string) => Promise<void>;
  };
};

async function openFixedExternalUrl(url: string) {
  const bridge = (window as WindowWithExternalBridge).electronAPI?.openExternal;
  if (bridge) {
    try {
      await bridge(url);
      return;
    } catch {
      // Browser fallback keeps the links useful while the desktop bridge starts.
    }
  }
  window.open(url, "_blank", "noopener,noreferrer");
}

export default function AboutPage() {
  const router = useRouter();
  const locale = useLocale();
  const isChinese = locale === "zh";
  const [runtimeInfo, setRuntimeInfo] = useState<RuntimeInfo | null>(null);

  useEffect(() => {
    let active = true;

    const loadRuntimeInfo = async () => {
      try {
        const desktopInfo = await readDesktopAppInfo();
        if (desktopInfo) {
          if (active) {
            setRuntimeInfo({
              version: desktopInfo.version,
              isPackaged: desktopInfo.isPackaged,
              platform: desktopInfo.platform,
            });
          }
          return;
        }
      } catch {
        // Fall back to the local service when an older desktop bridge is still starting.
      }

      try {
        const response = await fetch(`${API_URL}/health`, {
          headers: { Accept: "application/json" },
        });
        if (!response.ok) return;
        const payload = (await response.json()) as { version?: string };
        if (active && payload.version) {
          setRuntimeInfo({ version: payload.version, isPackaged: false });
        }
      } catch {
        // Basic product links remain available while the local service starts.
      }
    };

    void loadRuntimeInfo();
    return () => {
      active = false;
    };
  }, []);

  const copy = isChinese
    ? {
        back: "返回工作台",
        version: "版本",
        preview: "开发预览",
        desktop: "桌面版",
        repository: "GitHub",
        repositoryDescription: "查看源代码与项目进展",
        license: "MIT License",
        licenseDescription: "查看开源许可证",
        issues: "反馈与 Issues",
        issuesDescription: "报告问题或提出建议",
      }
    : {
        back: "Back to workspace",
        version: "Version",
        preview: "Development preview",
        desktop: "Desktop",
        repository: "GitHub",
        repositoryDescription: "View source code and project updates",
        license: "MIT License",
        licenseDescription: "Read the open-source license",
        issues: "Feedback & Issues",
        issuesDescription: "Report a problem or suggest an improvement",
      };

  const runtimeLabel = runtimeInfo
    ? `${runtimeInfo.isPackaged ? copy.desktop : copy.preview} · v${formatDisplayVersion(runtimeInfo.version)}`
    : copy.preview;
  const links = [
    {
      label: copy.repository,
      description: copy.repositoryDescription,
      url: REPOSITORY_URL,
      icon: Github,
    },
    {
      label: copy.license,
      description: copy.licenseDescription,
      url: LICENSE_URL,
      icon: Scale,
    },
    {
      label: copy.issues,
      description: copy.issuesDescription,
      url: ISSUES_URL,
      icon: MessageCircleQuestion,
    },
  ];

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border bg-card">
        <div className="mx-auto flex h-[68px] max-w-5xl items-center justify-between px-5 sm:px-8">
          <button
            type="button"
            onClick={() => router.push("/")}
            className="inline-flex items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            <ArrowLeft size={17} />
            {copy.back}
          </button>
          <div className="flex items-center gap-2.5">
            <Image
              src={RECEIPTBI_BRAND_ICON_SRC}
              alt=""
              width={32}
              height={32}
              unoptimized
              className="h-8 w-8 object-contain"
              aria-hidden="true"
            />
            <span className="text-sm font-semibold tracking-wide">ReceiptBI</span>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-5 py-12 sm:px-8 sm:py-16">
        <section className="grid gap-10 border-b border-border pb-10 md:grid-cols-[minmax(0,1fr)_260px] md:items-end">
          <div>
            <h1 className="text-5xl font-semibold tracking-[-0.055em] sm:text-6xl">ReceiptBI</h1>
          </div>

          <div className="border-t border-border pt-5 md:border-l md:border-t-0 md:pl-7 md:pt-0">
            <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
              {copy.version}
            </div>
            <div className="mt-3 font-mono text-sm font-semibold">{runtimeLabel}</div>
            {runtimeInfo?.platform && (
              <div className="mt-1 font-mono text-xs text-muted-foreground">
                {formatDesktopPlatform(runtimeInfo.platform)}
              </div>
            )}
          </div>
        </section>

        <section className="mt-9 grid border-l border-t border-border md:grid-cols-3">
          {links.map(({ label, description, url, icon: Icon }) => (
            <button
              key={url}
              type="button"
              onClick={() => void openFixedExternalUrl(url)}
              className="group flex min-h-32 items-start gap-3 border-b border-r border-border bg-card px-5 py-5 text-left transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary"
            >
              <Icon size={18} className="mt-0.5 shrink-0 text-primary" />
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-2 text-sm font-semibold">
                  {label}
                  <ExternalLink
                    size={13}
                    className="text-muted-foreground transition-colors group-hover:text-primary"
                  />
                </span>
                <span className="mt-2 block text-xs leading-5 text-muted-foreground">
                  {description}
                </span>
              </span>
            </button>
          ))}
        </section>
      </main>
    </div>
  );
}
