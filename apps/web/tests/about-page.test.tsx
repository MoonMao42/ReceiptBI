import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AboutPage from "@/app/about/page";
import messages from "@/messages/zh.json";

const mocks = vi.hoisted(() => ({
  push: vi.fn(),
  readDesktopAppInfo: vi.fn(),
  open: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mocks.push }),
}));

vi.mock("@/lib/api/client", () => ({
  api: { get: vi.fn() },
}));

vi.mock("@/lib/desktop-app-info", () => ({
  readDesktopAppInfo: mocks.readDesktopAppInfo,
  formatDesktopPlatform: (platform: string) => (platform === "darwin" ? "macOS" : platform),
}));

describe("AboutPage", () => {
  beforeEach(() => {
    mocks.push.mockClear();
    mocks.open.mockClear();
    mocks.readDesktopAppInfo.mockResolvedValue({
      version: "1.0.0",
      isPackaged: true,
      platform: "darwin",
    });
    vi.stubGlobal("open", mocks.open);
  });

  it("shows only basic product information and fixed project links", async () => {
    render(
      <NextIntlClientProvider locale="zh" messages={messages}>
        <AboutPage />
      </NextIntlClientProvider>
    );

    await waitFor(() => expect(screen.getByText("桌面版 · v1.0")).toBeInTheDocument());
    expect(screen.getByRole("heading", { name: "ReceiptBI" })).toBeInTheDocument();
    expect(screen.queryByText("本地优先的私人数据分析工作台。")).not.toBeInTheDocument();
    expect(screen.queryByText("ReceiptBI 怎样完成一项工作")).not.toBeInTheDocument();
    expect(screen.queryByText("当前真正支持的能力")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /GitHub/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /MIT License/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /问题与建议/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /GitHub/ }));
    expect(mocks.open).toHaveBeenCalledWith(
      "https://github.com/MoonMao42/ReceiptBI",
      "_blank",
      "noopener,noreferrer"
    );
  });
});
