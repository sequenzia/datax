import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ConnectionDetailPage } from "../connection-detail";
import type { ConnectionDetail } from "@/types/api";

// Mock hooks
const mockUseConnectionDetail = vi.fn();
const mockTestMutate = vi.fn();
const mockRefreshMutate = vi.fn();
const mockDeleteMutate = vi.fn();
const mockNavigate = vi.fn();

vi.mock("@/hooks/use-connections", () => ({
  useConnectionDetail: (id: string | undefined) =>
    mockUseConnectionDetail(id),
  useTestConnection: () => ({ mutate: mockTestMutate, isPending: false }),
  useRefreshConnectionSchema: () => ({
    mutate: mockRefreshMutate,
    isPending: false,
  }),
  useDeleteConnection: () => ({ mutate: mockDeleteMutate, isPending: false }),
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

const mockConnection: ConnectionDetail = {
  id: "660e8400-e29b-41d4-a716-446655440001",
  name: "Production DB",
  db_type: "postgresql",
  host: "db.example.com",
  port: 5432,
  database_name: "production",
  username: "admin",
  status: "connected",
  last_tested_at: "2026-03-10T08:00:00Z",
  created_at: "2026-02-15T09:00:00Z",
  updated_at: "2026-03-10T08:00:00Z",
  schema: [
    {
      table_name: "users",
      column_name: "id",
      data_type: "integer",
      is_nullable: false,
      is_primary_key: true,
      foreign_key_ref: null,
    },
    {
      table_name: "users",
      column_name: "email",
      data_type: "varchar(255)",
      is_nullable: false,
      is_primary_key: false,
      foreign_key_ref: null,
    },
    {
      table_name: "orders",
      column_name: "id",
      data_type: "integer",
      is_nullable: false,
      is_primary_key: true,
      foreign_key_ref: null,
    },
    {
      table_name: "orders",
      column_name: "user_id",
      data_type: "integer",
      is_nullable: false,
      is_primary_key: false,
      foreign_key_ref: "users.id",
    },
  ],
};

function successState<T>(data: T) {
  return { data, isLoading: false, isError: false, error: null };
}

function loadingState() {
  return { data: undefined, isLoading: true, isError: false, error: null };
}

function errorState(message = "API error: 500 Internal Server Error") {
  return {
    data: undefined,
    isLoading: false,
    isError: true,
    error: new Error(message),
  };
}

function renderPage(id: string) {
  return render(
    <MemoryRouter initialEntries={[`/connections/${id}`]}>
      <Routes>
        <Route
          path="connections/:id"
          element={<ConnectionDetailPage />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseConnectionDetail.mockReturnValue(successState(mockConnection));
});

describe("ConnectionDetailPage", () => {
  describe("invalid ID", () => {
    it("shows error for invalid UUID", () => {
      renderPage("not-a-valid-uuid");
      expect(
        screen.getByText("Invalid Connection ID"),
      ).toBeInTheDocument();
    });

    it("renders a link back to dashboard on invalid ID", () => {
      renderPage("bad-id");
      const link = screen.getByText("Back to Dashboard");
      expect(link).toBeInTheDocument();
      expect(link.closest("a")).toHaveAttribute("href", "/");
    });
  });

  describe("loading state", () => {
    it("shows loading skeleton while data is loading", () => {
      mockUseConnectionDetail.mockReturnValue(loadingState());
      const { container } = renderPage(
        "660e8400-e29b-41d4-a716-446655440001",
      );
      const skeletons = container.querySelectorAll(".animate-pulse");
      expect(skeletons.length).toBeGreaterThan(0);
    });
  });

  describe("404 not found", () => {
    it("shows not found message for 404 error", () => {
      mockUseConnectionDetail.mockReturnValue(
        errorState("API error: 404 Not Found"),
      );
      renderPage("660e8400-e29b-41d4-a716-446655440001");
      expect(screen.getByText("Connection Not Found")).toBeInTheDocument();
      expect(screen.getByTestId("not-found")).toBeInTheDocument();
    });
  });

  describe("error state", () => {
    it("shows error message on load failure", () => {
      mockUseConnectionDetail.mockReturnValue(errorState());
      renderPage("660e8400-e29b-41d4-a716-446655440001");
      expect(
        screen.getByText("Error Loading Connection"),
      ).toBeInTheDocument();
    });
  });

  describe("breadcrumbs", () => {
    it("renders breadcrumbs with Dashboard, Connections, and connection name", () => {
      renderPage("660e8400-e29b-41d4-a716-446655440001");
      const breadcrumbs = screen.getByTestId("breadcrumbs");
      expect(breadcrumbs).toBeInTheDocument();
      expect(within(breadcrumbs).getByText("Dashboard")).toBeInTheDocument();
      expect(
        within(breadcrumbs).getByText("Connections"),
      ).toBeInTheDocument();
      expect(
        within(breadcrumbs).getByText("Production DB"),
      ).toBeInTheDocument();
    });
  });

  describe("metadata", () => {
    it("displays connection metadata", () => {
      renderPage("660e8400-e29b-41d4-a716-446655440001");
      const metadata = screen.getByTestId("metadata");
      expect(metadata).toBeInTheDocument();
      expect(screen.getByText("Connected")).toBeInTheDocument();
      expect(screen.getByText("postgresql")).toBeInTheDocument();
      expect(screen.getByText("db.example.com:5432")).toBeInTheDocument();
      expect(screen.getByText("production")).toBeInTheDocument();
      expect(screen.getByText("admin")).toBeInTheDocument();
    });
  });

  describe("schema browser", () => {
    it("renders schema browser with table grouping", () => {
      renderPage("660e8400-e29b-41d4-a716-446655440001");
      const schemaBrowser = screen.getByTestId("schema-browser");
      expect(schemaBrowser).toBeInTheDocument();
      expect(screen.getByText("users")).toBeInTheDocument();
      expect(screen.getByText("orders")).toBeInTheDocument();
    });

    it("shows table count and column count in header", () => {
      renderPage("660e8400-e29b-41d4-a716-446655440001");
      expect(
        screen.getByText(/2 tables.*4 columns/),
      ).toBeInTheDocument();
    });

    it("expands table to show columns", async () => {
      renderPage("660e8400-e29b-41d4-a716-446655440001");
      const usersToggle = screen.getByTestId("table-toggle-users");
      await userEvent.click(usersToggle);
      // Should now show column details for users table
      expect(screen.getByText("email")).toBeInTheDocument();
      expect(screen.getByText("varchar(255)")).toBeInTheDocument();
    });

    it("shows foreign key references", async () => {
      renderPage("660e8400-e29b-41d4-a716-446655440001");
      const ordersToggle = screen.getByTestId("table-toggle-orders");
      await userEvent.click(ordersToggle);
      expect(screen.getByText("users.id")).toBeInTheDocument();
    });
  });

  describe("actions", () => {
    it("renders test, refresh schema, edit, and delete buttons", () => {
      renderPage("660e8400-e29b-41d4-a716-446655440001");
      expect(screen.getByTestId("test-button")).toBeInTheDocument();
      expect(screen.getByTestId("refresh-schema-button")).toBeInTheDocument();
      expect(screen.getByTestId("delete-button")).toBeInTheDocument();
      expect(
        screen.getByRole("link", { name: /Edit/i }),
      ).toBeInTheDocument();
    });

    it("calls test mutation when test button is clicked", async () => {
      renderPage("660e8400-e29b-41d4-a716-446655440001");
      await userEvent.click(screen.getByTestId("test-button"));
      expect(mockTestMutate).toHaveBeenCalledWith(
        "660e8400-e29b-41d4-a716-446655440001",
        expect.objectContaining({
          onSuccess: expect.any(Function),
          onError: expect.any(Function),
        }),
      );
    });

    it("calls refresh mutation when refresh button is clicked", async () => {
      renderPage("660e8400-e29b-41d4-a716-446655440001");
      await userEvent.click(screen.getByTestId("refresh-schema-button"));
      expect(mockRefreshMutate).toHaveBeenCalledWith(
        "660e8400-e29b-41d4-a716-446655440001",
      );
    });
  });

  describe("delete", () => {
    it("shows delete confirmation dialog", async () => {
      renderPage("660e8400-e29b-41d4-a716-446655440001");
      await userEvent.click(screen.getByTestId("delete-button"));
      expect(screen.getByTestId("delete-confirmation")).toBeInTheDocument();
      expect(
        screen.getByText(/Are you sure you want to delete/),
      ).toBeInTheDocument();
    });

    it("calls delete mutation when confirmed", async () => {
      renderPage("660e8400-e29b-41d4-a716-446655440001");
      await userEvent.click(screen.getByTestId("delete-button"));
      await userEvent.click(screen.getByTestId("confirm-delete-button"));
      expect(mockDeleteMutate).toHaveBeenCalledWith(
        "660e8400-e29b-41d4-a716-446655440001",
        expect.objectContaining({
          onSuccess: expect.any(Function),
          onError: expect.any(Function),
        }),
      );
    });

    it("closes delete dialog when cancel is clicked", async () => {
      renderPage("660e8400-e29b-41d4-a716-446655440001");
      await userEvent.click(screen.getByTestId("delete-button"));
      expect(screen.getByTestId("delete-confirmation")).toBeInTheDocument();
      await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
      expect(
        screen.queryByTestId("delete-confirmation"),
      ).not.toBeInTheDocument();
    });

    it("shows delete error when delete fails", async () => {
      mockDeleteMutate.mockImplementation(
        (_id: string, opts: { onError: (e: Error) => void }) => {
          opts.onError(new Error("Cannot delete: connection in use"));
        },
      );
      renderPage("660e8400-e29b-41d4-a716-446655440001");
      await userEvent.click(screen.getByTestId("delete-button"));
      await userEvent.click(screen.getByTestId("confirm-delete-button"));
      expect(screen.getByTestId("delete-error")).toBeInTheDocument();
      expect(
        screen.getByText("Cannot delete: connection in use"),
      ).toBeInTheDocument();
    });
  });
});
