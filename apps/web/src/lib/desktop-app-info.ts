export interface DesktopAppInfo {
  version: string;
  platform: string;
  isPackaged: boolean;
}

interface DesktopBridge {
  getAppInfo?: () => Promise<DesktopAppInfo>;
}

type WindowWithDesktopBridge = Window & {
  electronAPI?: DesktopBridge;
};

export async function readDesktopAppInfo(): Promise<DesktopAppInfo | undefined> {
  if (typeof window === "undefined") return undefined;
  return (window as WindowWithDesktopBridge).electronAPI?.getAppInfo?.();
}

export function formatDesktopPlatform(platform: string): string {
  const labels: Record<string, string> = {
    darwin: "macOS",
    win32: "Windows",
    linux: "Linux",
  };
  return labels[platform] ?? platform;
}
