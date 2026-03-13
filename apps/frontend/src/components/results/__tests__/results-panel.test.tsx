import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { ResultsPanel } from "../results-panel";
import { useResultsStore } from "@/stores/results-store";
import type { QueryResult } from "@/stores/results-store";

// Mock the useTheme hook
vi.mock("@/hooks/use-theme", () => ({
  useTheme: () => ({
    theme: "light" as const,
    resolvedTheme: "light" as const,
    setTheme: () => {},
  }),
}));

// Mock react-plotly.js
vi.mock("react-plotly.js", () => ({
  __esModule: true,
  default: () => <div data-testid="plotly-mock">Plotly Chart</div>,
}));

function makeResult(overrides: Partial<QueryResult> = {}): QueryResult {
  return {
    id: `result-${Math.random().toString(36).slice(2)}`,
    title: "Test Query",
    sql: "SELECT * FROM users",
    data: [{ name: "Alice", age: 30 }],
    columns: ["name", "age"],
    rowCount: 1,
    explanation: "Returns all users",
    chartConfig: null,
    error: null,
    source: "chat",
    createdAt: Date.now(),
    isExpanded: true,
    ...overrides,
  };
}

describe("ResultsPanel", () => {
  beforeEach(() => {
    useResultsStore.setState({ results: [], sortNewestFirst: true });
  });

  it("displays empty state when no results", () => {
    render(<ResultsPanel />);

    const emptyState = screen.getByTestId("results-empty-state");
    expect(emptyState).toBeInTheDocument();
    expect(screen.getByText("No results yet")).toBeInTheDocument();
    expect(
      screen.getByText(/Ask a question in the chat/),
    ).toBeInTheDocument();
  });

  it("renders cards in correct order", () => {
    const result1 = makeResult({ id: "result-1", title: "First Query", createdAt: 1000 });
    const result2 = makeResult({ id: "result-2", title: "Second Query", createdAt: 2000 });

    useResultsStore.setState({
      results: [result2, result1],
      sortNewestFirst: true,
    });

    render(<ResultsPanel />);

    expect(screen.getByTestId("results-panel")).toBeInTheDocument();
    expect(screen.getByTestId("result-card-result-2")).toBeInTheDocument();
    expect(screen.getByTestId("result-card-result-1")).toBeInTheDocument();

    const cards = screen.getAllByTestId(/^result-card-/);
    expect(cards).toHaveLength(2);
    expect(cards[0]).toHaveAttribute("data-testid", "result-card-result-2");
    expect(cards[1]).toHaveAttribute("data-testid", "result-card-result-1");
  });

  it("shows result count", () => {
    useResultsStore.setState({
      results: [makeResult({ id: "r1" }), makeResult({ id: "r2" }), makeResult({ id: "r3" })],
    });

    render(<ResultsPanel />);

    expect(screen.getByText("3 results")).toBeInTheDocument();
  });

  it("shows singular 'result' for single result", () => {
    useResultsStore.setState({
      results: [makeResult({ id: "r1" })],
    });

    render(<ResultsPanel />);

    expect(screen.getByText("1 result")).toBeInTheDocument();
  });

  it("can clear all results", async () => {
    const user = userEvent.setup();
    useResultsStore.setState({
      results: [makeResult({ id: "r1" }), makeResult({ id: "r2" })],
    });

    render(<ResultsPanel />);
    expect(screen.getByTestId("results-panel")).toBeInTheDocument();

    await user.click(screen.getByTestId("clear-results"));

    expect(screen.getByTestId("results-empty-state")).toBeInTheDocument();
  });

  it("can remove individual result", async () => {
    const user = userEvent.setup();
    useResultsStore.setState({
      results: [
        makeResult({ id: "r1", title: "Query 1" }),
        makeResult({ id: "r2", title: "Query 2" }),
      ],
    });

    render(<ResultsPanel />);

    await user.click(screen.getByTestId("remove-result-r1"));

    expect(screen.queryByTestId("result-card-r1")).not.toBeInTheDocument();
    expect(screen.getByTestId("result-card-r2")).toBeInTheDocument();
  });

  it("can toggle card expanded/collapsed state", async () => {
    const user = userEvent.setup();
    useResultsStore.setState({
      results: [makeResult({ id: "r1", isExpanded: true, sql: "SELECT 1" })],
    });

    render(<ResultsPanel />);

    // SQL section should be visible when expanded
    expect(screen.getByTestId("result-sql-section-r1")).toBeInTheDocument();

    // Collapse the card
    await user.click(screen.getByTestId("toggle-expand-r1"));

    // SQL section should not be visible when collapsed
    expect(screen.queryByTestId("result-sql-section-r1")).not.toBeInTheDocument();
  });

  it("scrollable container exists for overflow", () => {
    useResultsStore.setState({
      results: [makeResult({ id: "r1" })],
    });

    render(<ResultsPanel />);

    const scrollContainer = screen.getByTestId("results-scroll-container");
    expect(scrollContainer).toBeInTheDocument();
    expect(scrollContainer.className).toContain("overflow-y-auto");
  });

  it("cards have entrance animation class", () => {
    useResultsStore.setState({
      results: [makeResult({ id: "r1" })],
    });

    render(<ResultsPanel />);

    const card = screen.getByTestId("result-card-r1");
    expect(card.className).toContain("animate-result-card-enter");
  });

  it("can toggle sort order", async () => {
    const user = userEvent.setup();
    useResultsStore.setState({
      results: [
        makeResult({ id: "r1", title: "First" }),
        makeResult({ id: "r2", title: "Second" }),
      ],
      sortNewestFirst: true,
    });

    render(<ResultsPanel />);

    expect(screen.getByText("Newest")).toBeInTheDocument();

    await user.click(screen.getByTestId("toggle-sort-order"));

    expect(screen.getByText("Oldest")).toBeInTheDocument();
  });
});
