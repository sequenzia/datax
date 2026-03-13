import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { SqlResultsPanel } from "../sql-results-panel";
import type { QueryResult } from "@/stores/results-store";

function makeResult(overrides: Partial<QueryResult> = {}): QueryResult {
  return {
    id: `result-${Math.random().toString(36).slice(2)}`,
    title: "Test Query",
    sql: "SELECT * FROM users",
    data: [{ name: "Alice", age: 30 }],
    columns: ["name", "age"],
    rowCount: 1,
    explanation: null,
    chartConfig: null,
    error: null,
    source: "sql-editor",
    createdAt: Date.now(),
    isExpanded: true,
    ...overrides,
  };
}

describe("SqlResultsPanel", () => {
  it("shows empty state when no results", () => {
    render(
      <SqlResultsPanel results={[]} isExecuting={false} error={null} />,
    );

    expect(screen.getByTestId("sql-results-empty")).toBeInTheDocument();
    expect(screen.getByText("No results")).toBeInTheDocument();
    expect(
      screen.getByText(/Cmd\/Ctrl\+Enter to execute/),
    ).toBeInTheDocument();
  });

  it("shows loading state while executing", () => {
    render(
      <SqlResultsPanel results={[]} isExecuting={true} error={null} />,
    );

    expect(screen.getByTestId("sql-results-loading")).toBeInTheDocument();
    expect(screen.getByText("Executing query...")).toBeInTheDocument();
  });

  it("shows error state with error message", () => {
    render(
      <SqlResultsPanel
        results={[]}
        isExecuting={false}
        error="Syntax error at position 10: unexpected token 'FORM'"
      />,
    );

    expect(screen.getByTestId("sql-results-error")).toBeInTheDocument();
    expect(screen.getByText("Query Error")).toBeInTheDocument();
    expect(
      screen.getByText(/Syntax error at position 10/),
    ).toBeInTheDocument();
  });

  it("shows timeout suggestion for timeout errors", () => {
    render(
      <SqlResultsPanel
        results={[]}
        isExecuting={false}
        error="Query timeout after 30 seconds"
      />,
    );

    expect(
      screen.getByText(/Try simplifying your query/),
    ).toBeInTheDocument();
  });

  it("renders result cards with data", () => {
    const results = [
      makeResult({
        id: "r1",
        title: "Users",
        sql: "SELECT * FROM users",
        data: [
          { name: "Alice", age: 30 },
          { name: "Bob", age: 25 },
        ],
        columns: ["name", "age"],
        rowCount: 2,
      }),
    ];

    render(
      <SqlResultsPanel results={results} isExecuting={false} error={null} />,
    );

    expect(screen.getByTestId("sql-results-panel")).toBeInTheDocument();
    expect(screen.getByTestId("sql-result-card-r1")).toBeInTheDocument();
    expect(screen.getByText("Users")).toBeInTheDocument();
    expect(screen.getByText("2 rows")).toBeInTheDocument();
    expect(screen.getByText("Alice")).toBeInTheDocument();
    expect(screen.getByText("Bob")).toBeInTheDocument();
  });

  it("renders multiple result cards", () => {
    const results = [
      makeResult({ id: "r1", title: "First" }),
      makeResult({ id: "r2", title: "Second" }),
    ];

    render(
      <SqlResultsPanel results={results} isExecuting={false} error={null} />,
    );

    expect(screen.getByTestId("sql-result-card-r1")).toBeInTheDocument();
    expect(screen.getByTestId("sql-result-card-r2")).toBeInTheDocument();
  });

  it("handles results with no data gracefully", () => {
    const results = [
      makeResult({
        id: "r1",
        title: "Insert",
        data: [],
        columns: [],
        rowCount: 0,
      }),
    ];

    render(
      <SqlResultsPanel results={results} isExecuting={false} error={null} />,
    );

    expect(
      screen.getByText("Query executed successfully. No data returned."),
    ).toBeInTheDocument();
  });

  it("shows singular 'row' for single row result", () => {
    const results = [
      makeResult({
        id: "r1",
        data: [{ count: 42 }],
        columns: ["count"],
        rowCount: 1,
      }),
    ];

    render(
      <SqlResultsPanel results={results} isExecuting={false} error={null} />,
    );

    expect(screen.getByText("1 row")).toBeInTheDocument();
  });
});
