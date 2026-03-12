import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { DatasetDetailPage } from "../dataset-detail";
import type { DatasetDetail, DatasetPreview } from "@/types/api";

// Mock hooks
const mockUseDatasetDetail = vi.fn();
const mockUseDatasetPreview = vi.fn();
const mockDeleteMutate = vi.fn();
const mockNavigate = vi.fn();

vi.mock("@/hooks/use-datasets", () => ({
  useDatasetDetail: (id: string | undefined) => mockUseDatasetDetail(id),
  useDatasetPreview: (id: string | undefined, params: unknown) =>
    mockUseDatasetPreview(id, params),
  useDeleteDataset: () => ({ mutate: mockDeleteMutate, isPending: false }),
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

const mockDataset: DatasetDetail = {
  id: "550e8400-e29b-41d4-a716-446655440000",
  name: "sales_data.csv",
  file_format: "csv",
  file_size_bytes: 1048576,
  row_count: 15000,
  status: "ready",
  duckdb_table_name: "sales_data_abc123",
  created_at: "2026-03-01T10:00:00Z",
  updated_at: "2026-03-01T10:00:00Z",
  schema: [
    {
      column_name: "id",
      data_type: "INTEGER",
      is_nullable: false,
      is_primary_key: true,
    },
    {
      column_name: "name",
      data_type: "VARCHAR",
      is_nullable: true,
      is_primary_key: false,
    },
    {
      column_name: "amount",
      data_type: "DOUBLE",
      is_nullable: true,
      is_primary_key: false,
    },
  ],
};

const mockPreview: DatasetPreview = {
  columns: ["id", "name", "amount"],
  rows: [
    [1, "Widget A", 29.99],
    [2, "Widget B", 49.99],
  ],
  total_rows: 100,
  offset: 0,
  limit: 50,
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
    <MemoryRouter initialEntries={[`/datasets/${id}`]}>
      <Routes>
        <Route path="datasets/:id" element={<DatasetDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseDatasetDetail.mockReturnValue(successState(mockDataset));
  mockUseDatasetPreview.mockReturnValue(successState(mockPreview));
});

describe("DatasetDetailPage", () => {
  describe("invalid ID", () => {
    it("shows error for invalid UUID", () => {
      renderPage("not-a-valid-uuid");
      expect(screen.getByText("Invalid Dataset ID")).toBeInTheDocument();
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
      mockUseDatasetDetail.mockReturnValue(loadingState());
      const { container } = renderPage(
        "550e8400-e29b-41d4-a716-446655440000",
      );
      const skeletons = container.querySelectorAll(".animate-pulse");
      expect(skeletons.length).toBeGreaterThan(0);
    });
  });

  describe("404 not found", () => {
    it("shows not found message for 404 error", () => {
      mockUseDatasetDetail.mockReturnValue(errorState("API error: 404 Not Found"));
      renderPage("550e8400-e29b-41d4-a716-446655440000");
      expect(screen.getByText("Dataset Not Found")).toBeInTheDocument();
      expect(screen.getByTestId("not-found")).toBeInTheDocument();
    });
  });

  describe("error state", () => {
    it("shows error message on load failure", () => {
      mockUseDatasetDetail.mockReturnValue(errorState());
      renderPage("550e8400-e29b-41d4-a716-446655440000");
      expect(screen.getByText("Error Loading Dataset")).toBeInTheDocument();
    });
  });

  describe("breadcrumbs", () => {
    it("renders breadcrumbs with Dashboard, Datasets, and dataset name", () => {
      renderPage("550e8400-e29b-41d4-a716-446655440000");
      const breadcrumbs = screen.getByTestId("breadcrumbs");
      expect(breadcrumbs).toBeInTheDocument();
      expect(within(breadcrumbs).getByText("Dashboard")).toBeInTheDocument();
      expect(within(breadcrumbs).getByText("Datasets")).toBeInTheDocument();
      expect(
        within(breadcrumbs).getByText("sales_data.csv"),
      ).toBeInTheDocument();
    });
  });

  describe("metadata", () => {
    it("displays dataset metadata including status, format, size, and row count", () => {
      renderPage("550e8400-e29b-41d4-a716-446655440000");
      const metadata = screen.getByTestId("metadata");
      expect(metadata).toBeInTheDocument();
      expect(screen.getByText("Ready")).toBeInTheDocument();
      expect(screen.getByText("CSV")).toBeInTheDocument();
      expect(screen.getByText("1.0 MB")).toBeInTheDocument();
      expect(screen.getByText("15.0K")).toBeInTheDocument();
      expect(screen.getByText("sales_data_abc123")).toBeInTheDocument();
    });
  });

  describe("schema table", () => {
    it("displays schema table with column names and types", () => {
      renderPage("550e8400-e29b-41d4-a716-446655440000");
      const schemaTable = screen.getByTestId("schema-table");
      expect(schemaTable).toBeInTheDocument();
      const schemaScope = within(schemaTable);
      expect(schemaScope.getByText("id")).toBeInTheDocument();
      expect(schemaScope.getByText("INTEGER")).toBeInTheDocument();
      expect(schemaScope.getByText("name")).toBeInTheDocument();
      expect(schemaScope.getByText("VARCHAR")).toBeInTheDocument();
      expect(schemaScope.getByText("amount")).toBeInTheDocument();
      expect(schemaScope.getByText("DOUBLE")).toBeInTheDocument();
    });

    it("shows column count in schema header", () => {
      renderPage("550e8400-e29b-41d4-a716-446655440000");
      expect(screen.getByText("Schema (3 columns)")).toBeInTheDocument();
    });
  });

  describe("data preview", () => {
    it("renders preview table with column headers and data", () => {
      renderPage("550e8400-e29b-41d4-a716-446655440000");
      const previewTable = screen.getByTestId("preview-table");
      expect(previewTable).toBeInTheDocument();
      expect(screen.getByText("Widget A")).toBeInTheDocument();
      expect(screen.getByText("Widget B")).toBeInTheDocument();
    });

    it("shows total row count in preview header", () => {
      renderPage("550e8400-e29b-41d4-a716-446655440000");
      expect(screen.getByText(/100 total rows/)).toBeInTheDocument();
    });
  });

  describe("delete", () => {
    it("shows delete confirmation dialog when delete button is clicked", async () => {
      renderPage("550e8400-e29b-41d4-a716-446655440000");
      const deleteButton = screen.getByTestId("delete-button");
      await userEvent.click(deleteButton);
      expect(screen.getByTestId("delete-confirmation")).toBeInTheDocument();
      expect(
        screen.getByText(/Are you sure you want to delete/),
      ).toBeInTheDocument();
    });

    it("calls delete mutation when confirmed", async () => {
      renderPage("550e8400-e29b-41d4-a716-446655440000");
      await userEvent.click(screen.getByTestId("delete-button"));
      await userEvent.click(screen.getByTestId("confirm-delete-button"));
      expect(mockDeleteMutate).toHaveBeenCalledWith(
        "550e8400-e29b-41d4-a716-446655440000",
        expect.objectContaining({
          onSuccess: expect.any(Function),
          onError: expect.any(Function),
        }),
      );
    });

    it("closes delete dialog when cancel is clicked", async () => {
      renderPage("550e8400-e29b-41d4-a716-446655440000");
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
          opts.onError(new Error("Cannot delete: dataset is in use"));
        },
      );
      renderPage("550e8400-e29b-41d4-a716-446655440000");
      await userEvent.click(screen.getByTestId("delete-button"));
      await userEvent.click(screen.getByTestId("confirm-delete-button"));
      expect(screen.getByTestId("delete-error")).toBeInTheDocument();
      expect(
        screen.getByText("Cannot delete: dataset is in use"),
      ).toBeInTheDocument();
    });
  });
});
