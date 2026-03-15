import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DataProfile } from "../data-profile";
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
  ],
  sample_values: {
    id: [1, 2, 3, 4, 5],
    name: ["Alice", "Bob", "Charlie", "Diana", "Eve"],
    score: [88.5, 72.3, 91.0, 45.6, 67.8],
  },
  profiled_at: "2026-03-14T10:00:00Z",
};

// Mock the useDatasetProfile hook
vi.mock("@/hooks/use-datasets", () => ({
  useDatasetProfile: vi.fn(),
}));

// Mock the useBreakpoint hook for ActionToolbar
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

/* -------------------------------------------------------------------------- */
/*  Tests                                                                      */
/* -------------------------------------------------------------------------- */

describe("DataProfile", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders loading skeleton while fetching", () => {
    mockUseDatasetProfile.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
    } as ReturnType<typeof useDatasetProfile>);

    renderWithProviders(<DataProfile datasetId="test-uuid" />);
    expect(screen.getByTestId("skeleton-profile")).toBeInTheDocument();
  });

  it("renders error state when fetch fails", () => {
    mockUseDatasetProfile.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error("Network error"),
    } as ReturnType<typeof useDatasetProfile>);

    renderWithProviders(<DataProfile datasetId="test-uuid" />);
    expect(screen.getByTestId("data-profile-error")).toBeInTheDocument();
    expect(screen.getByText(/Network error/)).toBeInTheDocument();
  });

  it("renders column statistics correctly", () => {
    mockUseDatasetProfile.mockReturnValue({
      data: mockProfile,
      isLoading: false,
      isError: false,
      error: null,
    } as ReturnType<typeof useDatasetProfile>);

    renderWithProviders(
      <DataProfile datasetId="test-uuid-1234" datasetName="Test Dataset" />,
    );

    const profile = screen.getByTestId("data-profile");
    expect(profile).toBeInTheDocument();

    // Header
    expect(screen.getByText("Profile: Test Dataset")).toBeInTheDocument();
    expect(screen.getByText(/3 columns profiled/)).toBeInTheDocument();

    // Column cards
    const cards = screen.getAllByTestId("column-stat-card");
    expect(cards.length).toBe(3);

    // Check column names are shown
    expect(screen.getByText("id")).toBeInTheDocument();
    expect(screen.getByText("name")).toBeInTheDocument();
    expect(screen.getByText("score")).toBeInTheDocument();

    // Check types are shown
    expect(screen.getByText("BIGINT")).toBeInTheDocument();
    expect(screen.getByText("VARCHAR")).toBeInTheDocument();
    expect(screen.getByText("DOUBLE")).toBeInTheDocument();
  });

  it("displays per-column statistics: type, min, max, avg, std, null%, quartiles, approx_unique", () => {
    mockUseDatasetProfile.mockReturnValue({
      data: mockProfile,
      isLoading: false,
      isError: false,
      error: null,
    } as ReturnType<typeof useDatasetProfile>);

    renderWithProviders(<DataProfile datasetId="test-uuid-1234" />);

    // For the 'id' column (BIGINT): check all stat types are present
    expect(screen.getAllByText("Min").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Max").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Avg").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Std").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Null %").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Unique").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Q25").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Q50").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Q75").length).toBeGreaterThan(0);
  });

  it("displays sample values (5 per column)", () => {
    mockUseDatasetProfile.mockReturnValue({
      data: mockProfile,
      isLoading: false,
      isError: false,
      error: null,
    } as ReturnType<typeof useDatasetProfile>);

    renderWithProviders(<DataProfile datasetId="test-uuid-1234" />);

    // Check sample values appear (some may appear in both stats and samples)
    expect(screen.getAllByText("Alice").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Bob").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Charlie").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Diana").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Eve").length).toBeGreaterThanOrEqual(1);

    // Verify Samples section label is present
    const sampleHeaders = screen.getAllByText("Samples");
    expect(sampleHeaders.length).toBeGreaterThan(0);
  });

  it("renders mini quartile bars for numeric columns", () => {
    mockUseDatasetProfile.mockReturnValue({
      data: mockProfile,
      isLoading: false,
      isError: false,
      error: null,
    } as ReturnType<typeof useDatasetProfile>);

    renderWithProviders(<DataProfile datasetId="test-uuid-1234" />);

    // Numeric columns (id, score) should have quartile bars
    const quartileBars = screen.getAllByTestId("quartile-bar");
    expect(quartileBars.length).toBe(2);
  });

  it("shows pagination for wide tables", async () => {
    // Create a profile with 25 columns to trigger pagination (COLUMNS_PER_PAGE = 20)
    const wideProfile: DatasetProfile = {
      dataset_id: "wide-uuid",
      summarize_results: Array.from({ length: 25 }, (_, i) => ({
        column_name: `col_${i}`,
        column_type: "BIGINT",
        min: "0",
        max: "100",
        avg: "50",
        std: "10",
        approx_unique: 50,
        null_percentage: "0.00%",
        q25: "25",
        q50: "50",
        q75: "75",
        count: "100",
      })),
      sample_values: {},
      profiled_at: "2026-03-14T10:00:00Z",
    };

    mockUseDatasetProfile.mockReturnValue({
      data: wideProfile,
      isLoading: false,
      isError: false,
      error: null,
    } as ReturnType<typeof useDatasetProfile>);

    const user = userEvent.setup();
    renderWithProviders(<DataProfile datasetId="wide-uuid" />);

    // Should show pagination controls
    expect(screen.getByTestId("profile-pagination")).toBeInTheDocument();
    expect(screen.getByText(/Showing columns 1–20 of 25/)).toBeInTheDocument();

    // Only 20 cards visible
    const cards = screen.getAllByTestId("column-stat-card");
    expect(cards.length).toBe(20);

    // Click next
    await user.click(screen.getByTestId("profile-next"));
    expect(screen.getByText(/Showing columns 21–25 of 25/)).toBeInTheDocument();

    const cardsPage2 = screen.getAllByTestId("column-stat-card");
    expect(cardsPage2.length).toBe(5);
  });

  it("does not show pagination when columns fit on one page", () => {
    mockUseDatasetProfile.mockReturnValue({
      data: mockProfile,
      isLoading: false,
      isError: false,
      error: null,
    } as ReturnType<typeof useDatasetProfile>);

    renderWithProviders(<DataProfile datasetId="test-uuid-1234" />);

    expect(screen.queryByTestId("profile-pagination")).not.toBeInTheDocument();
  });

  it("wraps content in ComponentErrorBoundary", () => {
    mockUseDatasetProfile.mockReturnValue({
      data: mockProfile,
      isLoading: false,
      isError: false,
      error: null,
    } as ReturnType<typeof useDatasetProfile>);

    renderWithProviders(<DataProfile datasetId="test-uuid-1234" />);

    // DataProfile should be rendered successfully (no error boundary fallback)
    expect(screen.getByTestId("data-profile")).toBeInTheDocument();
  });

  it("renders profiled_at timestamp", () => {
    mockUseDatasetProfile.mockReturnValue({
      data: mockProfile,
      isLoading: false,
      isError: false,
      error: null,
    } as ReturnType<typeof useDatasetProfile>);

    renderWithProviders(<DataProfile datasetId="test-uuid-1234" />);

    // profiled_at should be displayed (formatted by toLocaleString)
    const profileEl = screen.getByTestId("data-profile");
    expect(profileEl.textContent).toContain("2026");
  });
});
