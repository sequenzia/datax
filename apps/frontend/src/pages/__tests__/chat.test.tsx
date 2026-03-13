import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ChatPage } from "../chat";
import type { Conversation, ConversationListResponse } from "@/types/api";

// Mock navigate
const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

// Mock the conversation hooks
const mockUseConversationList = vi.fn();
const mockDeleteMutate = vi.fn();

vi.mock("@/hooks/use-conversations", () => ({
  useConversationList: (search: string) => mockUseConversationList(search),
  useDeleteConversation: () => ({ mutate: mockDeleteMutate }),
}));

// Mock IntersectionObserver
const mockObserve = vi.fn();
const mockDisconnect = vi.fn();

class MockIntersectionObserver {
  constructor() {
    // no-op
  }
  observe = mockObserve;
  disconnect = mockDisconnect;
  unobserve = vi.fn();
}

vi.stubGlobal("IntersectionObserver", MockIntersectionObserver);

const mockConversations: Conversation[] = [
  {
    id: "550e8400-e29b-41d4-a716-446655440001",
    title: "Revenue Analysis",
    message_count: 5,
    created_at: "2026-03-10T10:00:00Z",
    updated_at: "2026-03-12T08:00:00Z",
  },
  {
    id: "550e8400-e29b-41d4-a716-446655440002",
    title: "Customer Segmentation",
    message_count: 12,
    created_at: "2026-03-09T09:00:00Z",
    updated_at: "2026-03-11T14:00:00Z",
  },
  {
    id: "550e8400-e29b-41d4-a716-446655440003",
    title: "Monthly Report",
    message_count: 1,
    created_at: "2026-02-15T08:00:00Z",
    updated_at: "2026-02-15T08:30:00Z",
  },
];

function makePage(
  conversations: Conversation[],
  nextCursor: string | null = null,
): ConversationListResponse {
  return { conversations, next_cursor: nextCursor };
}

function successState(pages: ConversationListResponse[]) {
  return {
    data: { pages, pageParams: [undefined] },
    isLoading: false,
    isError: false,
    fetchNextPage: vi.fn(),
    hasNextPage: pages.some((p) => p.next_cursor !== null),
    isFetchingNextPage: false,
    refetch: vi.fn(),
  };
}

function loadingState() {
  return {
    data: undefined,
    isLoading: true,
    isError: false,
    fetchNextPage: vi.fn(),
    hasNextPage: false,
    isFetchingNextPage: false,
    refetch: vi.fn(),
  };
}

function errorState() {
  return {
    data: undefined,
    isLoading: false,
    isError: true,
    fetchNextPage: vi.fn(),
    hasNextPage: false,
    isFetchingNextPage: false,
    refetch: vi.fn(),
  };
}

function renderPage(route = "/chat") {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path="chat" element={<ChatPage />} />
        <Route path="chat/:conversationId" element={<ChatPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseConversationList.mockReturnValue(
    successState([makePage(mockConversations)]),
  );
});

describe("ChatPage - Conversation History Browser", () => {
  describe("page header", () => {
    it("renders conversations heading", () => {
      renderPage();
      expect(
        screen.getByRole("heading", { name: "Conversations", level: 1 }),
      ).toBeInTheDocument();
    });

    it("renders search input", () => {
      renderPage();
      expect(screen.getByTestId("search-input")).toBeInTheDocument();
      expect(
        screen.getByPlaceholderText("Search conversations..."),
      ).toBeInTheDocument();
    });
  });

  describe("conversation list", () => {
    it("renders all conversation items sorted by most recent", () => {
      renderPage();
      const items = screen.getAllByTestId("conversation-item");
      expect(items).toHaveLength(3);

      // First item should be most recent (Revenue Analysis)
      expect(
        within(items[0]).getByText("Revenue Analysis"),
      ).toBeInTheDocument();
      expect(
        within(items[1]).getByText("Customer Segmentation"),
      ).toBeInTheDocument();
      expect(
        within(items[2]).getByText("Monthly Report"),
      ).toBeInTheDocument();
    });

    it("shows message count for each conversation", () => {
      renderPage();
      expect(screen.getByText("5 messages")).toBeInTheDocument();
      expect(screen.getByText("12 messages")).toBeInTheDocument();
      expect(screen.getByText("1 message")).toBeInTheDocument();
    });

    it("clicking a conversation navigates to chat", async () => {
      renderPage();
      const items = screen.getAllByTestId("conversation-item");
      await userEvent.click(items[0]);
      expect(mockNavigate).toHaveBeenCalledWith(
        "/chat/550e8400-e29b-41d4-a716-446655440001",
      );
    });
  });

  describe("search", () => {
    it("passes search term to hook after debounce", async () => {
      vi.useFakeTimers({ shouldAdvanceTime: true });
      const user = userEvent.setup({
        advanceTimers: vi.advanceTimersByTime,
      });
      renderPage();

      const input = screen.getByTestId("search-input");
      await user.type(input, "Revenue");

      // Before debounce: initial call with empty string
      expect(mockUseConversationList).toHaveBeenLastCalledWith("");

      // Advance past debounce
      await act(async () => {
        vi.advanceTimersByTime(350);
      });

      expect(mockUseConversationList).toHaveBeenLastCalledWith("Revenue");

      vi.useRealTimers();
    });

    it("shows empty state when no conversations and no search", () => {
      mockUseConversationList.mockReturnValue(
        successState([makePage([])]),
      );
      renderPage();

      // With debouncedSearch empty, should show empty-state not no-search-results
      expect(screen.getByTestId("empty-state")).toBeInTheDocument();
      expect(
        screen.queryByTestId("no-search-results"),
      ).not.toBeInTheDocument();
    });
  });

  describe("delete with confirmation", () => {
    it("shows delete confirmation dialog when delete is clicked", async () => {
      renderPage();
      const deleteButtons = screen.getAllByTestId(
        "delete-conversation-button",
      );
      await userEvent.click(deleteButtons[0]);

      const dialog = screen.getByTestId("delete-confirmation");
      expect(dialog).toBeInTheDocument();
      expect(
        screen.getByText(
          "Are you sure you want to delete this conversation? This action cannot be undone.",
        ),
      ).toBeInTheDocument();
    });

    it("calls delete mutation after confirming delete", async () => {
      renderPage();
      const deleteButtons = screen.getAllByTestId(
        "delete-conversation-button",
      );
      await userEvent.click(deleteButtons[0]);

      const confirmButton = screen.getByTestId("confirm-delete-button");
      await userEvent.click(confirmButton);
      expect(mockDeleteMutate).toHaveBeenCalledWith(
        "550e8400-e29b-41d4-a716-446655440001",
        expect.objectContaining({
          onError: expect.any(Function),
          onSettled: expect.any(Function),
        }),
      );
    });

    it("closes delete confirmation dialog when cancel is clicked", async () => {
      renderPage();
      const deleteButtons = screen.getAllByTestId(
        "delete-conversation-button",
      );
      await userEvent.click(deleteButtons[0]);

      expect(screen.getByTestId("delete-confirmation")).toBeInTheDocument();

      const cancelButton = screen.getByRole("button", { name: "Cancel" });
      await userEvent.click(cancelButton);

      expect(
        screen.queryByTestId("delete-confirmation"),
      ).not.toBeInTheDocument();
    });
  });

  describe("empty state", () => {
    it("shows empty state when no conversations exist", () => {
      mockUseConversationList.mockReturnValue(
        successState([makePage([])]),
      );
      renderPage();
      expect(screen.getByTestId("empty-state")).toBeInTheDocument();
      expect(
        screen.getByText(
          "No conversations yet. Start a new chat to analyze your data.",
        ),
      ).toBeInTheDocument();
    });
  });

  describe("loading state", () => {
    it("shows loading skeletons while data is loading", () => {
      mockUseConversationList.mockReturnValue(loadingState());
      renderPage();
      expect(screen.getByTestId("loading-skeleton")).toBeInTheDocument();
    });
  });

  describe("error handling", () => {
    it("shows error message when conversations fail to load", () => {
      mockUseConversationList.mockReturnValue(errorState());
      renderPage();
      expect(screen.getByTestId("error-state")).toBeInTheDocument();
      expect(
        screen.getByText("Failed to load conversations."),
      ).toBeInTheDocument();
    });

    it("shows retry button on error that calls refetch", async () => {
      const mockRefetch = vi.fn();
      mockUseConversationList.mockReturnValue({
        ...errorState(),
        refetch: mockRefetch,
      });
      renderPage();

      const retryButton = screen.getByTestId("retry-button");
      await userEvent.click(retryButton);
      expect(mockRefetch).toHaveBeenCalledTimes(1);
    });
  });

  describe("infinite scroll pagination", () => {
    it("sets up IntersectionObserver for infinite scroll", () => {
      mockUseConversationList.mockReturnValue(
        successState([
          makePage(
            mockConversations,
            "550e8400-e29b-41d4-a716-446655440003",
          ),
        ]),
      );
      renderPage();
      expect(mockObserve).toHaveBeenCalled();
    });

    it("shows loading indicator when fetching next page", () => {
      mockUseConversationList.mockReturnValue({
        ...successState([
          makePage(
            mockConversations,
            "550e8400-e29b-41d4-a716-446655440003",
          ),
        ]),
        isFetchingNextPage: true,
      });
      renderPage();
      expect(screen.getByTestId("loading-more")).toBeInTheDocument();
    });
  });
});
