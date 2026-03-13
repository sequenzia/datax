import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { DashboardPage } from "../dashboard";
import { ThemeProvider } from "@/providers/theme-provider";

vi.mock("@/hooks/use-dashboard-data", () => ({
  useDatasets: () => ({
    data: [
      { id: "1", name: "Sales Data", file_format: "csv", file_size_bytes: 1024, row_count: 100, status: "ready", created_at: "2024-01-01T00:00:00Z", updated_at: "2024-01-01T00:00:00Z" },
    ],
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
  useConnections: () => ({
    data: [
      { id: "1", name: "Prod DB", db_type: "postgresql", host: "localhost", port: 5432, database_name: "mydb", status: "connected", last_tested_at: null, created_at: "2024-01-01T00:00:00Z", updated_at: "2024-01-01T00:00:00Z" },
    ],
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
  useConversations: () => ({
    data: [
      { id: "1", title: "Revenue Analysis", message_count: 5, created_at: "2024-01-01T00:00:00Z", updated_at: "2024-01-01T00:00:00Z" },
    ],
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
}));

vi.mock("@/stores/chat-store", () => ({
  useChatStore: Object.assign(
    () => ({
      conversationId: null,
      messages: [],
      status: "idle",
    }),
    {
      getState: () => ({
        newConversation: vi.fn().mockResolvedValue("new-id"),
        sendMessage: vi.fn(),
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

function renderDashboard() {
  return render(
    <ThemeProvider>
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    </ThemeProvider>,
  );
}

describe("DashboardPage", () => {
  it("renders hero chat input", () => {
    renderDashboard();
    expect(screen.getByTestId("hero-chat-input")).toBeInTheDocument();
  });

  it("renders suggestion chips", () => {
    renderDashboard();
    const chips = screen.getAllByTestId("suggestion-chip");
    expect(chips.length).toBeGreaterThan(0);
  });

  it("renders recent conversations section", () => {
    renderDashboard();
    expect(screen.getByText("Recent Conversations")).toBeInTheDocument();
    expect(screen.getByText("Revenue Analysis")).toBeInTheDocument();
  });

  it("renders data sources summary", () => {
    renderDashboard();
    expect(screen.getByText(/1 dataset/)).toBeInTheDocument();
    expect(screen.getByText(/1 connection/)).toBeInTheDocument();
  });

  it("renders send button in hero input", () => {
    renderDashboard();
    expect(screen.getByTestId("hero-send-button")).toBeInTheDocument();
  });
});
