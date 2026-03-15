import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { InlineSqlBlock } from "../inline-sql-block";
import { useSqlEditorStore } from "@/stores/sql-editor-store";

// Mock useNavigate
const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe("InlineSqlBlock - Open in SQL Editor", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset SQL editor store
    useSqlEditorStore.setState({
      tabs: [
        {
          id: "tab-1",
          title: "Query 1",
          content: "",
          cursorPosition: { line: 1, col: 1 },
          isExecuting: false,
          error: null,
          results: [],
          executionTimeMs: null,
        },
      ],
      activeTabId: "tab-1",
      selectedSource: null,
      abortControllers: new Map(),
    });
  });

  it("renders 'Open in SQL Editor' button on SQL block", () => {
    render(
      <MemoryRouter>
        <InlineSqlBlock sql="SELECT * FROM users" />
      </MemoryRouter>,
    );

    expect(screen.getByTestId("open-in-editor-button")).toBeInTheDocument();
  });

  it("clicking 'Open in SQL Editor' creates a new tab with the query and navigates to /sql", async () => {
    const user = userEvent.setup();
    const testSql = "SELECT * FROM orders WHERE status = 'active'";

    render(
      <MemoryRouter>
        <InlineSqlBlock sql={testSql} />
      </MemoryRouter>,
    );

    await user.click(screen.getByTestId("open-in-editor-button"));

    // Should have created a new tab with the SQL content
    const store = useSqlEditorStore.getState();
    const newTab = store.tabs.find((t) => t.content === testSql);
    expect(newTab).toBeDefined();
    expect(newTab?.title).toBe("Chat Query");

    // Should navigate to the SQL editor page
    expect(mockNavigate).toHaveBeenCalledWith("/sql");
  });

  it("handles very long SQL - button still accessible", () => {
    const longSql = "SELECT " + "col_name, ".repeat(200) + "id FROM very_long_table WHERE " + "condition AND ".repeat(100) + "final_condition";

    render(
      <MemoryRouter>
        <InlineSqlBlock sql={longSql} />
      </MemoryRouter>,
    );

    const button = screen.getByTestId("open-in-editor-button");
    expect(button).toBeInTheDocument();
    expect(button).not.toBeDisabled();
  });
});
