import { render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Home from "@/app/page";
import { CONVERSATION_CONTINUITY_STORAGE_KEY } from "@/lib/stores/chat";

const mocks = vi.hoisted(() => ({
  bootstrap: vi.fn(),
  setCurrentConversation: vi.fn(),
  replace: vi.fn(),
  currentConversationId: null as string | null,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mocks.replace }),
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: () => ({ data: [], isLoading: false }),
}));

vi.mock("@/components/chat/Sidebar", () => ({
  Sidebar: () => <aside aria-label="项目导航" />,
}));

vi.mock("@/components/chat/ChatArea", () => ({
  ChatArea: () => <main aria-label="调查工作区" />,
}));

vi.mock("@/lib/stores/project", () => ({
  useProjectStore: () => ({
    bootstrap: mocks.bootstrap,
    currentProjectId: "project-1",
  }),
}));

vi.mock("@/lib/stores/chat", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/stores/chat")>();
  return {
    ...actual,
    useChatStore: () => ({
      messages: [],
      currentConversationId: mocks.currentConversationId,
      isLoading: false,
      activeStreamId: null,
      setCurrentConversation: mocks.setCurrentConversation,
    }),
  };
});

describe("home conversation continuity", () => {
  beforeEach(() => {
    mocks.bootstrap.mockReset();
    mocks.setCurrentConversation.mockReset();
    mocks.replace.mockReset();
    mocks.currentConversationId = null;
    window.history.replaceState(null, "", "/");
    vi.mocked(localStorage.getItem).mockReset();
    vi.mocked(localStorage.getItem).mockReturnValue(null);
  });

  it("restores the saved conversation for the bootstrapped project", async () => {
    vi.mocked(localStorage.getItem).mockImplementation((key) =>
      key === CONVERSATION_CONTINUITY_STORAGE_KEY
        ? JSON.stringify({
            version: 1,
            conversations: { "project-1": "conversation-1" },
          })
        : null
    );

    render(<Home />);

    await waitFor(() =>
      expect(mocks.setCurrentConversation).toHaveBeenCalledWith(
        "conversation-1",
        "project-1"
      )
    );
    expect(mocks.bootstrap).toHaveBeenCalledTimes(1);
    expect(mocks.replace).not.toHaveBeenCalled();
  });

  it("restores an explicitly carried report conversation and consumes the URL", async () => {
    window.history.replaceState(
      null,
      "",
      "/?conversation=conversation-from-report"
    );

    render(<Home />);

    await waitFor(() =>
      expect(mocks.setCurrentConversation).toHaveBeenCalledWith(
        "conversation-from-report",
        "project-1"
      )
    );
    expect(mocks.replace).toHaveBeenCalledWith("/", { scroll: false });
  });

  it("consumes a carried URL even when that conversation is already in memory", async () => {
    window.history.replaceState(
      null,
      "",
      "/?conversation=conversation-from-report"
    );
    mocks.currentConversationId = "conversation-from-report";

    render(<Home />);

    await waitFor(() =>
      expect(mocks.replace).toHaveBeenCalledWith("/", { scroll: false })
    );
    expect(mocks.setCurrentConversation).not.toHaveBeenCalled();
  });
});
