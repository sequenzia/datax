import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ConnectionsPage } from "../connections";
import type { Connection } from "@/types/api";

// Mock the connection hooks
const mockUseConnectionList = vi.fn();
const mockTestMutate = vi.fn();
const mockRefreshMutate = vi.fn();
const mockDeleteMutate = vi.fn();

vi.mock("@/hooks/use-connections", () => ({
  useConnectionList: () => mockUseConnectionList(),
  useTestConnection: () => ({ mutate: mockTestMutate }),
  useRefreshConnectionSchema: () => ({ mutate: mockRefreshMutate }),
  useDeleteConnection: () => ({ mutate: mockDeleteMutate }),
}));

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
  {
    id: "660e8400-e29b-41d4-a716-446655440003",
    name: "Broken DB",
    db_type: "postgresql",
    host: "broken.example.com",
    port: 5432,
    database_name: "broken",
    status: "error",
    last_tested_at: "2026-03-08T12:00:00Z",
    created_at: "2026-02-25T14:00:00Z",
    updated_at: "2026-03-08T12:00:00Z",
  },
];

function successState<T>(data: T) {
  return { data, isLoading: false, isError: false, refetch: vi.fn() };
}

function loadingState() {
  return {
    data: undefined,
    isLoading: true,
    isError: false,
    refetch: vi.fn(),
  };
}

function errorState() {
  return {
    data: undefined,
    isLoading: false,
    isError: true,
    refetch: vi.fn(),
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/connections"]}>
      <ConnectionsPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseConnectionList.mockReturnValue(successState(mockConnections));
});

describe("ConnectionsPage", () => {
  describe("page header", () => {
    it("renders connections heading", () => {
      renderPage();
      expect(
        screen.getByRole("heading", { name: "Connections", level: 1 }),
      ).toBeInTheDocument();
    });

    it("renders add connection button", () => {
      renderPage();
      const addLink = screen.getByRole("link", { name: /Add Connection/i });
      expect(addLink).toHaveAttribute("href", "/connections/new");
    });
  });

  describe("connection list", () => {
    it("renders all connection cards", () => {
      renderPage();
      const cards = screen.getAllByTestId("connection-card");
      expect(cards).toHaveLength(3);
    });

    it("shows connection name, type, host, and database", () => {
      renderPage();
      expect(screen.getByText("Production DB")).toBeInTheDocument();
      expect(screen.getByText("Staging MySQL")).toBeInTheDocument();
      expect(screen.getByText("Broken DB")).toBeInTheDocument();

      // Each card shows db_type and host in CardDescription
      const cards = screen.getAllByTestId("connection-card");
      const firstCard = within(cards[0]);
      expect(firstCard.getByText(/postgresql/)).toBeInTheDocument();
      expect(firstCard.getByText(/db\.example\.com/)).toBeInTheDocument();
      expect(firstCard.getByText(/production/)).toBeInTheDocument();
    });

    it("shows status indicators with correct colors", () => {
      renderPage();
      const statuses = screen.getAllByTestId("connection-status");
      expect(statuses).toHaveLength(3);

      // connected = green
      expect(statuses[0].className).toContain("bg-green-500");
      // disconnected = gray
      expect(statuses[1].className).toContain("bg-gray-400");
      // error = red
      expect(statuses[2].className).toContain("bg-red-500");
    });

    it("shows last tested date or Never", () => {
      renderPage();
      expect(screen.getByText(/Tested: Never/)).toBeInTheDocument();
    });
  });

  describe("action buttons", () => {
    it("renders test, refresh schema, edit, and delete buttons for each card", () => {
      renderPage();
      const testButtons = screen.getAllByTestId("test-button");
      const refreshButtons = screen.getAllByTestId("refresh-schema-button");
      const deleteButtons = screen.getAllByTestId("delete-button");

      expect(testButtons).toHaveLength(3);
      expect(refreshButtons).toHaveLength(3);
      expect(deleteButtons).toHaveLength(3);

      // Edit links
      const editLinks = screen.getAllByRole("link", { name: /Edit/i });
      expect(editLinks).toHaveLength(3);
      expect(editLinks[0]).toHaveAttribute(
        "href",
        "/connections/660e8400-e29b-41d4-a716-446655440001/edit",
      );
    });

    it("calls test mutation when test button is clicked", async () => {
      renderPage();
      const testButtons = screen.getAllByTestId("test-button");
      await userEvent.click(testButtons[0]);
      expect(mockTestMutate).toHaveBeenCalledWith(
        "660e8400-e29b-41d4-a716-446655440001",
        expect.objectContaining({ onError: expect.any(Function) }),
      );
    });

    it("calls refresh mutation when refresh schema button is clicked", async () => {
      renderPage();
      const refreshButtons = screen.getAllByTestId("refresh-schema-button");
      await userEvent.click(refreshButtons[0]);
      expect(mockRefreshMutate).toHaveBeenCalledWith(
        "660e8400-e29b-41d4-a716-446655440001",
        expect.objectContaining({ onSettled: expect.any(Function) }),
      );
    });

    it("shows delete confirmation dialog when delete is clicked", async () => {
      renderPage();
      const deleteButtons = screen.getAllByTestId("delete-button");
      await userEvent.click(deleteButtons[0]);

      const dialog = screen.getByTestId("delete-confirmation");
      expect(dialog).toBeInTheDocument();
      expect(
        screen.getByText(
          "Are you sure you want to delete this connection? This action cannot be undone.",
        ),
      ).toBeInTheDocument();
    });

    it("calls delete mutation after confirming delete", async () => {
      renderPage();
      const deleteButtons = screen.getAllByTestId("delete-button");
      await userEvent.click(deleteButtons[0]);

      const confirmButton = screen.getByTestId("confirm-delete-button");
      await userEvent.click(confirmButton);
      expect(mockDeleteMutate).toHaveBeenCalledWith(
        "660e8400-e29b-41d4-a716-446655440001",
        expect.objectContaining({ onSettled: expect.any(Function) }),
      );
    });

    it("closes delete confirmation dialog when cancel is clicked", async () => {
      renderPage();
      const deleteButtons = screen.getAllByTestId("delete-button");
      await userEvent.click(deleteButtons[0]);

      expect(screen.getByTestId("delete-confirmation")).toBeInTheDocument();

      const cancelButton = screen.getByRole("button", { name: "Cancel" });
      await userEvent.click(cancelButton);

      expect(screen.queryByTestId("delete-confirmation")).not.toBeInTheDocument();
    });
  });

  describe("empty state", () => {
    it("shows empty state when no connections exist", () => {
      mockUseConnectionList.mockReturnValue(successState([]));
      renderPage();
      expect(
        screen.getByText("No database connections configured."),
      ).toBeInTheDocument();
    });

    it("shows add connection link in empty state", () => {
      mockUseConnectionList.mockReturnValue(successState([]));
      renderPage();
      // Both header and empty state have "Add Connection"
      const addLinks = screen.getAllByRole("link", {
        name: /Add Connection/i,
      });
      expect(addLinks.length).toBeGreaterThanOrEqual(2);
    });
  });

  describe("loading state", () => {
    it("shows loading skeletons while data is loading", () => {
      mockUseConnectionList.mockReturnValue(loadingState());
      const { container } = renderPage();
      const skeletons = container.querySelectorAll(".animate-pulse");
      expect(skeletons.length).toBeGreaterThan(0);
    });
  });

  describe("error handling", () => {
    it("shows error message when connections fail to load", () => {
      mockUseConnectionList.mockReturnValue(errorState());
      renderPage();
      expect(
        screen.getByText("Failed to load connections."),
      ).toBeInTheDocument();
    });

    it("shows retry button on error that calls refetch", async () => {
      const mockRefetch = vi.fn();
      mockUseConnectionList.mockReturnValue({
        ...errorState(),
        refetch: mockRefetch,
      });
      renderPage();

      const retryButton = screen.getByRole("button", { name: "Retry" });
      await userEvent.click(retryButton);
      expect(mockRefetch).toHaveBeenCalledTimes(1);
    });
  });

  describe("scrollable list", () => {
    it("renders all connections when list has 20+ items", () => {
      const manyConnections = Array.from({ length: 25 }, (_, i) => ({
        ...mockConnections[0],
        id: `660e8400-e29b-41d4-a716-44665544${String(i).padStart(4, "0")}`,
        name: `Connection ${i}`,
      }));
      mockUseConnectionList.mockReturnValue(successState(manyConnections));
      renderPage();

      const cards = screen.getAllByTestId("connection-card");
      expect(cards).toHaveLength(25);
    });
  });
});
