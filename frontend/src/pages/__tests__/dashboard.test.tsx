import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { DashboardPage } from "../dashboard";
import type { Dataset, Connection, Conversation } from "@/types/api";

// Mock the dashboard data hooks
const mockUseDatasets = vi.fn();
const mockUseConnections = vi.fn();
const mockUseConversations = vi.fn();

vi.mock("@/hooks/use-dashboard-data", () => ({
  useDatasets: () => mockUseDatasets(),
  useConnections: () => mockUseConnections(),
  useConversations: () => mockUseConversations(),
}));

const mockDatasets: Dataset[] = [
  {
    id: "550e8400-e29b-41d4-a716-446655440001",
    name: "sales_data.csv",
    file_format: "csv",
    file_size_bytes: 1048576,
    row_count: 15000,
    status: "ready",
    created_at: "2026-03-01T10:00:00Z",
    updated_at: "2026-03-01T10:00:00Z",
  },
  {
    id: "550e8400-e29b-41d4-a716-446655440002",
    name: "users.parquet",
    file_format: "parquet",
    file_size_bytes: 5242880,
    row_count: 1500000,
    status: "processing",
    created_at: "2026-03-05T14:30:00Z",
    updated_at: "2026-03-05T14:30:00Z",
  },
];

const mockConnections: Connection[] = [
  {
    id: "660e8400-e29b-41d4-a716-446655440001",
    name: "Production DB",
    db_type: "postgresql",
    host: "db.example.com",
    port: 5432,
    database_name: "production",
    status: "connected",
    last_tested_at: "2026-03-10T08:00:00Z",
    created_at: "2026-02-15T09:00:00Z",
    updated_at: "2026-03-10T08:00:00Z",
  },
  {
    id: "660e8400-e29b-41d4-a716-446655440002",
    name: "Staging MySQL",
    db_type: "mysql",
    host: "staging.example.com",
    port: 3306,
    database_name: "staging",
    status: "disconnected",
    last_tested_at: null,
    created_at: "2026-02-20T11:00:00Z",
    updated_at: "2026-02-20T11:00:00Z",
  },
];

const mockConversations: Conversation[] = [
  {
    id: "770e8400-e29b-41d4-a716-446655440001",
    title: "Q1 Revenue Analysis",
    message_count: 12,
    created_at: "2026-03-10T10:00:00Z",
    updated_at: "2026-03-10T15:30:00Z",
  },
  {
    id: "770e8400-e29b-41d4-a716-446655440002",
    title: "User Growth Trends",
    message_count: 1,
    created_at: "2026-03-09T08:00:00Z",
    updated_at: "2026-03-09T09:00:00Z",
  },
];

function loadingState() {
  return {
    data: undefined,
    isLoading: true,
    isError: false,
    refetch: vi.fn(),
  };
}

function successState<T>(data: T) {
  return { data, isLoading: false, isError: false, refetch: vi.fn() };
}

function errorState() {
  return {
    data: undefined,
    isLoading: false,
    isError: true,
    refetch: vi.fn(),
  };
}

function renderDashboard() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <DashboardPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseDatasets.mockReturnValue(successState(mockDatasets));
  mockUseConnections.mockReturnValue(successState(mockConnections));
  mockUseConversations.mockReturnValue(successState(mockConversations));
});

describe("DashboardPage", () => {
  describe("page header", () => {
    it("renders dashboard heading", () => {
      renderDashboard();
      expect(
        screen.getByRole("heading", { name: "Dashboard", level: 1 }),
      ).toBeInTheDocument();
    });

    it("renders overview description", () => {
      renderDashboard();
      expect(
        screen.getByText(
          "Overview of your datasets, connections, and conversations.",
        ),
      ).toBeInTheDocument();
    });
  });

  describe("all sections render", () => {
    it("renders datasets, connections, and conversations sections", () => {
      renderDashboard();
      expect(
        screen.getByRole("heading", { name: "Datasets" }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("heading", { name: "Connections" }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("heading", { name: "Recent Conversations" }),
      ).toBeInTheDocument();
    });
  });

  describe("datasets section", () => {
    it("shows dataset cards with name, format, row count, and status", () => {
      renderDashboard();
      expect(screen.getByText("sales_data.csv")).toBeInTheDocument();
      expect(screen.getByText("CSV")).toBeInTheDocument();
      expect(screen.getByText("15.0K rows")).toBeInTheDocument();

      expect(screen.getByText("users.parquet")).toBeInTheDocument();
      expect(screen.getByText("PARQUET")).toBeInTheDocument();
      expect(screen.getByText("1.5M rows")).toBeInTheDocument();

      const statusIndicators = screen.getAllByTestId("dataset-status");
      expect(statusIndicators).toHaveLength(2);
    });

    it("links dataset cards to detail pages", () => {
      renderDashboard();
      const salesLink = screen
        .getByText("sales_data.csv")
        .closest("a");
      expect(salesLink).toHaveAttribute(
        "href",
        "/datasets/550e8400-e29b-41d4-a716-446655440001",
      );
    });
  });

  describe("connections section", () => {
    it("shows connection cards with name, type, host, and status indicator", () => {
      renderDashboard();
      expect(screen.getByText("Production DB")).toBeInTheDocument();
      expect(screen.getByText("postgresql")).toBeInTheDocument();
      expect(screen.getByText("db.example.com")).toBeInTheDocument();

      expect(screen.getByText("Staging MySQL")).toBeInTheDocument();
      expect(screen.getByText("mysql")).toBeInTheDocument();
      expect(screen.getByText("staging.example.com")).toBeInTheDocument();

      const statusIndicators = screen.getAllByTestId("connection-status");
      expect(statusIndicators).toHaveLength(2);
    });

    it("links connection cards to detail pages", () => {
      renderDashboard();
      const prodLink = screen
        .getByText("Production DB")
        .closest("a");
      expect(prodLink).toHaveAttribute(
        "href",
        "/connections/660e8400-e29b-41d4-a716-446655440001",
      );
    });
  });

  describe("conversations section", () => {
    it("shows conversation title, date, and message count", () => {
      renderDashboard();
      expect(screen.getByText("Q1 Revenue Analysis")).toBeInTheDocument();
      expect(screen.getByText("12 messages")).toBeInTheDocument();

      expect(screen.getByText("User Growth Trends")).toBeInTheDocument();
      expect(screen.getByText("1 message")).toBeInTheDocument();
    });

    it("links conversations to chat pages", () => {
      renderDashboard();
      const convoLink = screen
        .getByText("Q1 Revenue Analysis")
        .closest("a");
      expect(convoLink).toHaveAttribute(
        "href",
        "/chat/770e8400-e29b-41d4-a716-446655440001",
      );
    });
  });

  describe("quick actions", () => {
    it("renders Upload Data button linking to upload page", () => {
      renderDashboard();
      const uploadLink = screen.getByRole("link", { name: /Upload Data/i });
      expect(uploadLink).toHaveAttribute("href", "/datasets/upload");
    });

    it("renders Add Connection button linking to new connection page", () => {
      renderDashboard();
      const addConnLink = screen.getByRole("link", {
        name: /Add Connection/i,
      });
      expect(addConnLink).toHaveAttribute("href", "/connections/new");
    });

    it("renders Start Conversation button linking to chat page", () => {
      renderDashboard();
      const chatLink = screen.getByRole("link", {
        name: /Start Conversation/i,
      });
      expect(chatLink).toHaveAttribute("href", "/chat");
    });
  });

  describe("empty states", () => {
    it("shows empty state for datasets when none exist", () => {
      mockUseDatasets.mockReturnValue(successState([]));
      renderDashboard();
      expect(
        screen.getByText("No datasets uploaded yet."),
      ).toBeInTheDocument();
      // CTA appears in both Quick Actions and empty state
      const uploadLinks = screen.getAllByRole("link", { name: "Upload Data" });
      expect(uploadLinks.length).toBeGreaterThanOrEqual(2);
    });

    it("shows empty state for connections when none exist", () => {
      mockUseConnections.mockReturnValue(successState([]));
      renderDashboard();
      expect(
        screen.getByText("No database connections configured."),
      ).toBeInTheDocument();
      // CTA appears in both Quick Actions and empty state
      const connLinks = screen.getAllByRole("link", { name: "Add Connection" });
      expect(connLinks.length).toBeGreaterThanOrEqual(2);
    });

    it("shows empty state for conversations when none exist", () => {
      mockUseConversations.mockReturnValue(successState([]));
      renderDashboard();
      expect(screen.getByText("No conversations yet.")).toBeInTheDocument();
      // CTA appears in both Quick Actions and empty state
      const chatLinks = screen.getAllByRole("link", {
        name: "Start Conversation",
      });
      expect(chatLinks.length).toBeGreaterThanOrEqual(2);
    });

    it("shows all empty states for first-time user", () => {
      mockUseDatasets.mockReturnValue(successState([]));
      mockUseConnections.mockReturnValue(successState([]));
      mockUseConversations.mockReturnValue(successState([]));
      renderDashboard();

      expect(
        screen.getByText("No datasets uploaded yet."),
      ).toBeInTheDocument();
      expect(
        screen.getByText("No database connections configured."),
      ).toBeInTheDocument();
      expect(screen.getByText("No conversations yet.")).toBeInTheDocument();
    });
  });

  describe("error handling", () => {
    it("shows error message when datasets fail to load", () => {
      mockUseDatasets.mockReturnValue(errorState());
      renderDashboard();
      expect(
        screen.getByText("Failed to load datasets."),
      ).toBeInTheDocument();
    });

    it("shows error message when connections fail to load", () => {
      mockUseConnections.mockReturnValue(errorState());
      renderDashboard();
      expect(
        screen.getByText("Failed to load connections."),
      ).toBeInTheDocument();
    });

    it("shows error message when conversations fail to load", () => {
      mockUseConversations.mockReturnValue(errorState());
      renderDashboard();
      expect(
        screen.getByText("Failed to load conversations."),
      ).toBeInTheDocument();
    });

    it("shows retry button on error that calls refetch", async () => {
      const mockRefetch = vi.fn();
      mockUseDatasets.mockReturnValue({
        ...errorState(),
        refetch: mockRefetch,
      });
      renderDashboard();

      const retryButtons = screen.getAllByRole("button", { name: "Retry" });
      await userEvent.click(retryButtons[0]);
      expect(mockRefetch).toHaveBeenCalledTimes(1);
    });

    it("shows loaded sections even when one section fails (partial load)", () => {
      mockUseDatasets.mockReturnValue(errorState());
      // connections and conversations succeed
      renderDashboard();

      expect(
        screen.getByText("Failed to load datasets."),
      ).toBeInTheDocument();
      expect(screen.getByText("Production DB")).toBeInTheDocument();
      expect(screen.getByText("Q1 Revenue Analysis")).toBeInTheDocument();
    });
  });

  describe("loading states", () => {
    it("shows loading skeletons while data is loading", () => {
      mockUseDatasets.mockReturnValue(loadingState());
      mockUseConnections.mockReturnValue(loadingState());
      mockUseConversations.mockReturnValue(loadingState());
      const { container } = renderDashboard();

      const skeletons = container.querySelectorAll(".animate-pulse");
      expect(skeletons.length).toBeGreaterThan(0);
    });
  });

  describe("many items", () => {
    it("shows View all link when datasets exceed max visible items", () => {
      const manyDatasets = Array.from({ length: 10 }, (_, i) => ({
        ...mockDatasets[0],
        id: `550e8400-e29b-41d4-a716-44665544000${i}`,
        name: `dataset_${i}.csv`,
      }));
      mockUseDatasets.mockReturnValue(successState(manyDatasets));
      renderDashboard();

      const datasetsSection = screen
        .getByRole("heading", { name: "Datasets" })
        .closest("section")!;
      const viewAllLink = within(datasetsSection).getByText("View all");
      expect(viewAllLink).toBeInTheDocument();
    });

    it("shows View all link when connections exceed max visible items", () => {
      const manyConns = Array.from({ length: 8 }, (_, i) => ({
        ...mockConnections[0],
        id: `660e8400-e29b-41d4-a716-44665544000${i}`,
        name: `connection_${i}`,
      }));
      mockUseConnections.mockReturnValue(successState(manyConns));
      renderDashboard();

      const connectionsSection = screen
        .getByRole("heading", { name: "Connections" })
        .closest("section")!;
      const viewAllLink = within(connectionsSection).getByText("View all");
      expect(viewAllLink).toBeInTheDocument();
    });
  });
});
