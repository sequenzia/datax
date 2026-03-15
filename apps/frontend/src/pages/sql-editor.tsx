import { useCallback, useMemo, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import {
  Play,
  Save,
  Clock,
  History,
  Bookmark,
  FileText,
  Search,
  Trash2,
  X,
  AlertCircle,
  CheckCircle,
  Database,
  Loader2,
  Bot,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { CodeEditor, TabBar, SqlResultsPanel } from "@/components/sql-editor";
import { useSqlEditorStore } from "@/stores/sql-editor-store";
import { useChatStore } from "@/stores/chat-store";
import { useResultsStore } from "@/stores/results-store";
import type { QueryResult } from "@/stores/results-store";
import { useTheme } from "@/hooks/use-theme";
import { useDatasetList } from "@/hooks/use-datasets";
import { useConnectionList } from "@/hooks/use-connections";
import {
  useExecuteQuery,
  useExplainQuery,
  useSavedQueries,
  useSaveQuery,
  useDeleteSavedQuery,
  useQueryHistory,
} from "@/hooks/use-queries";
import { useSchemaCompletions } from "@/hooks/use-schema-completions";
import {
  createSchemaCompletionSource,
  createKeywordsOnlyCompletionSource,
} from "@/lib/sql-completions";
import type { DataSource } from "@/stores/sql-editor-store";
import type { HistoryEntry, SavedQuery } from "@/types/api";

type SidePanel = "history" | "saved" | "explain" | null;

function Toast({
  message,
  type,
  onClose,
}: {
  message: string;
  type: "success" | "error";
  onClose: () => void;
}) {
  return (
    <div
      data-testid="toast"
      className={`fixed right-4 top-4 z-50 flex items-center gap-2 rounded-lg border px-4 py-3 shadow-lg ${
        type === "error"
          ? "border-destructive/50 bg-destructive/10 text-destructive"
          : "border-green-500/50 bg-green-50 text-green-800 dark:bg-green-950 dark:text-green-200"
      }`}
    >
      {type === "error" ? (
        <AlertCircle className="size-4" />
      ) : (
        <CheckCircle className="size-4" />
      )}
      <p className="text-sm">{message}</p>
      <button
        onClick={onClose}
        className="ml-2 text-xs opacity-60 hover:opacity-100"
        aria-label="Dismiss"
      >
        <X className="size-3" />
      </button>
    </div>
  );
}

function useToast() {
  const [toast, setToast] = useState<{
    message: string;
    type: "success" | "error";
  } | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const showToast = useCallback(
    (message: string, type: "success" | "error") => {
      if (timerRef.current) clearTimeout(timerRef.current);
      setToast({ message, type });
      timerRef.current = setTimeout(() => setToast(null), 5000);
    },
    [],
  );

  const dismissToast = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setToast(null);
  }, []);

  return { toast, showToast, dismissToast };
}

function DataSourceSelector({
  sources,
  selectedSource,
  onSelect,
}: {
  sources: DataSource[];
  selectedSource: DataSource | null;
  onSelect: (source: DataSource | null) => void;
}) {
  return (
    <div className="flex items-center gap-1.5" data-testid="data-source-selector">
      <Database className="size-3 text-muted-foreground" />
      <select
        data-testid="source-select"
        value={selectedSource ? `${selectedSource.type}:${selectedSource.id}` : ""}
        onChange={(e) => {
          if (!e.target.value) {
            onSelect(null);
            return;
          }
          const source = sources.find(
            (s) => `${s.type}:${s.id}` === e.target.value,
          );
          onSelect(source ?? null);
        }}
        className="h-6 rounded border bg-background px-2 text-xs"
      >
        <option value="">Select source...</option>
        {sources.map((s) => (
          <option key={`${s.type}:${s.id}`} value={`${s.type}:${s.id}`}>
            {s.name} ({s.type})
          </option>
        ))}
      </select>
    </div>
  );
}

function HistoryPanel({
  onLoadQuery,
}: {
  onLoadQuery: (sql: string) => void;
}) {
  const { data, isLoading } = useQueryHistory({ limit: 100 });
  const [searchTerm, setSearchTerm] = useState("");

  const filtered = useMemo(() => {
    if (!data?.history) return [];
    if (!searchTerm.trim()) return data.history;
    const term = searchTerm.toLowerCase();
    return data.history.filter((e: HistoryEntry) =>
      e.sql.toLowerCase().includes(term),
    );
  }, [data, searchTerm]);

  return (
    <div
      data-testid="history-panel"
      className="flex h-full flex-col overflow-hidden"
    >
      <div className="flex items-center gap-2 border-b border-border px-3 py-2">
        <History className="size-3.5 text-muted-foreground" />
        <span className="text-xs font-medium">Query History</span>
      </div>
      <div className="px-3 py-2">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 size-3 -translate-y-1/2 text-muted-foreground" />
          <input
            data-testid="history-search"
            type="text"
            placeholder="Search history..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full rounded border bg-background py-1 pl-7 pr-2 text-xs"
          />
        </div>
      </div>
      <div className="flex-1 overflow-y-auto px-3 pb-3">
        {isLoading && (
          <div className="flex items-center justify-center py-4">
            <Loader2 className="size-4 animate-spin text-muted-foreground" />
          </div>
        )}
        {!isLoading && filtered.length === 0 && (
          <p className="py-4 text-center text-xs text-muted-foreground">
            No history entries found.
          </p>
        )}
        {filtered.map((entry: HistoryEntry, idx: number) => (
          <button
            key={idx}
            data-testid={`history-entry-${idx}`}
            className="mb-1 w-full rounded border bg-background p-2 text-left text-xs transition-colors hover:bg-accent"
            onClick={() => onLoadQuery(entry.sql)}
          >
            <pre className="max-h-12 overflow-hidden whitespace-pre-wrap break-words text-[10px]">
              {entry.sql}
            </pre>
            <div className="mt-1 flex items-center gap-2 text-[10px] text-muted-foreground">
              <span
                className={
                  entry.status === "success"
                    ? "text-green-600 dark:text-green-400"
                    : "text-destructive"
                }
              >
                {entry.status}
              </span>
              <span>{entry.row_count} rows</span>
              <span>{entry.execution_time_ms}ms</span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

function SavedQueriesPanel({
  onLoadQuery,
  onDelete,
}: {
  onLoadQuery: (sql: string) => void;
  onDelete: (id: string) => void;
}) {
  const { data: queries, isLoading } = useSavedQueries();

  return (
    <div
      data-testid="saved-queries-panel"
      className="flex h-full flex-col overflow-hidden"
    >
      <div className="flex items-center gap-2 border-b border-border px-3 py-2">
        <Bookmark className="size-3.5 text-muted-foreground" />
        <span className="text-xs font-medium">Saved Queries</span>
      </div>
      <div className="flex-1 overflow-y-auto px-3 py-2">
        {isLoading && (
          <div className="flex items-center justify-center py-4">
            <Loader2 className="size-4 animate-spin text-muted-foreground" />
          </div>
        )}
        {!isLoading && (!queries || queries.length === 0) && (
          <p className="py-4 text-center text-xs text-muted-foreground">
            No saved queries yet.
          </p>
        )}
        {queries?.map((sq: SavedQuery) => (
          <div
            key={sq.id}
            data-testid={`saved-query-${sq.id}`}
            className="mb-1 rounded border bg-background p-2 text-xs"
          >
            <div className="mb-1 flex items-center justify-between">
              <span className="font-medium">{sq.name}</span>
              <button
                data-testid={`delete-saved-${sq.id}`}
                onClick={() => onDelete(sq.id)}
                className="rounded p-0.5 text-muted-foreground hover:text-destructive"
                aria-label={`Delete ${sq.name}`}
              >
                <Trash2 className="size-3" />
              </button>
            </div>
            <button
              className="w-full text-left"
              onClick={() => onLoadQuery(sq.sql_content)}
            >
              <pre className="max-h-10 overflow-hidden whitespace-pre-wrap break-words text-[10px] text-muted-foreground">
                {sq.sql_content}
              </pre>
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

function ExplainPanel({ plan }: { plan: string | null }) {
  return (
    <div
      data-testid="explain-panel"
      className="flex h-full flex-col overflow-hidden"
    >
      <div className="flex items-center gap-2 border-b border-border px-3 py-2">
        <FileText className="size-3.5 text-muted-foreground" />
        <span className="text-xs font-medium">EXPLAIN Plan</span>
      </div>
      <div className="flex-1 overflow-y-auto p-3">
        {plan ? (
          <pre
            data-testid="explain-output"
            className="whitespace-pre-wrap break-words text-xs"
          >
            {plan}
          </pre>
        ) : (
          <p className="py-4 text-center text-xs text-muted-foreground">
            Run EXPLAIN to see the query plan.
          </p>
        )}
      </div>
    </div>
  );
}

export function SqlEditorPage() {
  const {
    tabs,
    activeTabId,
    selectedSource,
    addTab,
    closeTab,
    renameTab,
    setActiveTab,
    updateTabContent,
    updateCursorPosition,
    setTabExecuting,
    setTabError,
    addTabResult,
    setTabExecutionTime,
    setSelectedSource,
    setAbortController,
    cancelExecution,
    clearTabResults,
  } = useSqlEditorStore();

  const navigate = useNavigate();
  const { addResult } = useResultsStore();
  const { resolvedTheme } = useTheme();
  const { toast, showToast, dismissToast } = useToast();
  const [sidePanel, setSidePanel] = useState<SidePanel>(null);
  const [explainPlan, setExplainPlan] = useState<string | null>(null);

  const executeMutation = useExecuteQuery();
  const explainMutation = useExplainQuery();
  const saveMutation = useSaveQuery();
  const deleteSavedMutation = useDeleteSavedQuery();

  const { data: datasets } = useDatasetList();
  const { data: connections } = useConnectionList();

  // Schema-aware autocomplete
  const { tables: schemaTables } = useSchemaCompletions(selectedSource);
  const completionSource = useMemo(() => {
    if (schemaTables.length > 0) {
      return createSchemaCompletionSource(schemaTables);
    }
    return createKeywordsOnlyCompletionSource();
  }, [schemaTables]);

  const dataSources: DataSource[] = useMemo(() => {
    const sources: DataSource[] = [];
    if (datasets) {
      for (const d of datasets) {
        if (d.status === "ready") {
          sources.push({ id: d.id, name: d.name, type: "dataset" });
        }
      }
    }
    if (connections) {
      for (const c of connections) {
        if (c.status === "connected") {
          sources.push({ id: c.id, name: c.name, type: "connection" });
        }
      }
    }
    return sources;
  }, [datasets, connections]);

  const activeTab = useMemo(
    () => tabs.find((t) => t.id === activeTabId),
    [tabs, activeTabId],
  );

  const handleExecute = useCallback(() => {
    if (!activeTab) return;

    const query = activeTab.content.trim();
    if (!query) {
      setTabError(activeTab.id, "Cannot execute an empty query.");
      return;
    }

    if (!selectedSource) {
      setTabError(activeTab.id, "Please select a data source before executing.");
      return;
    }

    // Cancel any previous execution on this tab
    cancelExecution(activeTab.id);

    const abortController = new AbortController();
    setAbortController(activeTab.id, abortController);

    setTabExecuting(activeTab.id, true);
    setTabError(activeTab.id, null);
    setTabExecutionTime(activeTab.id, null);

    const tabId = activeTab.id;
    const tabTitle = activeTab.title;

    executeMutation.mutate(
      {
        body: {
          sql: query,
          source_id: selectedSource.id,
          source_type: selectedSource.type,
        },
        signal: abortController.signal,
      },
      {
        onSuccess: (response) => {
          setTabExecutionTime(tabId, response.execution_time_ms);

          // Transform rows from array-of-arrays to array-of-objects
          const dataRows = response.rows.map((row) => {
            const obj: Record<string, unknown> = {};
            response.columns.forEach((col, i) => {
              obj[col] = row[i];
            });
            return obj;
          });

          const resultPayload: Omit<
            QueryResult,
            "id" | "createdAt" | "isExpanded"
          > = {
            title: tabTitle,
            sql: query,
            data: dataRows,
            columns: response.columns,
            rowCount: response.row_count,
            explanation: null,
            chartConfig: null,
            error: null,
            source: "sql-editor",
          };

          addResult(resultPayload);

          const tabResult: QueryResult = {
            ...resultPayload,
            id: `result-tab-${Date.now()}`,
            createdAt: Date.now(),
            isExpanded: true,
          };
          addTabResult(tabId, tabResult);

          setTabExecuting(tabId, false);
        },
        onError: (error) => {
          if (error instanceof Error && error.name === "AbortError") {
            setTabExecuting(tabId, false);
            return;
          }

          let errorMessage = "Query execution failed.";
          if (error instanceof Error) {
            try {
              const parsed = JSON.parse(error.message) as {
                error?: { message?: string };
              };
              errorMessage = parsed?.error?.message ?? error.message;
            } catch {
              errorMessage = error.message;
            }
          }

          setTabError(tabId, errorMessage);
          setTabExecuting(tabId, false);
        },
      },
    );
  }, [
    activeTab,
    selectedSource,
    cancelExecution,
    setAbortController,
    setTabExecuting,
    setTabError,
    setTabExecutionTime,
    executeMutation,
    addResult,
    addTabResult,
  ]);

  const handleExplain = useCallback(() => {
    if (!activeTab) return;

    const query = activeTab.content.trim();
    if (!query) return;

    if (!selectedSource) {
      showToast("Please select a data source first.", "error");
      return;
    }

    setSidePanel("explain");
    setExplainPlan(null);

    explainMutation.mutate(
      {
        sql: query,
        source_id: selectedSource.id,
        source_type: selectedSource.type,
      },
      {
        onSuccess: (response) => {
          setExplainPlan(response.plan);
        },
        onError: (error) => {
          const msg =
            error instanceof Error ? error.message : "EXPLAIN failed.";
          setExplainPlan(`Error: ${msg}`);
        },
      },
    );
  }, [activeTab, selectedSource, explainMutation, showToast]);

  const handleSave = useCallback(() => {
    if (!activeTab) return;

    const query = activeTab.content.trim();
    if (!query) {
      showToast("Cannot save an empty query.", "error");
      return;
    }

    saveMutation.mutate(
      {
        name: activeTab.title,
        sql_content: query,
        source_id: selectedSource?.id ?? null,
        source_type: selectedSource?.type ?? null,
      },
      {
        onSuccess: () => {
          showToast("Query saved successfully.", "success");
        },
        onError: (error) => {
          const msg =
            error instanceof Error ? error.message : "Failed to save query.";
          showToast(msg, "error");
        },
      },
    );
  }, [activeTab, selectedSource, saveMutation, showToast]);

  const handleDeleteSaved = useCallback(
    (id: string) => {
      deleteSavedMutation.mutate(id, {
        onSuccess: () => {
          showToast("Saved query deleted.", "success");
        },
        onError: (error) => {
          const msg =
            error instanceof Error ? error.message : "Failed to delete query.";
          showToast(msg, "error");
        },
      });
    },
    [deleteSavedMutation, showToast],
  );

  const handleLoadQuery = useCallback(
    (sql: string) => {
      if (activeTab) {
        updateTabContent(activeTab.id, sql);
      }
    },
    [activeTab, updateTabContent],
  );

  const handleAskAi = useCallback(() => {
    if (!activeTab) return;
    const query = activeTab.content.trim();
    if (!query) return;

    useChatStore.getState().setPendingMessage(`Explain this query:\n\`\`\`sql\n${query}\n\`\`\``);
    navigate("/chat");
  }, [activeTab, navigate]);

  const handleBookmarkResult = useCallback(
    (result: QueryResult) => {
      if (!result.sql) return;
      saveMutation.mutate(
        {
          name: result.title || "Pinned Query",
          sql_content: result.sql,
          source_id: selectedSource?.id ?? null,
          source_type: selectedSource?.type ?? null,
        },
        {
          onSuccess: () => {
            showToast("Result pinned as saved query.", "success");
          },
          onError: (error) => {
            const msg =
              error instanceof Error ? error.message : "Failed to pin result.";
            showToast(msg, "error");
          },
        },
      );
    },
    [selectedSource, saveMutation, showToast],
  );

  const handleSourceChange = useCallback(
    (source: DataSource | null) => {
      setSelectedSource(source);
      // Clear cached results when switching source
      if (activeTab) {
        clearTabResults(activeTab.id);
      }
    },
    [activeTab, setSelectedSource, clearTabResults],
  );

  const handleContentChange = useCallback(
    (content: string) => {
      if (activeTab) {
        updateTabContent(activeTab.id, content);
      }
    },
    [activeTab, updateTabContent],
  );

  const handleCursorChange = useCallback(
    (position: { line: number; col: number }) => {
      if (activeTab) {
        updateCursorPosition(activeTab.id, position);
      }
    },
    [activeTab, updateCursorPosition],
  );

  const togglePanel = useCallback(
    (panel: SidePanel) => {
      setSidePanel((prev) => (prev === panel ? null : panel));
    },
    [],
  );

  if (!activeTab) return null;

  return (
    <div
      data-testid="sql-editor-page"
      className="flex h-full flex-col overflow-hidden"
    >
      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
          onClose={dismissToast}
        />
      )}

      {/* Tab bar */}
      <TabBar
        tabs={tabs}
        activeTabId={activeTabId}
        onSelectTab={setActiveTab}
        onAddTab={addTab}
        onCloseTab={closeTab}
        onRenameTab={renameTab}
      />

      {/* Toolbar */}
      <div
        data-testid="sql-toolbar"
        className="flex items-center gap-2 border-b border-border px-3 py-1.5"
      >
        <Button
          variant="default"
          size="xs"
          onClick={handleExecute}
          disabled={activeTab.isExecuting}
          data-testid="run-query-button"
        >
          <Play className="size-3" />
          <span>Run</span>
        </Button>
        <Button
          variant="ghost"
          size="xs"
          onClick={handleSave}
          data-testid="save-query-button"
        >
          <Save className="size-3" />
          <span>Save</span>
        </Button>
        <Button
          variant="ghost"
          size="xs"
          onClick={handleExplain}
          data-testid="explain-button"
        >
          <FileText className="size-3" />
          <span>Explain</span>
        </Button>
        <Button
          variant="ghost"
          size="xs"
          onClick={handleAskAi}
          disabled={!activeTab.content.trim()}
          data-testid="ask-ai-button"
        >
          <Bot className="size-3" />
          <span>Ask AI</span>
        </Button>

        <div className="mx-1 h-4 w-px bg-border" />

        <DataSourceSelector
          sources={dataSources}
          selectedSource={selectedSource}
          onSelect={handleSourceChange}
        />

        <div className="flex-1" />

        <Button
          variant="ghost"
          size="icon-xs"
          onClick={() => togglePanel("history")}
          data-testid="toggle-history"
          aria-label="Toggle history"
          className={sidePanel === "history" ? "bg-accent" : ""}
        >
          <History className="size-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="icon-xs"
          onClick={() => togglePanel("saved")}
          data-testid="toggle-saved"
          aria-label="Toggle saved queries"
          className={sidePanel === "saved" ? "bg-accent" : ""}
        >
          <Bookmark className="size-3.5" />
        </Button>

        <div className="mx-1 h-4 w-px bg-border" />

        {activeTab.executionTimeMs !== null && (
          <span
            data-testid="execution-time"
            className="flex items-center gap-1 text-xs text-muted-foreground"
          >
            <Clock className="size-3" />
            {activeTab.executionTimeMs}ms
          </span>
        )}

        <span
          data-testid="cursor-position"
          className="text-xs text-muted-foreground"
        >
          Ln {activeTab.cursorPosition.line}, Col{" "}
          {activeTab.cursorPosition.col}
        </span>
      </div>

      {/* Editor and results split with optional side panel */}
      <div className="flex flex-1 overflow-hidden">
        {/* Main editor + results */}
        <div className="flex flex-1 flex-col overflow-hidden">
          {/* Editor pane */}
          <div
            data-testid="editor-pane"
            className="flex min-h-[200px] flex-1 overflow-hidden border-b border-border"
          >
            <CodeEditor
              key={activeTabId}
              value={activeTab.content}
              onChange={handleContentChange}
              onCursorChange={handleCursorChange}
              onExecute={handleExecute}
              onSave={handleSave}
              darkMode={resolvedTheme === "dark"}
              completionSource={completionSource}
            />
          </div>

          {/* Results pane */}
          <div
            data-testid="results-pane"
            className="flex min-h-[150px] flex-1 overflow-hidden"
          >
            <SqlResultsPanel
              results={activeTab.results}
              isExecuting={activeTab.isExecuting}
              error={activeTab.error}
              onBookmark={handleBookmarkResult}
            />
          </div>
        </div>

        {/* Side panel */}
        {sidePanel && (
          <div
            data-testid="side-panel"
            className="w-72 shrink-0 border-l border-border bg-background"
          >
            {sidePanel === "history" && (
              <HistoryPanel onLoadQuery={handleLoadQuery} />
            )}
            {sidePanel === "saved" && (
              <SavedQueriesPanel
                onLoadQuery={handleLoadQuery}
                onDelete={handleDeleteSaved}
              />
            )}
            {sidePanel === "explain" && <ExplainPanel plan={explainPlan} />}
          </div>
        )}
      </div>
    </div>
  );
}
