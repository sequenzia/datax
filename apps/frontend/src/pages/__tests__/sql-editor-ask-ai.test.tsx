import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { SqlEditorPage } from "../sql-editor";
import { useSqlEditorStore } from "@/stores/sql-editor-store";
import { useChatStore } from "@/stores/chat-store";
import { useResultsStore } from "@/stores/results-store";

// Mock useNavigate
const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

// Mock schema completions hook (uses useQuery)
vi.mock("@/hooks/use-schema-completions", () => ({
  useSchemaCompletions: () => ({
    tables: [],
    isLoading: false,
    error: null,
  }),
}));

// Mock sql-completions
vi.mock("@/lib/sql-completions", () => ({
  createSchemaCompletionSource: () => () => null,
  createKeywordsOnlyCompletionSource: () => () => null,
}));

// Mock useTheme
vi.mock("@/hooks/use-theme", () => ({
  useTheme: () => ({
    theme: "light",
    resolvedTheme: "light",
    setTheme: vi.fn(),
  }),
}));

// Mock CodeEditor
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

// Mock TanStack Query hooks for datasets and connections
vi.mock("@/hooks/use-datasets", () => ({
  useDatasetList: () => ({ data: [], isLoading: false }),
}));

vi.mock("@/hooks/use-connections", () => ({
  useConnectionList: () => ({ data: [], isLoading: false }),
}));

vi.mock("@/hooks/use-queries", () => ({
  useExecuteQuery: () => ({ mutate: vi.fn(), isPending: false }),
  useExplainQuery: () => ({ mutate: vi.fn(), isPending: false }),
  useSavedQueries: () => ({ data: [], isLoading: false }),
  useSaveQuery: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateSavedQuery: () => ({ mutate: vi.fn(), isPending: false }),
  useDeleteSavedQuery: () => ({ mutate: vi.fn(), isPending: false }),
  useQueryHistory: () => ({
    data: { history: [], total: 0, offset: 0, limit: 100 },
    isLoading: false,
  }),
}));

describe("SqlEditorPage - Ask AI button", () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
    useChatStore.setState({
      conversationId: null,
      messages: [],
      status: "idle",
      error: null,
      _restored: false,
      pendingMessage: null,
    });
    useResultsStore.setState({ results: [], sortNewestFirst: true });
  });

  it("renders 'Ask AI' button in the toolbar", () => {
    render(
      <MemoryRouter>
        <SqlEditorPage />
      </MemoryRouter>,
    );

    expect(screen.getByTestId("ask-ai-button")).toBeInTheDocument();
  });

  it("disables 'Ask AI' button when SQL editor is empty", () => {
    render(
      <MemoryRouter>
        <SqlEditorPage />
      </MemoryRouter>,
    );

    expect(screen.getByTestId("ask-ai-button")).toBeDisabled();
  });

  it("enables 'Ask AI' button when SQL editor has content", () => {
    useSqlEditorStore.setState({
      tabs: [
        {
          id: "tab-1",
          title: "Query 1",
          content: "SELECT * FROM users",
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

    render(
      <MemoryRouter>
        <SqlEditorPage />
      </MemoryRouter>,
    );

    expect(screen.getByTestId("ask-ai-button")).not.toBeDisabled();
  });

  it("clicking 'Ask AI' sets pending message and navigates to /chat", async () => {
    const user = userEvent.setup();
    const testSql = "SELECT * FROM orders JOIN users ON orders.user_id = users.id";

    useSqlEditorStore.setState({
      tabs: [
        {
          id: "tab-1",
          title: "Query 1",
          content: testSql,
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

    render(
      <MemoryRouter>
        <SqlEditorPage />
      </MemoryRouter>,
    );

    await user.click(screen.getByTestId("ask-ai-button"));

    // Should set pending message with SQL content
    const chatStore = useChatStore.getState();
    expect(chatStore.pendingMessage).toContain(testSql);
    expect(chatStore.pendingMessage).toContain("Explain this query");

    // Should navigate to chat
    expect(mockNavigate).toHaveBeenCalledWith("/chat");
  });
});
