import { useState, useCallback } from "react";
import { Bookmark, Play, AlertCircle, Loader2, Code2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { executeQuery } from "@/lib/api";
import type { ExecuteQueryResponse } from "@/types/api";

export interface BookmarkCardProps {
  bookmarkId: string;
  title: string;
  sql?: string;
  sourceId?: string;
  sourceType?: string;
  className?: string;
}

/**
 * Displays a saved bookmark with its SQL and provides a re-execute action.
 * When re-execution fails (e.g., table deleted), shows an error with the
 * original bookmark info as fallback.
 */
export function BookmarkCard({
  title,
  sql,
  sourceId,
  sourceType,
  className,
}: BookmarkCardProps) {
  const [executing, setExecuting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ExecuteQueryResponse | null>(null);
  const [showSql, setShowSql] = useState(false);

  const handleExecute = useCallback(async () => {
    if (!sql || !sourceId || !sourceType) {
      setError("Missing SQL or source information to re-execute.");
      return;
    }

    setExecuting(true);
    setError(null);
    setResult(null);

    try {
      const response = await executeQuery({
        sql,
        source_id: sourceId,
        source_type: sourceType as "dataset" | "connection",
      });
      setResult(response);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to re-execute bookmark query.",
      );
    } finally {
      setExecuting(false);
    }
  }, [sql, sourceId, sourceType]);

  // Truncate SQL for display
  const truncatedSql =
    sql && sql.length > 120 ? sql.slice(0, 120) + "..." : sql;

  return (
    <div
      data-testid="bookmark-card"
      className={cn(
        "flex flex-col gap-2 rounded-lg border bg-card p-4 shadow-sm",
        className,
      )}
    >
      {/* Header */}
      <div className="flex items-center gap-2">
        <Bookmark className="size-4 shrink-0 text-primary" />
        <h3 className="text-sm font-semibold text-foreground">{title}</h3>
      </div>

      {/* SQL preview */}
      {sql && (
        <div className="flex flex-col gap-1">
          <button
            onClick={() => setShowSql((prev) => !prev)}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            data-testid="bookmark-toggle-sql"
          >
            <Code2 className="size-3" />
            {showSql ? "Hide SQL" : "Show SQL"}
          </button>
          {showSql ? (
            <pre
              data-testid="bookmark-sql-full"
              className="max-h-48 overflow-auto rounded-md bg-muted p-2 text-xs text-foreground"
            >
              {sql}
            </pre>
          ) : (
            <p
              className="truncate text-xs text-muted-foreground"
              title={sql}
              data-testid="bookmark-sql-truncated"
            >
              {truncatedSql}
            </p>
          )}
        </div>
      )}

      {/* Source info */}
      {sourceType && (
        <p className="text-xs text-muted-foreground">
          Source: {sourceType}
          {sourceId ? ` (${sourceId.slice(0, 8)}...)` : ""}
        </p>
      )}

      {/* Re-execute button */}
      {sql && sourceId && (
        <Button
          variant="outline"
          size="sm"
          onClick={handleExecute}
          disabled={executing}
          data-testid="bookmark-execute"
          className="w-fit"
        >
          {executing ? (
            <Loader2 className="mr-1 size-3 animate-spin" />
          ) : (
            <Play className="mr-1 size-3" />
          )}
          Re-execute
        </Button>
      )}

      {/* Error */}
      {error && (
        <div
          data-testid="bookmark-error"
          className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-2"
        >
          <AlertCircle className="mt-0.5 size-3.5 shrink-0 text-destructive" />
          <p className="text-xs text-destructive">{error}</p>
        </div>
      )}

      {/* Result preview */}
      {result && (
        <div
          data-testid="bookmark-result"
          className="rounded-md border bg-muted/50 p-2"
        >
          <p className="text-xs font-medium text-foreground">
            {result.row_count} rows returned in {result.execution_time_ms}ms
          </p>
          {result.columns.length > 0 && (
            <p className="mt-1 truncate text-xs text-muted-foreground">
              Columns: {result.columns.join(", ")}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
