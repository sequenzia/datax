import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ChatPage } from "../chat";
import { ThemeProvider } from "@/providers/theme-provider";

vi.mock("@copilotkit/react-core", () => ({
  useCopilotChatInternal: () => ({
    messages: [],
    sendMessage: vi.fn(),
    isLoading: false,
    stopGeneration: vi.fn(),
  }),
}));

vi.mock("@/hooks/use-ai-status", () => ({
  useAiStatus: () => ({
    connectionStatus: "connected",
    unavailableReason: null,
    hasProvider: true,
    bannerDismissed: false,
    showBanner: false,
    bannerMessage: "",
    dismissBanner: vi.fn(),
    chatDisabled: false,
    chatDisabledMessage: null,
  }),
}));

vi.mock("@/stores/chat-store", () => ({
  useChatStore: Object.assign(
    () => ({
      conversationId: null,
      messages: [],
      status: "idle",
      error: null,
      clearError: vi.fn(),
      switchConversation: vi.fn(),
      restoreSession: vi.fn(),
    }),
    {
      getState: () => ({
        conversationId: null,
        newConversation: vi.fn().mockResolvedValue("new-id"),
        reset: vi.fn(),
      }),
    },
  ),
}));

beforeEach(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

function renderChatPage(path = "/chat") {
  return render(
    <ThemeProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="chat" element={<ChatPage />} />
          <Route path="chat/:conversationId" element={<ChatPage />} />
        </Routes>
      </MemoryRouter>
    </ThemeProvider>,
  );
}

describe("ChatPage", () => {
  it("renders the chat page with empty state", () => {
    renderChatPage();
    expect(screen.getByTestId("chat-page")).toBeInTheDocument();
    expect(screen.getByText("Ask a question about your data")).toBeInTheDocument();
  });

  it("renders message list container", () => {
    renderChatPage();
    expect(screen.getByTestId("message-list")).toBeInTheDocument();
  });

  it("renders chat input", () => {
    renderChatPage();
    expect(screen.getByTestId("chat-input-form")).toBeInTheDocument();
  });

  it("renders send button", () => {
    renderChatPage();
    expect(screen.getByTestId("send-button")).toBeInTheDocument();
  });
});
