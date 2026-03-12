import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { DatasetsPage } from "../datasets";
import type { Dataset } from "@/types/api";

const mockUseDatasetList = vi.fn();
const mockDeleteMutate = vi.fn();

vi.mock("@/hooks/use-datasets", () => ({
  useDatasetList: () => mockUseDatasetList(),
  useDeleteDataset: () => ({ mutate: mockDeleteMutate, isPending: false }),
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
  {
    id: "550e8400-e29b-41d4-a716-446655440003",
    name: "errors.json",
    file_format: "json",
    file_size_bytes: 2048,
    row_count: null,
    status: "error",
    created_at: "2026-03-07T09:00:00Z",
    updated_at: "2026-03-07T09:00:00Z",
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
    <MemoryRouter initialEntries={["/datasets"]}>
      <DatasetsPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseDatasetList.mockReturnValue(successState(mockDatasets));
});

describe("DatasetsPage", () => {
  describe("page header", () => {
    it("renders datasets heading", () => {
      renderPage();
      expect(
        screen.getByRole("heading", { name: "Datasets", level: 1 }),
      ).toBeInTheDocument();
    });

    it("renders upload dataset button", () => {
      renderPage();
      const uploadLink = screen.getByRole("link", {
        name: /Upload Dataset/i,
      });
      expect(uploadLink).toHaveAttribute("href", "/datasets/upload");
    });
  });

  describe("dataset list", () => {
    it("renders all dataset rows", () => {
      renderPage();
      const rows = screen.getAllByTestId("dataset-row");
      expect(rows).toHaveLength(3);
    });

    it("shows dataset name, format, size, and status", () => {
      renderPage();
      expect(screen.getByText("sales_data.csv")).toBeInTheDocument();
      expect(screen.getByText("users.parquet")).toBeInTheDocument();
      expect(screen.getByText("errors.json")).toBeInTheDocument();
      // Default sort is created_at desc, so last row is sales_data.csv
      const rows = screen.getAllByTestId("dataset-row");
      // Verify the last row (sales_data.csv) shows "Ready"
      expect(within(rows[2]).getByText("Ready")).toBeInTheDocument();
      expect(within(rows[2]).getByText("CSV")).toBeInTheDocument();
      expect(within(rows[2]).getByText("1.0 MB")).toBeInTheDocument();
    });

    it("links dataset names to detail pages", () => {
      renderPage();
      const link = screen.getByText("sales_data.csv");
      expect(link.closest("a")).toHaveAttribute(
        "href",
        "/datasets/550e8400-e29b-41d4-a716-446655440001",
      );
    });
  });

  describe("search", () => {
    it("filters datasets by search query", async () => {
      renderPage();
      const searchInput = screen.getByTestId("search-input");
      await userEvent.type(searchInput, "sales");
      const rows = screen.getAllByTestId("dataset-row");
      expect(rows).toHaveLength(1);
      expect(screen.getByText("sales_data.csv")).toBeInTheDocument();
    });

    it("shows no results message when search has no matches", async () => {
      renderPage();
      const searchInput = screen.getByTestId("search-input");
      await userEvent.type(searchInput, "nonexistent");
      expect(
        screen.getByText("No datasets match your search criteria."),
      ).toBeInTheDocument();
    });
  });

  describe("status filter", () => {
    it("filters datasets by status", async () => {
      renderPage();
      const filter = screen.getByTestId("status-filter");
      await userEvent.selectOptions(filter, "error");
      const rows = screen.getAllByTestId("dataset-row");
      expect(rows).toHaveLength(1);
      expect(screen.getByText("errors.json")).toBeInTheDocument();
    });
  });

  describe("sorting", () => {
    it("sorts by name when name column header is clicked", async () => {
      renderPage();
      const nameButton = screen.getByRole("button", { name: /Name/i });
      await userEvent.click(nameButton);
      const rows = screen.getAllByTestId("dataset-row");
      // Ascending: errors.json, sales_data.csv, users.parquet
      const firstRowLink = rows[0].querySelector("a");
      expect(firstRowLink).toHaveTextContent("errors.json");
    });
  });

  describe("pagination", () => {
    it("paginates when more than 20 datasets exist", () => {
      const manyDatasets = Array.from({ length: 25 }, (_, i) => ({
        ...mockDatasets[0],
        id: `550e8400-e29b-41d4-a716-44665544${String(i).padStart(4, "0")}`,
        name: `dataset_${i}.csv`,
      }));
      mockUseDatasetList.mockReturnValue(successState(manyDatasets));
      renderPage();

      const pagination = screen.getByTestId("pagination");
      expect(pagination).toBeInTheDocument();
      expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();
    });

    it("navigates to next page", async () => {
      const manyDatasets = Array.from({ length: 25 }, (_, i) => ({
        ...mockDatasets[0],
        id: `550e8400-e29b-41d4-a716-44665544${String(i).padStart(4, "0")}`,
        name: `dataset_${i}.csv`,
      }));
      mockUseDatasetList.mockReturnValue(successState(manyDatasets));
      renderPage();

      await userEvent.click(screen.getByTestId("page-next"));
      expect(screen.getByText("Page 2 of 2")).toBeInTheDocument();
    });

    it("handles 100+ datasets with correct page count", () => {
      const manyDatasets = Array.from({ length: 105 }, (_, i) => ({
        ...mockDatasets[0],
        id: `550e8400-e29b-41d4-a716-44665544${String(i).padStart(4, "0")}`,
        name: `dataset_${i}.csv`,
      }));
      mockUseDatasetList.mockReturnValue(successState(manyDatasets));
      renderPage();

      expect(screen.getByText("Page 1 of 6")).toBeInTheDocument();
    });
  });

  describe("bulk actions", () => {
    it("shows bulk delete button when datasets are selected", async () => {
      renderPage();
      const checkboxes = screen.getAllByRole("checkbox");
      // First checkbox is "select all", second is first row
      await userEvent.click(checkboxes[1]);
      expect(screen.getByTestId("bulk-delete-button")).toBeInTheDocument();
    });
  });

  describe("empty state", () => {
    it("shows empty state when no datasets exist", () => {
      mockUseDatasetList.mockReturnValue(successState([]));
      renderPage();
      expect(
        screen.getByText("No datasets uploaded yet."),
      ).toBeInTheDocument();
    });
  });

  describe("loading state", () => {
    it("shows loading skeletons while data is loading", () => {
      mockUseDatasetList.mockReturnValue(loadingState());
      const { container } = renderPage();
      const skeletons = container.querySelectorAll(".animate-pulse");
      expect(skeletons.length).toBeGreaterThan(0);
    });
  });

  describe("error handling", () => {
    it("shows error message when datasets fail to load", () => {
      mockUseDatasetList.mockReturnValue(errorState());
      renderPage();
      expect(
        screen.getByText("Failed to load datasets."),
      ).toBeInTheDocument();
    });

    it("shows retry button on error", async () => {
      const mockRefetch = vi.fn();
      mockUseDatasetList.mockReturnValue({
        ...errorState(),
        refetch: mockRefetch,
      });
      renderPage();

      const retryButton = screen.getByRole("button", { name: "Retry" });
      await userEvent.click(retryButton);
      expect(mockRefetch).toHaveBeenCalledTimes(1);
    });
  });
});
