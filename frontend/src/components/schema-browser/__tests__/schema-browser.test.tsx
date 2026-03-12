import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { SchemaBrowser } from "../schema-browser";
import type { SchemaSource } from "@/types/api";

// Mock the useSchema hook
const mockUseSchema = vi.fn();
vi.mock("@/hooks/use-schema", () => ({
  useSchema: () => mockUseSchema(),
}));

function makeSources(overrides: Partial<SchemaSource>[] = []): SchemaSource[] {
  const defaults: SchemaSource[] = [
    {
      source_id: "src-1",
      source_type: "dataset",
      source_name: "Sales Data",
      tables: [
        {
          table_name: "orders",
          columns: [
            { name: "id", type: "INTEGER", nullable: false, is_primary_key: true },
            { name: "customer_id", type: "INTEGER", nullable: false, is_primary_key: false, foreign_key_ref: "customers.id" },
            { name: "total", type: "DOUBLE", nullable: true, is_primary_key: false },
          ],
        },
        {
          table_name: "products",
          columns: [
            { name: "id", type: "INTEGER", nullable: false, is_primary_key: true },
            { name: "name", type: "VARCHAR", nullable: false, is_primary_key: false },
          ],
        },
      ],
    },
    {
      source_id: "src-2",
      source_type: "connection",
      source_name: "Production DB",
      tables: [
        {
          table_name: "users",
          columns: [
            { name: "id", type: "UUID", nullable: false, is_primary_key: true },
            { name: "email", type: "VARCHAR", nullable: false, is_primary_key: false },
          ],
        },
      ],
    },
  ];

  if (overrides.length > 0) {
    return overrides.map((o, i) => ({ ...defaults[i % defaults.length], ...o }));
  }
  return defaults;
}

describe("SchemaBrowser", () => {
  beforeEach(() => {
    mockUseSchema.mockReturnValue({
      data: { sources: makeSources() },
      isLoading: false,
      isError: false,
      error: null,
    });
  });

  it("renders the schema browser with header and source count", () => {
    render(<SchemaBrowser />);

    expect(screen.getByTestId("schema-browser")).toBeInTheDocument();
    expect(screen.getByText("Schema Browser")).toBeInTheDocument();
    expect(screen.getByText("2 sources")).toBeInTheDocument();
  });

  it("displays loading state", () => {
    mockUseSchema.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
    });

    render(<SchemaBrowser />);

    expect(screen.getByText("Loading schema...")).toBeInTheDocument();
  });

  it("displays error state", () => {
    mockUseSchema.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error("Network error"),
    });

    render(<SchemaBrowser />);

    expect(screen.getByText("Network error")).toBeInTheDocument();
  });

  it("displays empty state when no sources", () => {
    mockUseSchema.mockReturnValue({
      data: { sources: [] },
      isLoading: false,
      isError: false,
      error: null,
    });

    render(<SchemaBrowser />);

    expect(screen.getByTestId("schema-empty-state")).toBeInTheDocument();
    expect(screen.getByText("No data sources")).toBeInTheDocument();
  });

  it("shows dataset icon for dataset sources", () => {
    render(<SchemaBrowser />);

    const source1 = screen.getByTestId("source-src-1");
    expect(within(source1).getByTestId("icon-dataset")).toBeInTheDocument();
  });

  it("shows connection icon for connection sources", () => {
    render(<SchemaBrowser />);

    const source2 = screen.getByTestId("source-src-2");
    expect(within(source2).getByTestId("icon-connection")).toBeInTheDocument();
  });

  it("shows source names and table counts", () => {
    render(<SchemaBrowser />);

    expect(screen.getByText("Sales Data")).toBeInTheDocument();
    expect(screen.getByText("2 tables")).toBeInTheDocument();
    expect(screen.getByText("Production DB")).toBeInTheDocument();
    expect(screen.getByText("1 table")).toBeInTheDocument();
  });

  it("expands source to show tables on click", async () => {
    const user = userEvent.setup();
    render(<SchemaBrowser />);

    // Tables should not be visible initially
    expect(screen.queryByTestId("table-orders")).not.toBeInTheDocument();

    // Click to expand the first source
    await user.click(screen.getByTestId("source-toggle-src-1"));

    // Tables should be visible now
    expect(screen.getByTestId("table-orders")).toBeInTheDocument();
    expect(screen.getByTestId("table-products")).toBeInTheDocument();
  });

  it("expands table to show columns with types", async () => {
    const user = userEvent.setup();
    render(<SchemaBrowser />);

    // Expand source first
    await user.click(screen.getByTestId("source-toggle-src-1"));

    // Columns should not be visible
    expect(screen.queryByTestId("column-id")).not.toBeInTheDocument();

    // Expand orders table
    await user.click(screen.getByTestId("table-toggle-orders"));

    // Columns should be visible with types
    expect(screen.getByTestId("column-id")).toBeInTheDocument();
    expect(screen.getByTestId("column-customer_id")).toBeInTheDocument();
    expect(screen.getByTestId("column-total")).toBeInTheDocument();

    // Check types are displayed
    const idCol = screen.getByTestId("column-id");
    expect(within(idCol).getByText("INTEGER")).toBeInTheDocument();
  });

  it("shows PK badge for primary key columns", async () => {
    const user = userEvent.setup();
    render(<SchemaBrowser />);

    await user.click(screen.getByTestId("source-toggle-src-1"));
    await user.click(screen.getByTestId("table-toggle-orders"));

    const idCol = screen.getByTestId("column-id");
    expect(within(idCol).getByTestId("badge-pk")).toBeInTheDocument();
    expect(within(idCol).getByText("PK")).toBeInTheDocument();
  });

  it("shows FK badge for foreign key columns", async () => {
    const user = userEvent.setup();
    render(<SchemaBrowser />);

    await user.click(screen.getByTestId("source-toggle-src-1"));
    await user.click(screen.getByTestId("table-toggle-orders"));

    const fkCol = screen.getByTestId("column-customer_id");
    expect(within(fkCol).getByTestId("badge-fk")).toBeInTheDocument();
    expect(within(fkCol).getByText("FK")).toBeInTheDocument();
  });

  it("shows NULL badge for nullable non-PK columns", async () => {
    const user = userEvent.setup();
    render(<SchemaBrowser />);

    await user.click(screen.getByTestId("source-toggle-src-1"));
    await user.click(screen.getByTestId("table-toggle-orders"));

    const nullableCol = screen.getByTestId("column-total");
    expect(within(nullableCol).getByTestId("badge-nullable")).toBeInTheDocument();
  });

  it("collapses expanded source on second click", async () => {
    const user = userEvent.setup();
    render(<SchemaBrowser />);

    // Expand
    await user.click(screen.getByTestId("source-toggle-src-1"));
    expect(screen.getByTestId("table-orders")).toBeInTheDocument();

    // Collapse
    await user.click(screen.getByTestId("source-toggle-src-1"));
    expect(screen.queryByTestId("table-orders")).not.toBeInTheDocument();
  });

  it("filters sources by search query matching source name", async () => {
    const user = userEvent.setup();
    render(<SchemaBrowser />);

    const searchInput = screen.getByTestId("schema-search-input");
    await user.type(searchInput, "Sales");

    // "Sales Data" source should be visible
    expect(screen.getByTestId("source-src-1")).toBeInTheDocument();
    // "Production DB" source should not
    expect(screen.queryByTestId("source-src-2")).not.toBeInTheDocument();
  });

  it("filters by table name", async () => {
    const user = userEvent.setup();
    render(<SchemaBrowser />);

    await user.type(screen.getByTestId("schema-search-input"), "users");

    // Only "Production DB" should show (contains "users" table)
    expect(screen.getByTestId("source-src-2")).toBeInTheDocument();
    expect(screen.queryByTestId("source-src-1")).not.toBeInTheDocument();
  });

  it("filters by column name", async () => {
    const user = userEvent.setup();
    render(<SchemaBrowser />);

    await user.type(screen.getByTestId("schema-search-input"), "email");

    // Only "Production DB" should show (contains column "email")
    expect(screen.getByTestId("source-src-2")).toBeInTheDocument();
    expect(screen.queryByTestId("source-src-1")).not.toBeInTheDocument();
  });

  it("shows no results message when search matches nothing", async () => {
    const user = userEvent.setup();
    render(<SchemaBrowser />);

    await user.type(screen.getByTestId("schema-search-input"), "zzzznonexistent");

    expect(screen.getByTestId("schema-no-results")).toBeInTheDocument();
    expect(screen.getByText(/No results for/)).toBeInTheDocument();
  });

  it("clears search when clear button is clicked", async () => {
    const user = userEvent.setup();
    render(<SchemaBrowser />);

    const searchInput = screen.getByTestId("schema-search-input");
    await user.type(searchInput, "Sales");

    // Only one source visible
    expect(screen.queryByTestId("source-src-2")).not.toBeInTheDocument();

    // Clear search
    await user.click(screen.getByTestId("schema-search-clear"));

    // Both sources should be visible again
    expect(screen.getByTestId("source-src-1")).toBeInTheDocument();
    expect(screen.getByTestId("source-src-2")).toBeInTheDocument();
  });

  it("auto-expands nodes when searching", async () => {
    const user = userEvent.setup();
    render(<SchemaBrowser />);

    await user.type(screen.getByTestId("schema-search-input"), "email");

    // Source and table should be auto-expanded when searching
    expect(screen.getByTestId("table-users")).toBeInTheDocument();
    expect(screen.getByTestId("column-email")).toBeInTheDocument();
  });

  it("shows column count for each table", async () => {
    const user = userEvent.setup();
    render(<SchemaBrowser />);

    await user.click(screen.getByTestId("source-toggle-src-1"));

    expect(screen.getByText("3 cols")).toBeInTheDocument();
    expect(screen.getByText("2 cols")).toBeInTheDocument();
  });

  it("has scrollable tree container", () => {
    render(<SchemaBrowser />);

    const container = screen.getByTestId("schema-tree-container");
    expect(container.className).toContain("overflow-y-auto");
  });

  it("shows singular 'source' for single source", () => {
    mockUseSchema.mockReturnValue({
      data: {
        sources: [makeSources()[0]],
      },
      isLoading: false,
      isError: false,
      error: null,
    });

    render(<SchemaBrowser />);

    expect(screen.getByText("1 source")).toBeInTheDocument();
  });
});
