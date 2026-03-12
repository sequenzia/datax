import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ResultCard } from "../result-card";
import type { QueryResult } from "@/stores/results-store";

// Mock react-plotly.js for chart rendering in result cards
vi.mock("react-plotly.js", () => ({
  __esModule: true,
  default: () => <div data-testid="plotly-mock">Plotly Chart</div>,
}));

function makeResult(overrides: Partial<QueryResult> = {}): QueryResult {
  return {
    id: "r1",
    title: "Test Query",
    sql: "SELECT * FROM users WHERE age > 30",
    data: [
      { name: "Alice", age: 30 },
      { name: "Bob", age: 25 },
    ],
    columns: ["name", "age"],
    rowCount: 2,
    explanation: "Returns all users over 30",
    chartConfig: null,
    error: null,
    source: "chat",
    createdAt: Date.now(),
    isExpanded: true,
    ...overrides,
  };
}

const defaultProps = {
  onToggleExpanded: vi.fn(),
  onRemove: vi.fn(),
};

describe("ResultCard", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe("Card sections", () => {
    it("renders header with title, source, and timestamp", () => {
      render(<ResultCard result={makeResult()} {...defaultProps} />);

      expect(screen.getByText("Test Query")).toBeInTheDocument();
      expect(screen.getByText("Chat")).toBeInTheDocument();
    });

    it("shows SQL Editor as source label for sql-editor source", () => {
      render(
        <ResultCard
          result={makeResult({ source: "sql-editor" })}
          {...defaultProps}
        />,
      );

      expect(screen.getByText("SQL Editor")).toBeInTheDocument();
    });

    it("renders SQL section with syntax highlighting", () => {
      render(<ResultCard result={makeResult()} {...defaultProps} />);

      const sqlCode = screen.getByTestId("result-sql-code-r1");
      expect(sqlCode).toBeInTheDocument();

      // SQL keywords should be wrapped in spans with font-semibold class
      const keywordSpans = sqlCode.querySelectorAll("span.font-semibold");
      expect(keywordSpans.length).toBeGreaterThan(0);

      // Check SELECT keyword is highlighted
      const keywordTexts = Array.from(keywordSpans).map(
        (span) => span.textContent,
      );
      expect(keywordTexts).toContain("SELECT");
      expect(keywordTexts).toContain("FROM");
      expect(keywordTexts).toContain("WHERE");
    });

    it("renders data table with correct columns and rows", () => {
      render(<ResultCard result={makeResult()} {...defaultProps} />);

      const tableSection = screen.getByTestId("result-table-section-r1");
      expect(tableSection).toBeInTheDocument();

      // Column headers exist via sort buttons
      expect(screen.getByTestId("sort-column-name")).toBeInTheDocument();
      expect(screen.getByTestId("sort-column-age")).toBeInTheDocument();

      // Data cells
      expect(screen.getByText("Alice")).toBeInTheDocument();
      expect(screen.getByText("Bob")).toBeInTheDocument();
    });

    it("renders row count", () => {
      render(<ResultCard result={makeResult()} {...defaultProps} />);
      expect(screen.getByText("Results (2 rows)")).toBeInTheDocument();
    });

    it("renders singular row for single row result", () => {
      render(
        <ResultCard
          result={makeResult({
            data: [{ name: "Alice", age: 30 }],
            rowCount: 1,
          })}
          {...defaultProps}
        />,
      );
      expect(screen.getByText("Results (1 row)")).toBeInTheDocument();
    });

    it("renders AI explanation", () => {
      render(<ResultCard result={makeResult()} {...defaultProps} />);

      const explanation = screen.getByTestId("result-explanation-r1");
      expect(explanation).toBeInTheDocument();
      expect(screen.getByText("Returns all users over 30")).toBeInTheDocument();
    });

    it("renders chart section when chart config present", () => {
      render(
        <ResultCard
          result={makeResult({
            chartConfig: {
              type: "bar",
              data: [{ type: "bar", x: ["A"], y: [1] }],
            },
          })}
          {...defaultProps}
        />,
      );

      expect(
        screen.getByTestId("result-chart-r1"),
      ).toBeInTheDocument();
    });

    it("does not render chart section when no chart config", () => {
      render(
        <ResultCard
          result={makeResult({ chartConfig: null })}
          {...defaultProps}
        />,
      );

      expect(
        screen.queryByTestId("result-chart-r1"),
      ).not.toBeInTheDocument();
    });
  });

  describe("Collapsible SQL", () => {
    it("SQL is expanded by default", () => {
      render(<ResultCard result={makeResult()} {...defaultProps} />);

      expect(screen.getByTestId("result-sql-code-r1")).toBeInTheDocument();
    });

    it("toggles SQL section collapsed/expanded", async () => {
      const user = userEvent.setup();
      render(<ResultCard result={makeResult()} {...defaultProps} />);

      // SQL is visible
      expect(screen.getByTestId("result-sql-code-r1")).toBeInTheDocument();

      // Click to collapse
      await user.click(screen.getByTestId("toggle-sql-r1"));

      // SQL should be hidden
      expect(
        screen.queryByTestId("result-sql-code-r1"),
      ).not.toBeInTheDocument();

      // Click to expand again
      await user.click(screen.getByTestId("toggle-sql-r1"));

      // SQL should be visible again
      expect(screen.getByTestId("result-sql-code-r1")).toBeInTheDocument();
    });
  });

  describe("Table sorting", () => {
    it("sorts column ascending on first click", async () => {
      const user = userEvent.setup();
      const result = makeResult({
        data: [
          { name: "Charlie", age: 35 },
          { name: "Alice", age: 30 },
          { name: "Bob", age: 25 },
        ],
        rowCount: 3,
      });
      render(<ResultCard result={result} {...defaultProps} />);

      await user.click(screen.getByTestId("sort-column-name"));

      // Check ascending indicator
      expect(screen.getByTestId("sort-asc-name")).toBeInTheDocument();

      // Check order: Alice, Bob, Charlie
      const rows = screen
        .getAllByRole("row")
        .slice(1); // skip header
      expect(within(rows[0]).getByText("Alice")).toBeInTheDocument();
      expect(within(rows[1]).getByText("Bob")).toBeInTheDocument();
      expect(within(rows[2]).getByText("Charlie")).toBeInTheDocument();
    });

    it("sorts column descending on second click", async () => {
      const user = userEvent.setup();
      const result = makeResult({
        data: [
          { name: "Alice", age: 30 },
          { name: "Charlie", age: 35 },
          { name: "Bob", age: 25 },
        ],
        rowCount: 3,
      });
      render(<ResultCard result={result} {...defaultProps} />);

      // First click: ascending
      await user.click(screen.getByTestId("sort-column-name"));
      // Second click: descending
      await user.click(screen.getByTestId("sort-column-name"));

      expect(screen.getByTestId("sort-desc-name")).toBeInTheDocument();

      const rows = screen
        .getAllByRole("row")
        .slice(1);
      expect(within(rows[0]).getByText("Charlie")).toBeInTheDocument();
      expect(within(rows[1]).getByText("Bob")).toBeInTheDocument();
      expect(within(rows[2]).getByText("Alice")).toBeInTheDocument();
    });

    it("clears sort on third click", async () => {
      const user = userEvent.setup();
      const result = makeResult({
        data: [
          { name: "Charlie", age: 35 },
          { name: "Alice", age: 30 },
        ],
        rowCount: 2,
      });
      render(<ResultCard result={result} {...defaultProps} />);

      // Click three times to cycle: none -> asc -> desc -> none
      await user.click(screen.getByTestId("sort-column-name"));
      await user.click(screen.getByTestId("sort-column-name"));
      await user.click(screen.getByTestId("sort-column-name"));

      expect(screen.queryByTestId("sort-asc-name")).not.toBeInTheDocument();
      expect(screen.queryByTestId("sort-desc-name")).not.toBeInTheDocument();
    });

    it("sorts numeric columns correctly", async () => {
      const user = userEvent.setup();
      const result = makeResult({
        data: [
          { name: "Alice", age: 30 },
          { name: "Bob", age: 5 },
          { name: "Charlie", age: 100 },
        ],
        rowCount: 3,
      });
      render(<ResultCard result={result} {...defaultProps} />);

      await user.click(screen.getByTestId("sort-column-age"));

      const rows = screen
        .getAllByRole("row")
        .slice(1);
      expect(within(rows[0]).getByText("5")).toBeInTheDocument();
      expect(within(rows[1]).getByText("30")).toBeInTheDocument();
      expect(within(rows[2]).getByText("100")).toBeInTheDocument();
    });
  });

  describe("CSV export", () => {
    it("renders CSV export button", () => {
      render(<ResultCard result={makeResult()} {...defaultProps} />);

      const csvButton = screen.getByTestId("export-csv-r1");
      expect(csvButton).toBeInTheDocument();
    });

    it("triggers download on CSV export click", async () => {
      const user = userEvent.setup();
      const createObjectURL = vi.fn(() => "blob:test-url");
      const revokeObjectURL = vi.fn();
      const clickMock = vi.fn();

      // Mock URL methods
      global.URL.createObjectURL = createObjectURL;
      global.URL.revokeObjectURL = revokeObjectURL;

      // Mock createElement to intercept the download link
      const originalCreateElement = document.createElement.bind(document);
      vi.spyOn(document, "createElement").mockImplementation((tagName: string) => {
        const el = originalCreateElement(tagName);
        if (tagName === "a") {
          Object.defineProperty(el, "click", { value: clickMock });
        }
        return el;
      });

      render(<ResultCard result={makeResult()} {...defaultProps} />);

      await user.click(screen.getByTestId("export-csv-r1"));

      expect(createObjectURL).toHaveBeenCalled();
      expect(clickMock).toHaveBeenCalled();
      expect(revokeObjectURL).toHaveBeenCalledWith("blob:test-url");
    });
  });

  describe("Long value truncation", () => {
    it("truncates values longer than 100 characters with tooltip", () => {
      const longValue = "A".repeat(150);
      render(
        <ResultCard
          result={makeResult({
            data: [{ name: longValue, age: 30 }],
            rowCount: 1,
          })}
          {...defaultProps}
        />,
      );

      const truncatedCell = screen.getByTestId("truncated-cell-0-name");
      expect(truncatedCell).toBeInTheDocument();
      // Should show truncated text (100 chars + "...")
      expect(truncatedCell.textContent).toBe("A".repeat(100) + "...");
      // Should have full value as title attribute for tooltip
      expect(truncatedCell).toHaveAttribute("title", longValue);
    });

    it("does not truncate short values", () => {
      render(
        <ResultCard
          result={makeResult({
            data: [{ name: "Short", age: 30 }],
            rowCount: 1,
          })}
          {...defaultProps}
        />,
      );

      expect(
        screen.queryByTestId("truncated-cell-0-name"),
      ).not.toBeInTheDocument();
    });
  });

  describe("Edge cases", () => {
    it("handles 0 rows with empty data message", () => {
      render(
        <ResultCard
          result={makeResult({
            data: [],
            columns: [],
            rowCount: 0,
            explanation: null,
          })}
          {...defaultProps}
        />,
      );

      expect(
        screen.getByTestId("result-empty-data-r1"),
      ).toBeInTheDocument();
      expect(
        screen.getByText("No data returned by this query."),
      ).toBeInTheDocument();
    });

    it("handles null data with empty data message", () => {
      render(
        <ResultCard
          result={makeResult({
            data: null,
            columns: [],
            rowCount: 0,
            explanation: null,
          })}
          {...defaultProps}
        />,
      );

      expect(
        screen.getByText("No data returned by this query."),
      ).toBeInTheDocument();
    });

    it("displays NULL values in italic for null cells", () => {
      render(
        <ResultCard
          result={makeResult({
            data: [{ name: null, age: 30 }],
            columns: ["name", "age"],
            rowCount: 1,
          })}
          {...defaultProps}
        />,
      );

      // Find cell with "NULL" text
      const cells = screen.getAllByRole("cell");
      const nullCell = cells.find((cell) => cell.textContent === "NULL");
      expect(nullCell).toBeDefined();
      expect(nullCell!.className).toContain("italic");
    });

    it("handles all NULL column", () => {
      render(
        <ResultCard
          result={makeResult({
            data: [
              { name: null, age: 30 },
              { name: null, age: 25 },
            ],
            columns: ["name", "age"],
            rowCount: 2,
          })}
          {...defaultProps}
        />,
      );

      const cells = screen.getAllByRole("cell");
      const nullCells = cells.filter((cell) => cell.textContent === "NULL");
      expect(nullCells.length).toBe(2);
      nullCells.forEach((cell) => {
        expect(cell.className).toContain("italic");
      });
    });

    it("paginates large result sets (over 100 rows)", () => {
      const largeData = Array.from({ length: 250 }, (_, i) => ({
        id: i,
        name: `User ${i}`,
      }));

      render(
        <ResultCard
          result={makeResult({
            data: largeData,
            columns: ["id", "name"],
            rowCount: 250,
          })}
          {...defaultProps}
        />,
      );

      // Should show pagination
      const pagination = screen.getByTestId("result-pagination-r1");
      expect(pagination).toBeInTheDocument();
      expect(screen.getByText("Page 1 of 3")).toBeInTheDocument();

      // First page should show 100 rows (plus header row)
      const rows = screen.getAllByRole("row");
      expect(rows.length).toBe(101); // 100 data rows + 1 header
    });

    it("navigates between pages", async () => {
      const user = userEvent.setup();
      const largeData = Array.from({ length: 150 }, (_, i) => ({
        id: i,
        name: `User ${i}`,
      }));

      render(
        <ResultCard
          result={makeResult({
            data: largeData,
            columns: ["id", "name"],
            rowCount: 150,
          })}
          {...defaultProps}
        />,
      );

      expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();

      // First page should show User 0
      expect(screen.getByText("User 0")).toBeInTheDocument();

      // Navigate to next page
      await user.click(screen.getByTestId("next-page-r1"));

      expect(screen.getByText("Page 2 of 2")).toBeInTheDocument();
      expect(screen.getByText("User 100")).toBeInTheDocument();

      // Navigate back
      await user.click(screen.getByTestId("prev-page-r1"));
      expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();
    });

    it("alternating rows have different backgrounds", () => {
      render(
        <ResultCard
          result={makeResult({
            data: [
              { name: "Alice", age: 30 },
              { name: "Bob", age: 25 },
              { name: "Charlie", age: 35 },
            ],
            rowCount: 3,
          })}
          {...defaultProps}
        />,
      );

      const rows = screen.getAllByRole("row").slice(1); // skip header
      // Odd-indexed rows (0-based: row index 1) should have bg-muted/25
      expect(rows[1].className).toContain("bg-muted/25");
      // Even-indexed rows should not
      expect(rows[0].className).not.toContain("bg-muted/25");
    });
  });

  describe("Error handling", () => {
    it("displays error card for query errors", () => {
      render(
        <ResultCard
          result={makeResult({
            error: "Syntax error at position 10",
            data: null,
            columns: [],
            rowCount: 0,
          })}
          {...defaultProps}
        />,
      );

      expect(screen.getByTestId("result-error-r1")).toBeInTheDocument();
      expect(
        screen.getByText("Syntax error at position 10"),
      ).toBeInTheDocument();
    });

    it("error card does not show expand/collapse toggle", () => {
      render(
        <ResultCard
          result={makeResult({
            error: "Some error",
            data: null,
            columns: [],
            rowCount: 0,
          })}
          {...defaultProps}
        />,
      );

      expect(
        screen.queryByTestId("toggle-expand-r1"),
      ).not.toBeInTheDocument();
    });

    it("error card still shows remove button", () => {
      render(
        <ResultCard
          result={makeResult({
            error: "Some error",
            data: null,
            columns: [],
            rowCount: 0,
          })}
          {...defaultProps}
        />,
      );

      expect(screen.getByTestId("remove-result-r1")).toBeInTheDocument();
    });
  });

  describe("Horizontal scroll", () => {
    it("table container has overflow-x-auto for horizontal scroll", () => {
      render(<ResultCard result={makeResult()} {...defaultProps} />);

      const scrollContainer = screen.getByTestId("result-table-scroll-r1");
      expect(scrollContainer.className).toContain("overflow-x-auto");
    });
  });
});
