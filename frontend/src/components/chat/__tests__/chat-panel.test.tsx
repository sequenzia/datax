import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ChatPanel } from "@/components/layout/chat-panel";

// Mock streamdown to render children as plain text in tests
vi.mock("streamdown", () => ({
  Streamdown: ({
    children,
    mode,
  }: {
    children?: string;
    mode?: string;
  }) => (
    <div data-testid="streamdown" data-mode={mode}>
      {children}
    </div>
  ),
}));

// Mock the UI store
const mockUIStore = {
  chatPanelOpen: true,
  chatPanelWidth: 380,
  toggleChatPanel: vi.fn(),
};

vi.mock("@/stores/ui-store", () => ({
  useUIStore: () => mockUIStore,
}));

// Mock the chat store
const mockChatStore = {
  conversationId: null as string | null,
  messages: [] as Array<{
    id: string;
    role: "user" | "assistant";
    content: string;
    metadata: null;
    created_at: string;
  }>,
  status: "idle" as string,
  error: null as string | null,
  streamingContent: "",
  sendMessage: vi.fn(),
  cancelStream: vi.fn(),
  clearError: vi.fn(),
  newConversation: vi.fn(),
  switchConversation: vi.fn(),
  reset: vi.fn(),
  restoreSession: vi.fn(),
};

vi.mock("@/stores/chat-store", () => ({
  useChatStore: () => mockChatStore,
}));

// Mock the conversation list hook
const mockConversations = [
  {
    id: "conv-1",
    title: "First Chat",
    message_count: 3,
    created_at: "2026-03-10T10:00:00Z",
    updated_at: "2026-03-12T08:00:00Z",
  },
  {
    id: "conv-2",
    title: "Second Chat",
    message_count: 7,
    created_at: "2026-03-09T09:00:00Z",
    updated_at: "2026-03-11T14:00:00Z",
  },
];

vi.mock("@/hooks/use-conversations", () => ({
  useConversationList: () => ({
    data: {
      pages: [{ conversations: mockConversations, next_cursor: null }],
      pageParams: [undefined],
    },
    isLoading: false,
    isError: false,
    fetchNextPage: vi.fn(),
    hasNextPage: false,
    isFetchingNextPage: false,
    refetch: vi.fn(),
  }),
  useDeleteConversation: () => ({ mutate: vi.fn() }),
}));

function resetMocks() {
  mockUIStore.chatPanelOpen = true;
  mockUIStore.chatPanelWidth = 380;
  mockChatStore.conversationId = null;
  mockChatStore.messages = [];
  mockChatStore.status = "idle";
  mockChatStore.error = null;
  mockChatStore.streamingContent = "";
  vi.clearAllMocks();
}

beforeEach(() => {
  resetMocks();
});

describe("ChatPanel", () => {
  describe("rendering", () => {
    it("renders the chat panel with header and input", () => {
      render(<ChatPanel />);
      expect(screen.getByTestId("chat-panel")).toBeInTheDocument();
      expect(screen.getByTestId("chat-input-form")).toBeInTheDocument();
      expect(screen.getByTestId("message-list")).toBeInTheDocument();
    });

    it("returns null when panel is closed and not fullWidth", () => {
      mockUIStore.chatPanelOpen = false;
      const { container } = render(<ChatPanel />);
      expect(container.firstChild).toBeNull();
    });

    it("renders when fullWidth even if panel is closed", () => {
      mockUIStore.chatPanelOpen = false;
      render(<ChatPanel fullWidth />);
      expect(screen.getByTestId("chat-panel")).toBeInTheDocument();
    });

    it("shows empty state when no messages", () => {
      render(<ChatPanel />);
      expect(
        screen.getByText("Ask a question about your data"),
      ).toBeInTheDocument();
    });

    it("shows collapse button in sidebar mode", () => {
      render(<ChatPanel />);
      expect(screen.getByTestId("collapse-chat-button")).toBeInTheDocument();
    });

    it("hides collapse button in fullWidth mode", () => {
      render(<ChatPanel fullWidth />);
      expect(
        screen.queryByTestId("collapse-chat-button"),
      ).not.toBeInTheDocument();
    });
  });

  describe("message display", () => {
    it("renders user and assistant messages", () => {
      mockChatStore.messages = [
        {
          id: "msg-1",
          role: "user",
          content: "What is the total revenue?",
          metadata: null,
          created_at: "2026-03-12T10:00:00Z",
        },
        {
          id: "msg-2",
          role: "assistant",
          content: "The total revenue is $1,234,567.",
          metadata: null,
          created_at: "2026-03-12T10:00:05Z",
        },
      ];
      render(<ChatPanel />);

      expect(screen.getByTestId("message-bubble-user")).toBeInTheDocument();
      expect(
        screen.getByTestId("message-bubble-assistant"),
      ).toBeInTheDocument();
      expect(
        screen.getByText("What is the total revenue?"),
      ).toBeInTheDocument();
      expect(
        screen.getByText("The total revenue is $1,234,567."),
      ).toBeInTheDocument();
    });

    it("renders messages in order", () => {
      mockChatStore.messages = [
        {
          id: "msg-1",
          role: "user",
          content: "First",
          metadata: null,
          created_at: "2026-03-12T10:00:00Z",
        },
        {
          id: "msg-2",
          role: "assistant",
          content: "Second",
          metadata: null,
          created_at: "2026-03-12T10:00:01Z",
        },
        {
          id: "msg-3",
          role: "user",
          content: "Third",
          metadata: null,
          created_at: "2026-03-12T10:00:02Z",
        },
      ];
      render(<ChatPanel />);

      const messageList = screen.getByTestId("message-list");
      const bubbles = within(messageList).getAllByTestId(/^message-bubble-/);
      expect(bubbles).toHaveLength(3);

      // Verify order by checking text content
      expect(within(bubbles[0]).getByText("First")).toBeInTheDocument();
      expect(within(bubbles[1]).getByText("Second")).toBeInTheDocument();
      expect(within(bubbles[2]).getByText("Third")).toBeInTheDocument();
    });
  });

  describe("streaming", () => {
    it("shows streaming assistant message during streaming", () => {
      mockChatStore.status = "streaming";
      mockChatStore.streamingContent = "Let me analyze";
      mockChatStore.messages = [
        {
          id: "msg-1",
          role: "user",
          content: "Analyze revenue",
          metadata: null,
          created_at: "2026-03-12T10:00:00Z",
        },
      ];
      render(<ChatPanel />);

      expect(screen.getByTestId("streaming-text")).toBeInTheDocument();
      expect(screen.getByText("Let me analyze")).toBeInTheDocument();
      // Streamdown renders the caret during streaming; fallback cursor only shows when content is empty
    });

    it("shows fallback cursor when streaming starts with empty content", () => {
      mockChatStore.status = "streaming";
      mockChatStore.streamingContent = "";
      mockChatStore.messages = [
        {
          id: "msg-1",
          role: "user",
          content: "Analyze revenue",
          metadata: null,
          created_at: "2026-03-12T10:00:00Z",
        },
      ];
      render(<ChatPanel />);

      expect(screen.getByTestId("streaming-text")).toBeInTheDocument();
      expect(screen.getByTestId("streaming-cursor")).toBeInTheDocument();
    });

    it("shows cancel button during streaming", () => {
      mockChatStore.status = "streaming";
      render(<ChatPanel />);
      expect(screen.getByTestId("cancel-stream-button")).toBeInTheDocument();
    });
  });

  describe("sending messages", () => {
    it("calls sendMessage when input is submitted", async () => {
      render(<ChatPanel />);
      const input = screen.getByTestId("chat-input");
      await userEvent.type(input, "Hello AI");
      await userEvent.click(screen.getByTestId("send-button"));
      expect(mockChatStore.sendMessage).toHaveBeenCalledWith("Hello AI");
    });

    it("prevents empty submissions", async () => {
      render(<ChatPanel />);
      await userEvent.click(screen.getByTestId("send-button"));
      expect(mockChatStore.sendMessage).not.toHaveBeenCalled();
    });
  });

  describe("error handling", () => {
    it("shows error banner when error exists", () => {
      mockChatStore.error = "Connection failed";
      render(<ChatPanel />);
      const errorBanner = screen.getByTestId("chat-error");
      expect(errorBanner).toBeInTheDocument();
      expect(screen.getByText("Connection failed")).toBeInTheDocument();
    });

    it("dismisses error when dismiss button is clicked", async () => {
      mockChatStore.error = "Connection failed";
      render(<ChatPanel />);
      const dismissButton = screen.getByText("Dismiss");
      await userEvent.click(dismissButton);
      expect(mockChatStore.clearError).toHaveBeenCalledTimes(1);
    });

    it("hides error banner when no error", () => {
      mockChatStore.error = null;
      render(<ChatPanel />);
      expect(screen.queryByTestId("chat-error")).not.toBeInTheDocument();
    });
  });

  describe("conversation selector", () => {
    it("shows conversation selector trigger", () => {
      render(<ChatPanel />);
      expect(
        screen.getByTestId("conversation-selector-trigger"),
      ).toBeInTheDocument();
    });

    it("shows 'New Conversation' when no conversation selected", () => {
      mockChatStore.conversationId = null;
      render(<ChatPanel />);
      expect(screen.getByText("New Conversation")).toBeInTheDocument();
    });

    it("shows current conversation title when selected", () => {
      mockChatStore.conversationId = "conv-1";
      render(<ChatPanel />);
      expect(screen.getByText("First Chat")).toBeInTheDocument();
    });

    it("opens dropdown with conversation list", async () => {
      render(<ChatPanel />);
      await userEvent.click(
        screen.getByTestId("conversation-selector-trigger"),
      );
      expect(
        screen.getByTestId("conversation-selector-dropdown"),
      ).toBeInTheDocument();
      expect(
        screen.getByTestId("new-conversation-button"),
      ).toBeInTheDocument();
    });

    it("shows all conversations in dropdown", async () => {
      render(<ChatPanel />);
      await userEvent.click(
        screen.getByTestId("conversation-selector-trigger"),
      );
      const options = screen.getAllByTestId("conversation-option");
      expect(options).toHaveLength(2);
      expect(screen.getByText("First Chat")).toBeInTheDocument();
      expect(screen.getByText("Second Chat")).toBeInTheDocument();
    });

    it("calls switchConversation when a conversation is selected", async () => {
      render(<ChatPanel />);
      await userEvent.click(
        screen.getByTestId("conversation-selector-trigger"),
      );
      const options = screen.getAllByTestId("conversation-option");
      await userEvent.click(options[1]);
      expect(mockChatStore.switchConversation).toHaveBeenCalledWith("conv-2");
    });

    it("calls reset when new conversation button is clicked", async () => {
      render(<ChatPanel />);
      await userEvent.click(
        screen.getByTestId("conversation-selector-trigger"),
      );
      await userEvent.click(screen.getByTestId("new-conversation-button"));
      expect(mockChatStore.reset).toHaveBeenCalledTimes(1);
    });
  });

  describe("loading state", () => {
    it("shows loading spinner when loading", () => {
      mockChatStore.status = "loading";
      render(<ChatPanel />);
      expect(screen.getByTestId("chat-loading")).toBeInTheDocument();
    });

    it("disables input while loading", () => {
      mockChatStore.status = "loading";
      render(<ChatPanel />);
      expect(screen.getByTestId("chat-input")).toBeDisabled();
    });
  });

  describe("panel collapsibility", () => {
    it("calls toggleChatPanel when collapse button is clicked", async () => {
      render(<ChatPanel />);
      await userEvent.click(screen.getByTestId("collapse-chat-button"));
      expect(mockUIStore.toggleChatPanel).toHaveBeenCalledTimes(1);
    });
  });
});
