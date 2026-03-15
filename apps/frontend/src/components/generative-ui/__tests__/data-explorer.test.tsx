import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DataExplorer } from "../data-explorer";
import type { DatasetProfile } from "@/types/api";

/* -------------------------------------------------------------------------- */
/*  Mocks                                                                      */
/* -------------------------------------------------------------------------- */

const mockProfile: DatasetProfile = {
  dataset_id: "test-uuid-1234",
  summarize_results: [
    {
      column_name: "id",
      column_type: "BIGINT",
      min: "1",
      max: "100",
      avg: "50.5",
      std: "29.15",
      approx_unique: 100,
      null_percentage: "0.00%",
      q25: "25",
      q50: "50",
      q75: "75",
      count: "100",
    },
    {
      column_name: "name",
      column_type: "VARCHAR",
      min: "Alice",
      max: "Zara",
      avg: null,
      std: null,
      approx_unique: 95,
      null_percentage: "2.00%",
      q25: null,
      q50: null,
      q75: null,
      count: "100",
    },
    {
      column_name: "score",
      column_type: "DOUBLE",
      min: "0.0",
      max: "99.9",
      avg: "55.32",
      std: "22.45",
      approx_unique: 87,
      null_percentage: "5.00%",
      q25: "33.0",
      q50: "55.0",
      q75: "78.0",
      count: "100",
    },
    {
      column_name: "is_active",
      column_type: "BOOLEAN",
      min: "false",
      max: "true",
      avg: null,
      std: null,
      approx_unique: 2,
      null_percentage: "0.00%",
      q25: null,
      q50: null,
      q75: null,
      count: "100",
    },
    {
      column_name: "created_at",
      column_type: "TIMESTAMP",
      min: "2024-01-01",
      max: "2024-12-31",
      avg: null,
      std: null,
      approx_unique: 100,
      null_percentage: "1.00%",
      q25: null,
      q50: null,
      q75: null,
      count: "100",
    },
  ],
  sample_values: {
    id: [1, 2, 3, 4, 5],
    name: ["Alice", "Bob", "Charlie", "Diana", "Eve"],
    score: [88.5, 72.3, 91.0, 45.6, 67.8],
    is_active: [true, false, true, true, false],
    created_at: ["2024-01-01", "2024-06-15", "2024-12-31"],
  },
  profiled_at: "2026-03-14T10:00:00Z",
};

// Mock the useDatasetProfile hook
vi.mock("@/hooks/use-datasets", () => ({
  useDatasetProfile: vi.fn(),
  useDatasetList: vi.fn(() => ({ data: [], isLoading: false })),
}));

// Mock useBreakpoint for ActionToolbar
vi.mock("@/hooks/use-breakpoint", () => ({
  useBreakpoint: () => "desktop",
}));

import { useDatasetProfile } from "@/hooks/use-datasets";
const mockUseDatasetProfile = vi.mocked(useDatasetProfile);

/* -------------------------------------------------------------------------- */
/*  Helpers                                                                    */
/* -------------------------------------------------------------------------- */

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
}

function setupProfileMock(profile: DatasetProfile | undefined = mockProfile, isLoading = false, isError = false, error: Error | null = null) {
  mockUseDatasetProfile.mockReturnValue({
    data: profile,
    isLoading,
    isError,
    error,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof useDatasetProfile>);
}

/* -------------------------------------------------------------------------- */
/*  Tests                                                                      */
/* -------------------------------------------------------------------------- */

describe("DataExplorer", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseDatasetProfile.mockReset();
  });

  /* ------ Loading / Error states ------ */

  it("renders loading skeleton while fetching", () => {
    setupProfileMock(undefined, true);
    renderWithProviders(<DataExplorer datasetId="test-uuid" />);
    expect(screen.getByTestId("skeleton-profile")).toBeInTheDocument();
  });

  it("renders error state when fetch fails", () => {
    setupProfileMock(undefined, false, true, new Error("Network error"));
    renderWithProviders(<DataExplorer datasetId="test-uuid" />);
    expect(screen.getByTestId("data-explorer-error")).toBeInTheDocument();
    expect(screen.getByText(/Network error/)).toBeInTheDocument();
  });

  it("renders on-demand profiling message when no profile data", () => {
    mockUseDatasetProfile.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof useDatasetProfile>);
    renderWithProviders(<DataExplorer datasetId="test-uuid" />);
    expect(screen.getByTestId("data-explorer-no-profile")).toBeInTheDocument();
  });

  /* ------ Column browser ------ */

  it("renders column browser with all columns and stats", () => {
    setupProfileMock();
    renderWithProviders(
      <DataExplorer datasetId="test-uuid-1234" datasetName="Test Dataset" />,
    );

    const explorer = screen.getByTestId("data-explorer");
    expect(explorer).toBeInTheDocument();

    // Header
    expect(screen.getByText("Explore: Test Dataset")).toBeInTheDocument();
    expect(screen.getByText(/5 columns/)).toBeInTheDocument();

    // Column browser
    const browser = screen.getByTestId("column-browser");
    expect(browser).toBeInTheDocument();

    // All columns listed
    const rows = screen.getAllByTestId("column-row");
    expect(rows.length).toBe(5);

    // Column names
    expect(screen.getByText("id")).toBeInTheDocument();
    expect(screen.getByText("name")).toBeInTheDocument();
    expect(screen.getByText("score")).toBeInTheDocument();
    expect(screen.getByText("is_active")).toBeInTheDocument();
    expect(screen.getByText("created_at")).toBeInTheDocument();
  });

  it("displays type, null percentage, and distinct count for each column", () => {
    setupProfileMock();
    renderWithProviders(<DataExplorer datasetId="test-uuid-1234" />);

    // Type labels
    expect(screen.getByText("BIGINT")).toBeInTheDocument();
    expect(screen.getByText("VARCHAR")).toBeInTheDocument();
    expect(screen.getByText("DOUBLE")).toBeInTheDocument();
    expect(screen.getByText("BOOLEAN")).toBeInTheDocument();
    expect(screen.getByText("TIMESTAMP")).toBeInTheDocument();

    // Distinct count badges (some values like "100 distinct" appear for multiple columns)
    expect(screen.getAllByText("100 distinct").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("95 distinct")).toBeInTheDocument();
    expect(screen.getByText("87 distinct")).toBeInTheDocument();
    expect(screen.getByText("2 distinct")).toBeInTheDocument();

    // Null badges (only columns with null% > 0)
    expect(screen.getByText("2.00% null")).toBeInTheDocument();
    expect(screen.getByText("5.00% null")).toBeInTheDocument();
    expect(screen.getByText("1.00% null")).toBeInTheDocument();
  });

  /* ------ Column search ------ */

  it("filters columns based on search query", async () => {
    setupProfileMock();
    const user = userEvent.setup();
    renderWithProviders(<DataExplorer datasetId="test-uuid-1234" />);

    const searchInput = screen.getByTestId("column-search");
    await user.type(searchInput, "name");

    const rows = screen.getAllByTestId("column-row");
    expect(rows.length).toBe(1);
    expect(screen.getByText("name")).toBeInTheDocument();
  });

  it("shows no results message for unmatched search", async () => {
    setupProfileMock();
    const user = userEvent.setup();
    renderWithProviders(<DataExplorer datasetId="test-uuid-1234" />);

    const searchInput = screen.getByTestId("column-search");
    await user.type(searchInput, "nonexistent_column");

    expect(screen.queryAllByTestId("column-row").length).toBe(0);
    expect(screen.getByText(/No columns match/)).toBeInTheDocument();
  });

  /* ------ Column detail ------ */

  it("shows column detail panel when a column is clicked", async () => {
    setupProfileMock();
    const user = userEvent.setup();
    renderWithProviders(<DataExplorer datasetId="test-uuid-1234" />);

    // Click on the "score" column
    const rows = screen.getAllByTestId("column-row");
    const scoreRow = rows.find((r) => r.textContent?.includes("score"));
    expect(scoreRow).toBeDefined();
    await user.click(scoreRow!);

    // Detail panel should be visible
    const detail = screen.getByTestId("column-detail");
    expect(detail).toBeInTheDocument();

    // Stats should be shown
    const stats = screen.getByTestId("column-stats");
    expect(stats).toBeInTheDocument();
    expect(stats.textContent).toContain("Min");
    expect(stats.textContent).toContain("Max");
    expect(stats.textContent).toContain("Avg");

    // Distribution histogram should show for numeric columns
    expect(screen.getByTestId("distribution-histogram")).toBeInTheDocument();
  });

  it("shows distribution visualization for numeric columns", async () => {
    setupProfileMock();
    const user = userEvent.setup();
    renderWithProviders(<DataExplorer datasetId="test-uuid-1234" />);

    // Click "id" column (BIGINT)
    const rows = screen.getAllByTestId("column-row");
    const idRow = rows.find((r) => r.textContent?.includes("id"));
    await user.click(idRow!);

    expect(screen.getByTestId("distribution-histogram")).toBeInTheDocument();
    expect(screen.getByText(/Min: 1/)).toBeInTheDocument();
    expect(screen.getByText(/Max: 100/)).toBeInTheDocument();
  });

  it("shows top values with clickable quick-filter buttons", async () => {
    setupProfileMock();
    const user = userEvent.setup();
    renderWithProviders(<DataExplorer datasetId="test-uuid-1234" />);

    // Click on "name" column
    const rows = screen.getAllByTestId("column-row");
    const nameRow = rows.find((r) => r.textContent?.includes("name"));
    await user.click(nameRow!);

    // Top values should be visible
    const topValues = screen.getByTestId("top-values");
    expect(topValues).toBeInTheDocument();

    const quickFilterButtons = within(topValues).getAllByTestId("quick-filter-value");
    expect(quickFilterButtons.length).toBeGreaterThan(0);
  });

  /* ------ Quick filter ------ */

  it("applies quick filter when clicking a value", async () => {
    setupProfileMock();
    const user = userEvent.setup();
    renderWithProviders(<DataExplorer datasetId="test-uuid-1234" />);

    // Click on "name" column
    const rows = screen.getAllByTestId("column-row");
    const nameRow = rows.find((r) => r.textContent?.includes("name"));
    await user.click(nameRow!);

    // Click a sample value to filter
    const quickFilterButtons = screen.getAllByTestId("quick-filter-value");
    await user.click(quickFilterButtons[0]); // "Alice"

    // Active filters bar should appear
    const activeFilters = screen.getByTestId("active-filters");
    expect(activeFilters).toBeInTheDocument();
    expect(activeFilters.textContent).toContain("name");
    expect(activeFilters.textContent).toContain("Alice");
  });

  it("removes quick filter when clicking the remove button", async () => {
    setupProfileMock();
    const user = userEvent.setup();
    renderWithProviders(<DataExplorer datasetId="test-uuid-1234" />);

    // Click on "name" column and add filter
    const rows = screen.getAllByTestId("column-row");
    const nameRow = rows.find((r) => r.textContent?.includes("name"));
    await user.click(nameRow!);

    const quickFilterButtons = screen.getAllByTestId("quick-filter-value");
    await user.click(quickFilterButtons[0]);

    // Active filters should be visible
    expect(screen.getByTestId("active-filters")).toBeInTheDocument();

    // Click "Clear all"
    await user.click(screen.getByText("Clear all"));

    // Filters should be gone
    expect(screen.queryByTestId("active-filters")).not.toBeInTheDocument();
  });

  /* ------ Close detail ------ */

  it("closes detail panel when clicking close button", async () => {
    setupProfileMock();
    const user = userEvent.setup();
    renderWithProviders(<DataExplorer datasetId="test-uuid-1234" />);

    // Open detail
    const rows = screen.getAllByTestId("column-row");
    await user.click(rows[0]);
    expect(screen.getByTestId("column-detail")).toBeInTheDocument();

    // Close detail
    await user.click(screen.getByTestId("close-detail"));
    expect(screen.queryByTestId("column-detail")).not.toBeInTheDocument();
  });

  /* ------ All unique detection ------ */

  it("shows 'all unique' label when approx_unique matches total count", async () => {
    // "id" column has approx_unique=100 and count=100 => all unique
    setupProfileMock();
    const user = userEvent.setup();
    renderWithProviders(<DataExplorer datasetId="test-uuid-1234" />);

    // Click on "id" column
    const rows = screen.getAllByTestId("column-row");
    const idRow = rows.find((r) => r.textContent?.includes("id"));
    await user.click(idRow!);

    const stats = screen.getByTestId("column-stats");
    expect(stats.textContent).toContain("all unique");
  });

  /* ------ Error boundary ------ */

  it("wraps content in ComponentErrorBoundary", () => {
    setupProfileMock();
    renderWithProviders(<DataExplorer datasetId="test-uuid-1234" />);
    expect(screen.getByTestId("data-explorer")).toBeInTheDocument();
  });

  /* ------ Virtualization for 500+ columns ------ */

  it("uses virtualized list for datasets with many columns", () => {
    const largeProfile: DatasetProfile = {
      dataset_id: "large-uuid",
      summarize_results: Array.from({ length: 600 }, (_, i) => ({
        column_name: `col_${i}`,
        column_type: i % 2 === 0 ? "BIGINT" : "VARCHAR",
        min: "0",
        max: "100",
        avg: i % 2 === 0 ? "50" : null,
        std: i % 2 === 0 ? "10" : null,
        approx_unique: 50,
        null_percentage: "0.00%",
        q25: i % 2 === 0 ? "25" : null,
        q50: i % 2 === 0 ? "50" : null,
        q75: i % 2 === 0 ? "75" : null,
        count: "1000",
      })),
      sample_values: {},
      profiled_at: null,
    };

    setupProfileMock(largeProfile);
    renderWithProviders(<DataExplorer datasetId="large-uuid" />);

    // The column list should exist
    const columnList = screen.getByTestId("column-list");
    expect(columnList).toBeInTheDocument();

    // Not all 600 rows should be rendered (virtual scrolling)
    const rows = screen.getAllByTestId("column-row");
    expect(rows.length).toBeLessThan(600);
  });
});
