import { ArrowDownUp, Trash2, BarChart3 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useResultsStore } from "@/stores/results-store";
import { useTheme } from "@/hooks/use-theme";
import { ResultCard } from "./result-card";

export function ResultsPanel() {
  const {
    results,
    sortNewestFirst,
    toggleExpanded,
    removeResult,
    clearResults,
    toggleSortOrder,
  } = useResultsStore();
  const { resolvedTheme } = useTheme();

  if (results.length === 0) {
    return (
      <div
        data-testid="results-empty-state"
        className="flex flex-1 flex-col items-center justify-center gap-3 p-6"
      >
        <div className="rounded-full bg-muted p-3">
          <BarChart3 className="size-6 text-muted-foreground" />
        </div>
        <div className="text-center">
          <p className="text-sm font-medium text-foreground">No results yet</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Ask a question in the chat or run a query in the SQL editor to see
            results here.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div data-testid="results-panel" className="flex flex-1 flex-col overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center gap-2 border-b border-border px-4 py-2">
        <span className="text-xs text-muted-foreground">
          {results.length} result{results.length !== 1 ? "s" : ""}
        </span>
        <div className="flex-1" />
        <Button
          variant="ghost"
          size="xs"
          onClick={toggleSortOrder}
          aria-label={
            sortNewestFirst ? "Sort oldest first" : "Sort newest first"
          }
          data-testid="toggle-sort-order"
        >
          <ArrowDownUp className="size-3" />
          <span>{sortNewestFirst ? "Newest" : "Oldest"}</span>
        </Button>
        <Button
          variant="ghost"
          size="xs"
          onClick={clearResults}
          aria-label="Clear all results"
          data-testid="clear-results"
        >
          <Trash2 className="size-3" />
          <span>Clear</span>
        </Button>
      </div>

      {/* Scrollable card list */}
      <div
        data-testid="results-scroll-container"
        className="flex-1 overflow-y-auto p-4"
      >
        <div className="flex flex-col gap-3">
          {results.map((result, index) => (
            <ResultCard
              key={result.id}
              result={result}
              onToggleExpanded={toggleExpanded}
              onRemove={removeResult}
              animationDelay={index * 50}
              resolvedTheme={resolvedTheme}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
