import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { SqlEditorPage } from "../sql-editor";
import { useSqlEditorStore } from "@/stores/sql-editor-store";
import { useResultsStore } from "@/stores/results-store";

// Mock schema completions hook (uses useQuery)
vi.mock("@/hooks/use-schema-completions", () => ({
  useSchemaCompletions: () => ({
    tables: [],
    isLoading: false,
    error: null,
  }),
}));

// Mock sql-completions (completion source factory)
vi.mock("@/lib/sql-completions", () => ({
  createSchemaCompletionSource: () => () => null,
  createKeywordsOnlyCompletionSource: () => () => null,
}));

// Mock the useTheme hook
vi.mock("@/hooks/use-theme", () => ({
  useTheme: () => ({
    theme: "light",
    resolvedTheme: "light",
    setTheme: vi.fn(),
  }),
}));

// Mock CodeEditor since CodeMirror requires a real DOM
vi.mock("@/components/sql-editor/code-editor", () => ({
  CodeEditor: ({
    value,
    onChange,
    onExecute,
    onSave,
  }: {
    value: string;
    onChange: (v: string) => void;
    onExecute: () => void;
    onCursorChange?: (pos: { line: number; col: number }) => void;
    onSave?: () => void;
    darkMode?: boolean;
  }) => (
    <div data-testid="code-editor">
      <textarea
        data-testid="mock-editor-textarea"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      <button data-testid="mock-execute-button" onClick={onExecute}>
        Execute
      </button>
      <button data-testid="mock-save-button" onClick={() => onSave?.()}>
        Save
      </button>
    </div>
  ),
}));

// Track mutation calls for assertions
const mockExecuteMutate = vi.fn();
const mockExplainMutate = vi.fn();
const mockSaveMutate = vi.fn();
const mockDeleteSavedMutate = vi.fn();

// Mock TanStack Query hooks
vi.mock("@/hooks/use-dashboard-data", () => ({
  useDatasets: () => ({
    data: [
      {
        id: "ds-1",
        name: "Sales Data",
        status: "ready",
        file_format: "csv",
        file_size_bytes: 1024,
        row_count: 100,
        created_at: "2026-01-01",
        updated_at: "2026-01-01",
      },
      {
        id: "ds-2",
        name: "Users Data",
        status: "processing",
        file_format: "csv",
        file_size_bytes: 512,
        row_count: null,
        created_at: "2026-01-01",
        updated_at: "2026-01-01",
      },
    ],
    isLoading: false,
  }),
  useConnections: () => ({
    data: [
      {
        id: "conn-1",
        name: "Production DB",
        status: "connected",
        db_type: "postgresql",
        host: "localhost",
        port: 5432,
        database_name: "prod",
        last_tested_at: null,
        created_at: "2026-01-01",
        updated_at: "2026-01-01",
      },
    ],
    isLoading: false,
  }),
}));

vi.mock("@/hooks/use-queries", () => ({
  useExecuteQuery: () => ({
    mutate: mockExecuteMutate,
    isPending: false,
  }),
  useExplainQuery: () => ({
    mutate: mockExplainMutate,
    isPending: false,
  }),
  useSavedQueries: () => ({
    data: [
      {
        id: "sq-1",
        name: "Top Sales",
        sql_content: "SELECT * FROM sales ORDER BY revenue DESC",
        source_id: null,
        source_type: null,
        created_at: "2026-01-01",
        updated_at: "2026-01-01",
      },
    ],
    isLoading: false,
  }),
  useSaveQuery: () => ({
    mutate: mockSaveMutate,
    isPending: false,
  }),
  useUpdateSavedQuery: () => ({
    mutate: vi.fn(),
    isPending: false,
  }),
  useDeleteSavedQuery: () => ({
    mutate: mockDeleteSavedMutate,
    isPending: false,
  }),
  useQueryHistory: () => ({
    data: {
      history: [
        {
          sql: "SELECT count(*) FROM users",
          source_id: "ds-1",
          source_type: "dataset",
          row_count: 1,
          execution_time_ms: 12,
          status: "success",
          executed_at: "2026-01-01T00:00:00Z",
        },
        {
          sql: "SELECT * FROM orders",
          source_id: "conn-1",
          source_type: "connection",
          row_count: 50,
          execution_time_ms: 45,
          status: "success",
          executed_at: "2026-01-01T00:00:00Z",
        },
      ],
      total: 2,
      offset: 0,
      limit: 100,
    },
    isLoading: false,
  }),
}));

describe("SqlEditorPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset stores to initial state
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
    useResultsStore.setState({ results: [], sortNewestFirst: true });
  });

  it("renders the SQL editor page with all sections", () => {
    render(<MemoryRouter><SqlEditorPage /></MemoryRouter>);

    expect(screen.getByTestId("sql-editor-page")).toBeInTheDocument();
    expect(screen.getByTestId("tab-bar")).toBeInTheDocument();
    expect(screen.getByTestId("sql-toolbar")).toBeInTheDocument();
    expect(screen.getByTestId("editor-pane")).toBeInTheDocument();
    expect(screen.getByTestId("results-pane")).toBeInTheDocument();
  });

  it("renders the code editor", () => {
    render(<MemoryRouter><SqlEditorPage /></MemoryRouter>);

    expect(screen.getByTestId("code-editor")).toBeInTheDocument();
  });

  it("shows run, save, and explain buttons in toolbar", () => {
    render(<MemoryRouter><SqlEditorPage /></MemoryRouter>);

    expect(screen.getByTestId("run-query-button")).toBeInTheDocument();
    expect(screen.getByTestId("save-query-button")).toBeInTheDocument();
    expect(screen.getByTestId("explain-button")).toBeInTheDocument();
  });

  it("shows data source selector with available sources", () => {
    render(<MemoryRouter><SqlEditorPage /></MemoryRouter>);

    const selector = screen.getByTestId("data-source-selector");
    expect(selector).toBeInTheDocument();

    const select = screen.getByTestId("source-select");
    // Should show ready datasets and connected connections
    expect(select).toBeInTheDocument();
    // Sales Data (ready) should be an option
    expect(
      within(select).getByText("Sales Data (dataset)"),
    ).toBeInTheDocument();
    // Users Data (processing) should NOT be an option
    expect(
      within(select).queryByText("Users Data (dataset)"),
    ).not.toBeInTheDocument();
    // Production DB (connected) should be an option
    expect(
      within(select).getByText("Production DB (connection)"),
    ).toBeInTheDocument();
  });

  it("shows cursor position in toolbar", () => {
    render(<MemoryRouter><SqlEditorPage /></MemoryRouter>);

    expect(screen.getByTestId("cursor-position")).toHaveTextContent(
      "Ln 1, Col 1",
    );
  });

  it("prevents execution of empty query", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><SqlEditorPage /></MemoryRouter>);

    await user.click(screen.getByTestId("run-query-button"));

    const resultsPane = screen.getByTestId("results-pane");
    expect(
      within(resultsPane).getByTestId("sql-results-error"),
    ).toBeInTheDocument();
  });

  it("shows error when executing without data source selected", async () => {
    const user = userEvent.setup();
    // Set some content so it gets past the empty check
    useSqlEditorStore.setState({
      tabs: [
        {
          id: "tab-1",
          title: "Query 1",
          content: "SELECT 1",
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

    render(<MemoryRouter><SqlEditorPage /></MemoryRouter>);

    await user.click(screen.getByTestId("run-query-button"));

    // Should show error about no data source
    const resultsPane = screen.getByTestId("results-pane");
    expect(
      within(resultsPane).getByTestId("sql-results-error"),
    ).toBeInTheDocument();
  });

  it("calls execute API when source is selected and run is clicked", async () => {
    const user = userEvent.setup();
    useSqlEditorStore.setState({
      tabs: [
        {
          id: "tab-1",
          title: "Query 1",
          content: "SELECT * FROM sales",
          cursorPosition: { line: 1, col: 1 },
          isExecuting: false,
          error: null,
          results: [],
          executionTimeMs: null,
        },
      ],
      activeTabId: "tab-1",
      selectedSource: { id: "ds-1", name: "Sales Data", type: "dataset" },
      abortControllers: new Map(),
    });

    render(<MemoryRouter><SqlEditorPage /></MemoryRouter>);

    await user.click(screen.getByTestId("run-query-button"));

    expect(mockExecuteMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        body: {
          sql: "SELECT * FROM sales",
          source_id: "ds-1",
          source_type: "dataset",
        },
      }),
      expect.any(Object),
    );
  });

  it("creates new tab via add button", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><SqlEditorPage /></MemoryRouter>);

    await user.click(screen.getByTestId("add-tab-button"));

    const tabs = screen.getAllByTestId(/^tab-tab-/);
    expect(tabs.length).toBeGreaterThanOrEqual(2);
  });

  it("can switch between tabs", async () => {
    const user = userEvent.setup();

    useSqlEditorStore.setState({
      tabs: [
        {
          id: "tab-a",
          title: "Tab A",
          content: "SELECT 1",
          cursorPosition: { line: 1, col: 1 },
          isExecuting: false,
          error: null,
          results: [],
          executionTimeMs: null,
        },
        {
          id: "tab-b",
          title: "Tab B",
          content: "SELECT 2",
          cursorPosition: { line: 1, col: 1 },
          isExecuting: false,
          error: null,
          results: [],
          executionTimeMs: null,
        },
      ],
      activeTabId: "tab-a",
      selectedSource: null,
      abortControllers: new Map(),
    });

    render(<MemoryRouter><SqlEditorPage /></MemoryRouter>);

    expect(screen.getByTestId("mock-editor-textarea")).toHaveValue("SELECT 1");

    await user.click(screen.getByText("Tab B"));

    expect(screen.getByTestId("mock-editor-textarea")).toHaveValue("SELECT 2");
  });

  it("maintains independent content per tab", async () => {
    const user = userEvent.setup();

    useSqlEditorStore.setState({
      tabs: [
        {
          id: "tab-a",
          title: "Tab A",
          content: "SELECT * FROM users",
          cursorPosition: { line: 1, col: 1 },
          isExecuting: false,
          error: null,
          results: [],
          executionTimeMs: null,
        },
        {
          id: "tab-b",
          title: "Tab B",
          content: "SELECT * FROM orders",
          cursorPosition: { line: 1, col: 1 },
          isExecuting: false,
          error: null,
          results: [],
          executionTimeMs: null,
        },
      ],
      activeTabId: "tab-a",
      selectedSource: null,
      abortControllers: new Map(),
    });

    render(<MemoryRouter><SqlEditorPage /></MemoryRouter>);

    expect(screen.getByTestId("mock-editor-textarea")).toHaveValue(
      "SELECT * FROM users",
    );

    await user.click(screen.getByText("Tab B"));
    expect(screen.getByTestId("mock-editor-textarea")).toHaveValue(
      "SELECT * FROM orders",
    );

    await user.click(screen.getByText("Tab A"));
    expect(screen.getByTestId("mock-editor-textarea")).toHaveValue(
      "SELECT * FROM users",
    );
  });

  it("can close a tab", async () => {
    const user = userEvent.setup();

    useSqlEditorStore.setState({
      tabs: [
        {
          id: "tab-a",
          title: "Tab A",
          content: "",
          cursorPosition: { line: 1, col: 1 },
          isExecuting: false,
          error: null,
          results: [],
          executionTimeMs: null,
        },
        {
          id: "tab-b",
          title: "Tab B",
          content: "",
          cursorPosition: { line: 1, col: 1 },
          isExecuting: false,
          error: null,
          results: [],
          executionTimeMs: null,
        },
      ],
      activeTabId: "tab-a",
      selectedSource: null,
      abortControllers: new Map(),
    });

    render(<MemoryRouter><SqlEditorPage /></MemoryRouter>);

    await user.click(screen.getByTestId("tab-close-tab-a"));

    expect(screen.queryByTestId("tab-tab-a")).not.toBeInTheDocument();
    expect(screen.getByTestId("tab-tab-b")).toBeInTheDocument();
  });

  it("shows empty results state initially", () => {
    render(<MemoryRouter><SqlEditorPage /></MemoryRouter>);

    expect(screen.getByTestId("sql-results-empty")).toBeInTheDocument();
  });

  it("disables run button while executing", () => {
    useSqlEditorStore.setState({
      tabs: [
        {
          id: "tab-1",
          title: "Query 1",
          content: "SELECT 1",
          cursorPosition: { line: 1, col: 1 },
          isExecuting: true,
          error: null,
          results: [],
          executionTimeMs: null,
        },
      ],
      activeTabId: "tab-1",
      selectedSource: null,
      abortControllers: new Map(),
    });

    render(<MemoryRouter><SqlEditorPage /></MemoryRouter>);

    expect(screen.getByTestId("run-query-button")).toBeDisabled();
  });

  it("shows execution time after query completes", () => {
    useSqlEditorStore.setState({
      tabs: [
        {
          id: "tab-1",
          title: "Query 1",
          content: "SELECT 1",
          cursorPosition: { line: 1, col: 1 },
          isExecuting: false,
          error: null,
          results: [],
          executionTimeMs: 42,
        },
      ],
      activeTabId: "tab-1",
      selectedSource: null,
      abortControllers: new Map(),
    });

    render(<MemoryRouter><SqlEditorPage /></MemoryRouter>);

    expect(screen.getByTestId("execution-time")).toHaveTextContent("42ms");
  });

  it("opens history panel when toggle is clicked", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><SqlEditorPage /></MemoryRouter>);

    await user.click(screen.getByTestId("toggle-history"));

    expect(screen.getByTestId("history-panel")).toBeInTheDocument();
    expect(screen.getByTestId("history-search")).toBeInTheDocument();
    expect(screen.getByTestId("history-entry-0")).toBeInTheDocument();
    expect(screen.getByTestId("history-entry-1")).toBeInTheDocument();
  });

  it("loads query from history when entry is clicked", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><SqlEditorPage /></MemoryRouter>);

    await user.click(screen.getByTestId("toggle-history"));
    await user.click(screen.getByTestId("history-entry-0"));

    // Should load the SQL into the editor
    expect(screen.getByTestId("mock-editor-textarea")).toHaveValue(
      "SELECT count(*) FROM users",
    );
  });

  it("filters history by search term", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><SqlEditorPage /></MemoryRouter>);

    await user.click(screen.getByTestId("toggle-history"));

    const searchInput = screen.getByTestId("history-search");
    await user.type(searchInput, "orders");

    // Only the orders entry should be visible
    expect(screen.queryByTestId("history-entry-0")).toBeInTheDocument();
    expect(screen.queryByTestId("history-entry-1")).not.toBeInTheDocument();
  });

  it("opens saved queries panel when toggle is clicked", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><SqlEditorPage /></MemoryRouter>);

    await user.click(screen.getByTestId("toggle-saved"));

    expect(screen.getByTestId("saved-queries-panel")).toBeInTheDocument();
    expect(screen.getByTestId("saved-query-sq-1")).toBeInTheDocument();
    expect(screen.getByText("Top Sales")).toBeInTheDocument();
  });

  it("loads saved query into editor when clicked", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><SqlEditorPage /></MemoryRouter>);

    await user.click(screen.getByTestId("toggle-saved"));
    // Click on the saved query text to load it
    await user.click(
      screen.getByText("SELECT * FROM sales ORDER BY revenue DESC"),
    );

    expect(screen.getByTestId("mock-editor-textarea")).toHaveValue(
      "SELECT * FROM sales ORDER BY revenue DESC",
    );
  });

  it("deletes saved query when delete button is clicked", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><SqlEditorPage /></MemoryRouter>);

    await user.click(screen.getByTestId("toggle-saved"));
    await user.click(screen.getByTestId("delete-saved-sq-1"));

    expect(mockDeleteSavedMutate).toHaveBeenCalledWith(
      "sq-1",
      expect.any(Object),
    );
  });

  it("calls save API via Cmd+S (mock save button)", async () => {
    const user = userEvent.setup();
    useSqlEditorStore.setState({
      tabs: [
        {
          id: "tab-1",
          title: "Query 1",
          content: "SELECT * FROM test",
          cursorPosition: { line: 1, col: 1 },
          isExecuting: false,
          error: null,
          results: [],
          executionTimeMs: null,
        },
      ],
      activeTabId: "tab-1",
      selectedSource: { id: "ds-1", name: "Sales Data", type: "dataset" },
      abortControllers: new Map(),
    });

    render(<MemoryRouter><SqlEditorPage /></MemoryRouter>);

    // Click the mock save button (simulating Cmd+S in the editor)
    await user.click(screen.getByTestId("mock-save-button"));

    expect(mockSaveMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "Query 1",
        sql_content: "SELECT * FROM test",
        source_id: "ds-1",
        source_type: "dataset",
      }),
      expect.any(Object),
    );
  });

  it("calls explain API when explain button is clicked", async () => {
    const user = userEvent.setup();
    useSqlEditorStore.setState({
      tabs: [
        {
          id: "tab-1",
          title: "Query 1",
          content: "SELECT * FROM test",
          cursorPosition: { line: 1, col: 1 },
          isExecuting: false,
          error: null,
          results: [],
          executionTimeMs: null,
        },
      ],
      activeTabId: "tab-1",
      selectedSource: { id: "ds-1", name: "Sales Data", type: "dataset" },
      abortControllers: new Map(),
    });

    render(<MemoryRouter><SqlEditorPage /></MemoryRouter>);

    await user.click(screen.getByTestId("explain-button"));

    expect(mockExplainMutate).toHaveBeenCalledWith(
      {
        sql: "SELECT * FROM test",
        source_id: "ds-1",
        source_type: "dataset",
      },
      expect.any(Object),
    );

    // Explain panel should be visible
    expect(screen.getByTestId("explain-panel")).toBeInTheDocument();
  });

  it("closes side panel when toggle is clicked again", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><SqlEditorPage /></MemoryRouter>);

    // Open history
    await user.click(screen.getByTestId("toggle-history"));
    expect(screen.getByTestId("history-panel")).toBeInTheDocument();

    // Close history
    await user.click(screen.getByTestId("toggle-history"));
    expect(screen.queryByTestId("history-panel")).not.toBeInTheDocument();
  });

  it("switches between side panels", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><SqlEditorPage /></MemoryRouter>);

    // Open history
    await user.click(screen.getByTestId("toggle-history"));
    expect(screen.getByTestId("history-panel")).toBeInTheDocument();

    // Switch to saved queries
    await user.click(screen.getByTestId("toggle-saved"));
    expect(screen.queryByTestId("history-panel")).not.toBeInTheDocument();
    expect(screen.getByTestId("saved-queries-panel")).toBeInTheDocument();
  });

  it("selects a data source from the selector", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><SqlEditorPage /></MemoryRouter>);

    const select = screen.getByTestId("source-select");
    await user.selectOptions(select, "dataset:ds-1");

    // Verify the source was selected
    const store = useSqlEditorStore.getState();
    expect(store.selectedSource).toEqual({
      id: "ds-1",
      name: "Sales Data",
      type: "dataset",
    });
  });

  it("clears results when switching data source", async () => {
    const user = userEvent.setup();

    useSqlEditorStore.setState({
      tabs: [
        {
          id: "tab-1",
          title: "Query 1",
          content: "SELECT 1",
          cursorPosition: { line: 1, col: 1 },
          isExecuting: false,
          error: "old error",
          results: [
            {
              id: "r1",
              title: "Old",
              sql: "SELECT 1",
              data: [],
              columns: [],
              rowCount: 0,
              explanation: null,
              chartConfig: null,
              error: null,
              source: "sql-editor",
              createdAt: Date.now(),
              isExpanded: true,
            },
          ],
          executionTimeMs: 100,
        },
      ],
      activeTabId: "tab-1",
      selectedSource: { id: "ds-1", name: "Sales Data", type: "dataset" },
      abortControllers: new Map(),
    });

    render(<MemoryRouter><SqlEditorPage /></MemoryRouter>);

    // Switch to a different source
    const select = screen.getByTestId("source-select");
    await user.selectOptions(select, "connection:conn-1");

    // Results, error, and execution time should be cleared
    const store = useSqlEditorStore.getState();
    const tab = store.tabs.find((t) => t.id === "tab-1");
    expect(tab?.results).toEqual([]);
    expect(tab?.error).toBeNull();
    expect(tab?.executionTimeMs).toBeNull();
  });
});
