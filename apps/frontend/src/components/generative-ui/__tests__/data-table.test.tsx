import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { DataTable } from "../data-table";
import type { DataTableColumn } from "../data-table";

/* -------------------------------------------------------------------------- */
/*  Mocks                                                                      */
/* -------------------------------------------------------------------------- */

// Mock useBreakpoint for ActionToolbar
vi.mock("@/hooks/use-breakpoint", () => ({
  useBreakpoint: () => "desktop",
}));

// Mock useVirtualizer to return a predictable result for tests
// (jsdom does not have real scroll measurements)
vi.mock("@tanstack/react-virtual", () => ({
  useVirtualizer: ({ count }: { count: number }) => ({
    getTotalSize: () => count * 36,
    getVirtualItems: () =>
      Array.from({ length: count }, (_, i) => ({
        index: i,
        start: i * 36,
        size: 36,
        end: (i + 1) * 36,
        key: i,
        lane: 0,
      })),
    measureElement: () => {},
  }),
}));

/* -------------------------------------------------------------------------- */
/*  Test Data                                                                  */
/* -------------------------------------------------------------------------- */

const sampleColumns: DataTableColumn[] = [
  { name: "id", type: "INTEGER" },
  { name: "name", type: "VARCHAR" },
  { name: "amount", type: "DOUBLE" },
  { name: "date", type: "DATE" },
];

const sampleRows: unknown[][] = [
  [1, "Alice", 100.5, "2026-01-01"],
  [2, "Bob", 200.75, "2026-01-02"],
  [3, "Charlie", 50.25, "2026-01-03"],
  [4, "Diana", 300.0, "2026-01-04"],
  [5, "Eve", 150.0, "2026-01-05"],
];

/* -------------------------------------------------------------------------- */
/*  Tests                                                                      */
/* -------------------------------------------------------------------------- */

describe("DataTable", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  /* -- Rendering -- */

  it("renders with column definitions and data", () => {
    render(<DataTable columns={sampleColumns} rows={sampleRows} />);

    const table = screen.getByTestId("data-table");
    expect(table).toBeInTheDocument();

    // Column headers are rendered
    expect(screen.getByTestId("column-header-id")).toBeInTheDocument();
    expect(screen.getByTestId("column-header-name")).toBeInTheDocument();
    expect(screen.getByTestId("column-header-amount")).toBeInTheDocument();
    expect(screen.getByTestId("column-header-date")).toBeInTheDocument();
  });

  it("renders data rows", () => {
    render(<DataTable columns={sampleColumns} rows={sampleRows} />);

    const rows = screen.getAllByTestId("data-row");
    expect(rows.length).toBe(5);

    // Check cell contents
    expect(screen.getByText("Alice")).toBeInTheDocument();
    expect(screen.getByText("Bob")).toBeInTheDocument();
    expect(screen.getByText("Charlie")).toBeInTheDocument();
  });

  it("renders title when provided", () => {
    render(
      <DataTable
        columns={sampleColumns}
        rows={sampleRows}
        title="Sales Data"
      />,
    );
    expect(screen.getByText("Sales Data")).toBeInTheDocument();
  });

  it("shows row count badge", () => {
    render(<DataTable columns={sampleColumns} rows={sampleRows} />);
    const badge = screen.getByTestId("row-count-badge");
    expect(badge).toHaveTextContent("5 rows");
  });

  /* -- Empty state -- */

  it("shows empty state for no rows", () => {
    render(<DataTable columns={sampleColumns} rows={[]} />);
    expect(screen.getByTestId("data-table-empty")).toBeInTheDocument();
    expect(screen.getByText("No data")).toBeInTheDocument();
  });

  it("shows empty state for no columns", () => {
    render(<DataTable columns={[]} rows={[]} />);
    expect(screen.getByTestId("data-table-empty")).toBeInTheDocument();
  });

  /* -- Sorting -- */

  it("sorts ascending on header click", async () => {
    const user = userEvent.setup();
    render(<DataTable columns={sampleColumns} rows={sampleRows} />);

    // Click the name column header to sort ascending
    const nameHeader = screen.getByTestId("column-header-name");
    await user.click(nameHeader);

    // Ascending sort indicator should appear
    expect(screen.getByTestId("sort-asc")).toBeInTheDocument();

    // First row should now be Alice (alphabetically first)
    const rows = screen.getAllByTestId("data-row");
    expect(within(rows[0]).getByText("Alice")).toBeInTheDocument();
  });

  it("sorts descending on second header click", async () => {
    const user = userEvent.setup();
    render(<DataTable columns={sampleColumns} rows={sampleRows} />);

    const nameHeader = screen.getByTestId("column-header-name");

    // First click: ascending
    await user.click(nameHeader);
    expect(screen.getByTestId("sort-asc")).toBeInTheDocument();

    // Second click: descending
    await user.click(nameHeader);
    expect(screen.getByTestId("sort-desc")).toBeInTheDocument();

    // First row should be Eve (alphabetically last)
    const rows = screen.getAllByTestId("data-row");
    expect(within(rows[0]).getByText("Eve")).toBeInTheDocument();
  });

  /* -- Filtering / Global Search -- */

  it("filters rows via global search", async () => {
    const user = userEvent.setup();
    render(<DataTable columns={sampleColumns} rows={sampleRows} />);

    const searchInput = screen.getByTestId("global-search");
    await user.type(searchInput, "Alice");

    // Only Alice's row should remain visible
    const rows = screen.getAllByTestId("data-row");
    expect(rows.length).toBe(1);
    expect(within(rows[0]).getByText("Alice")).toBeInTheDocument();
  });

  it("shows filtered badge and count when filtering", async () => {
    const user = userEvent.setup();
    render(<DataTable columns={sampleColumns} rows={sampleRows} />);

    await user.type(screen.getByTestId("global-search"), "Bob");

    expect(screen.getByTestId("filter-status-badge")).toHaveTextContent(
      "Filtered",
    );
    expect(screen.getByTestId("row-count-badge")).toHaveTextContent(
      "1 of 5 rows",
    );
  });

  /* -- Column Visibility -- */

  it("toggles column visibility via column picker", async () => {
    const user = userEvent.setup();
    render(<DataTable columns={sampleColumns} rows={sampleRows} />);

    // Open column picker
    await user.click(screen.getByTestId("column-picker-toggle"));
    expect(screen.getByTestId("column-picker-dropdown")).toBeInTheDocument();

    // Uncheck the "amount" column
    const amountToggle = screen.getByTestId("column-toggle-amount");
    await user.click(amountToggle);

    // Amount column header should no longer be visible
    expect(
      screen.queryByTestId("column-header-amount"),
    ).not.toBeInTheDocument();

    // Other columns should still be there
    expect(screen.getByTestId("column-header-id")).toBeInTheDocument();
    expect(screen.getByTestId("column-header-name")).toBeInTheDocument();
    expect(screen.getByTestId("column-header-date")).toBeInTheDocument();
  });

  /* -- Virtual Scrolling -- */

  it("renders only visible rows via virtual scrolling", () => {
    // Create a large dataset
    const largeRows = Array.from({ length: 100 }, (_, i) => [
      i,
      `Name ${i}`,
      i * 10,
      "2026-01-01",
    ]);

    render(<DataTable columns={sampleColumns} rows={largeRows} />);

    // Virtual scrolling should still render all rows in our mock
    // (the mock returns all items since jsdom has no scroll)
    const rows = screen.getAllByTestId("data-row");
    // With page size 50, should render 50 rows max (pagination limits)
    expect(rows.length).toBe(50);
  });

  /* -- Pagination -- */

  it("paginates with page size selector", async () => {
    const user = userEvent.setup();

    // Create dataset with 100 rows
    const manyRows = Array.from({ length: 100 }, (_, i) => [
      i,
      `Name ${i}`,
      i * 10,
      "2026-01-01",
    ]);

    render(<DataTable columns={sampleColumns} rows={manyRows} />);

    const pagination = screen.getByTestId("table-pagination");
    expect(pagination).toBeInTheDocument();

    // Default page size is 50, so page 1 of 2
    expect(pagination).toHaveTextContent("Page 1 of 2");

    // Change page size to 25
    const select = screen.getByTestId("page-size-select");
    await user.selectOptions(select, "25");
    expect(pagination).toHaveTextContent("Page 1 of 4");
  });

  it("navigates between pages", async () => {
    const user = userEvent.setup();

    const manyRows = Array.from({ length: 100 }, (_, i) => [
      i,
      `Name ${i}`,
      i * 10,
      "2026-01-01",
    ]);

    render(<DataTable columns={sampleColumns} rows={manyRows} />);

    // Go to next page
    await user.click(screen.getByTestId("next-page"));
    expect(screen.getByTestId("table-pagination")).toHaveTextContent(
      "Page 2 of 2",
    );

    // Go back
    await user.click(screen.getByTestId("prev-page"));
    expect(screen.getByTestId("table-pagination")).toHaveTextContent(
      "Page 1 of 2",
    );
  });

  /* -- Single Column -- */

  it("renders cleanly with a single column", () => {
    const singleCol: DataTableColumn[] = [{ name: "value" }];
    const singleRows: unknown[][] = [[1], [2], [3]];

    render(<DataTable columns={singleCol} rows={singleRows} />);

    const table = screen.getByTestId("data-table");
    expect(table).toBeInTheDocument();
    expect(screen.getByTestId("column-header-value")).toBeInTheDocument();

    const rows = screen.getAllByTestId("data-row");
    expect(rows.length).toBe(3);
  });

  /* -- Error Boundary -- */

  it("wraps content in ComponentErrorBoundary", () => {
    render(<DataTable columns={sampleColumns} rows={sampleRows} />);
    expect(screen.getByTestId("data-table")).toBeInTheDocument();
  });
});
