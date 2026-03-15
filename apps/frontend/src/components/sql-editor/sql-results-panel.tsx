import { useState, useCallback } from "react";
import { AlertCircle, Loader2, BarChart3, Pin, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
} from "@/components/ui/card";
import type { QueryResult } from "@/stores/results-store";

interface SqlResultsPanelProps {
  results: QueryResult[];
  isExecuting: boolean;
  error: string | null;
  onBookmark?: (result: QueryResult) => void;
}

export function SqlResultsPanel({
  results,
  isExecuting,
  error,
  onBookmark,
}: SqlResultsPanelProps) {
  if (isExecuting) {
    return (
      <div
        data-testid="sql-results-loading"
        className="flex flex-1 items-center justify-center gap-2 p-6"
      >
        <Loader2 className="size-4 animate-spin text-muted-foreground" />
        <span className="text-sm text-muted-foreground">
          Executing query...
        </span>
      </div>
    );
  }

  if (error) {
    return (
      <div data-testid="sql-results-error" className="flex flex-1 flex-col p-4">
        <Card className="border-destructive/50 bg-destructive/5">
          <CardHeader className="flex-row items-center gap-2 py-3">
            <AlertCircle className="size-4 text-destructive" />
            <CardTitle className="text-sm text-destructive">
              Query Error
            </CardTitle>
          </CardHeader>
          <CardContent className="border-t border-destructive/20 py-3">
            <pre className="overflow-x-auto whitespace-pre-wrap text-xs text-destructive">
              {error}
            </pre>
            {error.toLowerCase().includes("timeout") && (
              <p className="mt-2 text-xs text-muted-foreground">
                Try simplifying your query or adding LIMIT to reduce the result
                set.
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    );
  }

  if (results.length === 0) {
    return (
      <div
        data-testid="sql-results-empty"
        className="flex flex-1 flex-col items-center justify-center gap-3 p-6"
      >
        <div className="rounded-full bg-muted p-3">
          <BarChart3 className="size-6 text-muted-foreground" />
        </div>
        <div className="text-center">
          <p className="text-sm font-medium text-foreground">No results</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Write a query above and press Cmd/Ctrl+Enter to execute.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div data-testid="sql-results-panel" className="flex flex-1 flex-col overflow-hidden">
      <div
        data-testid="sql-results-scroll"
        className="flex-1 overflow-y-auto p-4"
      >
        <div className="flex flex-col gap-3">
          {results.map((result) => (
            <ResultCard
              key={result.id}
              result={result}
              onBookmark={onBookmark}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function ResultCard({
  result,
  onBookmark,
}: {
  result: QueryResult;
  onBookmark?: (result: QueryResult) => void;
}) {
  const [pinned, setPinned] = useState(false);

  const handlePin = useCallback(() => {
    onBookmark?.(result);
    setPinned(true);
    setTimeout(() => setPinned(false), 2000);
  }, [result, onBookmark]);

  return (
    <Card data-testid={`sql-result-card-${result.id}`}>
      <CardHeader className="flex-row items-center gap-2 py-3">
        <CardTitle className="flex-1 truncate text-sm">
          {result.title}
        </CardTitle>
        {onBookmark && (
          <Button
            variant="ghost"
            size="icon-xs"
            onClick={handlePin}
            aria-label="Pin result"
            data-testid={`pin-result-${result.id}`}
          >
            {pinned ? (
              <Check className="size-3 text-green-500" />
            ) : (
              <Pin className="size-3" />
            )}
          </Button>
        )}
        <span className="text-xs text-muted-foreground">
          {result.rowCount} row{result.rowCount !== 1 ? "s" : ""}
        </span>
      </CardHeader>
      <CardContent className="border-t border-border py-3">
        {result.sql && (
          <div className="mb-3">
            <p className="mb-1 text-xs font-medium text-muted-foreground">
              SQL
            </p>
            <pre className="overflow-x-auto rounded-md bg-muted p-2 text-xs">
              <code>{result.sql}</code>
            </pre>
          </div>
        )}

        {result.data && result.data.length > 0 && (
          <div>
            <div className="overflow-x-auto rounded-md border">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b bg-muted/50">
                    {result.columns.map((col) => (
                      <th
                        key={col}
                        className="px-3 py-1.5 text-left font-medium text-muted-foreground"
                      >
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.data.slice(0, 50).map((row, rowIdx) => (
                    <tr
                      key={rowIdx}
                      className={cn(
                        "border-b last:border-b-0",
                        rowIdx % 2 === 1 && "bg-muted/25",
                      )}
                    >
                      {result.columns.map((col) => (
                        <td key={col} className="px-3 py-1.5">
                          {String(row[col] ?? "")}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              {result.data.length > 50 && (
                <p className="px-3 py-1.5 text-xs text-muted-foreground">
                  Showing 50 of {result.rowCount} rows
                </p>
              )}
            </div>
          </div>
        )}

        {(!result.data || result.data.length === 0) && (
          <p className="text-sm text-muted-foreground">
            Query executed successfully. No data returned.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
