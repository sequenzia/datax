import { useState, useMemo, useCallback } from "react";
import {
  ChevronDown,
  ChevronUp,
  Code2,
  MessageSquare,
  X,
  Download,
  ArrowUp,
  ArrowDown,
  AlertCircle,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  CardAction,
} from "@/components/ui/card";
import { ChartRenderer } from "@/components/charts";
import type { ChartConfig } from "@/components/charts";
import type { QueryResult } from "@/stores/results-store";

interface ResultCardProps {
  result: QueryResult;
  onToggleExpanded: (id: string) => void;
  onRemove: (id: string) => void;
  animationDelay?: number;
  resolvedTheme?: "light" | "dark";
}

type SortDirection = "asc" | "desc" | null;

interface SortState {
  column: string | null;
  direction: SortDirection;
}

const PAGE_SIZE = 100;
const MAX_CELL_LENGTH = 100;

const SQL_KEYWORDS = new Set([
  "SELECT", "FROM", "WHERE", "AND", "OR", "NOT", "IN", "IS", "NULL",
  "JOIN", "LEFT", "RIGHT", "INNER", "OUTER", "FULL", "CROSS", "ON",
  "GROUP", "BY", "ORDER", "ASC", "DESC", "LIMIT", "OFFSET", "HAVING",
  "INSERT", "INTO", "VALUES", "UPDATE", "SET", "DELETE", "CREATE",
  "TABLE", "ALTER", "DROP", "INDEX", "VIEW", "AS", "DISTINCT",
  "COUNT", "SUM", "AVG", "MIN", "MAX", "CASE", "WHEN", "THEN",
  "ELSE", "END", "BETWEEN", "LIKE", "EXISTS", "UNION", "ALL",
  "WITH", "RECURSIVE", "OVER", "PARTITION", "WINDOW", "ROWS",
  "RANGE", "UNBOUNDED", "PRECEDING", "FOLLOWING", "CURRENT", "ROW",
  "CAST", "COALESCE", "NULLIF", "TRUE", "FALSE",
]);

function highlightSql(sql: string): Array<{ text: string; isKeyword: boolean }> {
  const tokens: Array<{ text: string; isKeyword: boolean }> = [];
  const regex = /(\b[A-Za-z_]+\b|[^A-Za-z_]+)/g;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(sql)) !== null) {
    const text = match[0];
    const isKeyword = SQL_KEYWORDS.has(text.toUpperCase());
    tokens.push({ text, isKeyword });
  }

  return tokens;
}

function formatTimestamp(timestamp: number): string {
  const date = new Date(timestamp);
  return date.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatCellValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "NULL";
  }
  return String(value);
}

function truncateValue(value: string, maxLength: number): { display: string; isTruncated: boolean } {
  if (value.length <= maxLength) {
    return { display: value, isTruncated: false };
  }
  return { display: value.slice(0, maxLength) + "...", isTruncated: true };
}

function sortData(
  data: Record<string, unknown>[],
  sortState: SortState,
): Record<string, unknown>[] {
  if (!sortState.column || !sortState.direction) {
    return data;
  }

  const { column, direction } = sortState;

  return [...data].sort((a, b) => {
    const aVal = a[column];
    const bVal = b[column];

    if (aVal === null || aVal === undefined) return direction === "asc" ? -1 : 1;
    if (bVal === null || bVal === undefined) return direction === "asc" ? 1 : -1;

    if (typeof aVal === "number" && typeof bVal === "number") {
      return direction === "asc" ? aVal - bVal : bVal - aVal;
    }

    const aStr = String(aVal);
    const bStr = String(bVal);
    const cmp = aStr.localeCompare(bStr);
    return direction === "asc" ? cmp : -cmp;
  });
}

function generateCsv(columns: string[], data: Record<string, unknown>[]): string {
  const escapeCsvField = (value: string): string => {
    if (value.includes(",") || value.includes('"') || value.includes("\n")) {
      return `"${value.replace(/"/g, '""')}"`;
    }
    return value;
  };

  const header = columns.map(escapeCsvField).join(",");
  const rows = data.map((row) =>
    columns.map((col) => escapeCsvField(formatCellValue(row[col]))).join(","),
  );

  return [header, ...rows].join("\n");
}

function downloadCsv(filename: string, csvContent: string): void {
  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export function ResultCard({
  result,
  onToggleExpanded,
  onRemove,
  animationDelay = 0,
  resolvedTheme = "light",
}: ResultCardProps) {
  const [sqlExpanded, setSqlExpanded] = useState(true);
  const [sortState, setSortState] = useState<SortState>({ column: null, direction: null });
  const [currentPage, setCurrentPage] = useState(0);

  const sortedData = useMemo(() => {
    if (!result.data) return [];
    return sortData(result.data, sortState);
  }, [result.data, sortState]);

  const totalPages = useMemo(() => {
    return Math.max(1, Math.ceil(sortedData.length / PAGE_SIZE));
  }, [sortedData.length]);

  const paginatedData = useMemo(() => {
    const start = currentPage * PAGE_SIZE;
    return sortedData.slice(start, start + PAGE_SIZE);
  }, [sortedData, currentPage]);

  const handleSort = useCallback((column: string) => {
    setSortState((prev) => {
      if (prev.column !== column) {
        return { column, direction: "asc" };
      }
      if (prev.direction === "asc") {
        return { column, direction: "desc" };
      }
      return { column: null, direction: null };
    });
    setCurrentPage(0);
  }, []);

  const handleExportCsv = useCallback(() => {
    if (!result.data || result.data.length === 0) return;
    const csv = generateCsv(result.columns, result.data);
    const filename = `${result.title.replace(/[^a-zA-Z0-9]/g, "_")}_${result.id}.csv`;
    downloadCsv(filename, csv);
  }, [result.data, result.columns, result.title, result.id]);

  const sourceIcon =
    result.source === "chat" ? (
      <MessageSquare className="size-3.5 text-muted-foreground" />
    ) : (
      <Code2 className="size-3.5 text-muted-foreground" />
    );

  const sourceLabel = result.source === "chat" ? "Chat" : "SQL Editor";

  // Error state card
  if (result.error) {
    return (
      <Card
        data-testid={`result-card-${result.id}`}
        className={cn("animate-result-card-enter gap-0 py-0 border-destructive/50")}
        style={{ animationDelay: `${animationDelay}ms` }}
      >
        <CardHeader className="flex-row items-center gap-2 py-3">
          <AlertCircle className="size-3.5 text-destructive" />
          <CardTitle className="flex-1 truncate text-sm text-destructive">
            {result.title}
          </CardTitle>
          <span className="text-xs text-muted-foreground">
            {formatTimestamp(result.createdAt)}
          </span>
          <CardAction className="flex flex-row gap-1">
            <Button
              variant="ghost"
              size="icon-xs"
              onClick={() => onRemove(result.id)}
              aria-label="Remove result"
              data-testid={`remove-result-${result.id}`}
            >
              <X className="size-3.5" />
            </Button>
          </CardAction>
        </CardHeader>
        <CardContent className="border-t border-destructive/20 py-3">
          <pre
            data-testid={`result-error-${result.id}`}
            className="overflow-x-auto whitespace-pre-wrap text-xs text-destructive"
          >
            {result.error}
          </pre>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card
      data-testid={`result-card-${result.id}`}
      className={cn("animate-result-card-enter gap-0 py-0")}
      style={{ animationDelay: `${animationDelay}ms` }}
    >
      {/* Header */}
      <CardHeader className="flex-row items-center gap-2 py-3">
        {sourceIcon}
        <CardTitle className="flex-1 truncate text-sm">
          {result.title}
        </CardTitle>
        <span
          data-testid={`result-source-${result.id}`}
          className="text-xs text-muted-foreground"
        >
          {sourceLabel}
        </span>
        <span className="text-xs text-muted-foreground">
          {formatTimestamp(result.createdAt)}
        </span>
        <CardAction className="flex flex-row gap-1">
          <Button
            variant="ghost"
            size="icon-xs"
            onClick={() => onToggleExpanded(result.id)}
            aria-label={result.isExpanded ? "Collapse result" : "Expand result"}
            data-testid={`toggle-expand-${result.id}`}
          >
            {result.isExpanded ? (
              <ChevronUp className="size-3.5" />
            ) : (
              <ChevronDown className="size-3.5" />
            )}
          </Button>
          <Button
            variant="ghost"
            size="icon-xs"
            onClick={() => onRemove(result.id)}
            aria-label="Remove result"
            data-testid={`remove-result-${result.id}`}
          >
            <X className="size-3.5" />
          </Button>
        </CardAction>
      </CardHeader>

      {result.isExpanded && (
        <CardContent className="border-t border-border py-3">
          {/* Collapsible SQL section */}
          {result.sql && (
            <div className="mb-3" data-testid={`result-sql-section-${result.id}`}>
              <button
                className="mb-1 flex w-full items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground"
                onClick={() => setSqlExpanded((prev) => !prev)}
                data-testid={`toggle-sql-${result.id}`}
                aria-label={sqlExpanded ? "Collapse SQL" : "Expand SQL"}
              >
                {sqlExpanded ? (
                  <ChevronDown className="size-3" />
                ) : (
                  <ChevronRight className="size-3" />
                )}
                SQL
              </button>
              {sqlExpanded && (
                <pre
                  data-testid={`result-sql-code-${result.id}`}
                  className="overflow-x-auto rounded-md bg-muted p-2 text-xs"
                >
                  <code>
                    {highlightSql(result.sql).map((token, i) =>
                      token.isKeyword ? (
                        <span key={i} className="font-semibold text-primary">
                          {token.text}
                        </span>
                      ) : (
                        <span key={i}>{token.text}</span>
                      ),
                    )}
                  </code>
                </pre>
              )}
            </div>
          )}

          {/* Data table */}
          {result.data && result.data.length > 0 && (
            <div className="mb-3" data-testid={`result-table-section-${result.id}`}>
              <div className="mb-1 flex items-center justify-between">
                <p className="text-xs font-medium text-muted-foreground">
                  Results ({result.rowCount.toLocaleString()} row{result.rowCount !== 1 ? "s" : ""})
                </p>
                <Button
                  variant="ghost"
                  size="xs"
                  onClick={handleExportCsv}
                  aria-label="Export CSV"
                  data-testid={`export-csv-${result.id}`}
                >
                  <Download className="size-3" />
                  <span>CSV</span>
                </Button>
              </div>
              <div
                className="overflow-x-auto rounded-md border"
                data-testid={`result-table-scroll-${result.id}`}
              >
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b bg-muted/50">
                      {result.columns.map((col) => (
                        <th
                          key={col}
                          className="cursor-pointer select-none px-3 py-1.5 text-left font-medium text-muted-foreground hover:text-foreground"
                          onClick={() => handleSort(col)}
                          data-testid={`sort-column-${col}`}
                          aria-label={`Sort by ${col}`}
                        >
                          <span className="inline-flex items-center gap-1">
                            {col}
                            {sortState.column === col && sortState.direction === "asc" && (
                              <ArrowUp className="size-3" data-testid={`sort-asc-${col}`} />
                            )}
                            {sortState.column === col && sortState.direction === "desc" && (
                              <ArrowDown className="size-3" data-testid={`sort-desc-${col}`} />
                            )}
                          </span>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {paginatedData.map((row, rowIdx) => (
                      <tr
                        key={rowIdx}
                        className={cn(
                          "border-b last:border-b-0",
                          rowIdx % 2 === 1 && "bg-muted/25",
                        )}
                      >
                        {result.columns.map((col) => {
                          const raw = formatCellValue(row[col]);
                          const { display, isTruncated } = truncateValue(raw, MAX_CELL_LENGTH);
                          const isNull = row[col] === null || row[col] === undefined;
                          return (
                            <td
                              key={col}
                              className={cn(
                                "max-w-[300px] px-3 py-1.5",
                                isNull && "italic text-muted-foreground",
                              )}
                              title={isTruncated ? raw : undefined}
                              data-testid={isTruncated ? `truncated-cell-${rowIdx}-${col}` : undefined}
                            >
                              {display}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Pagination controls */}
              {totalPages > 1 && (
                <div
                  className="mt-2 flex items-center justify-between text-xs text-muted-foreground"
                  data-testid={`result-pagination-${result.id}`}
                >
                  <span>
                    Page {currentPage + 1} of {totalPages}
                  </span>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon-xs"
                      disabled={currentPage === 0}
                      onClick={() => setCurrentPage((p) => p - 1)}
                      aria-label="Previous page"
                      data-testid={`prev-page-${result.id}`}
                    >
                      <ChevronLeft className="size-3" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-xs"
                      disabled={currentPage >= totalPages - 1}
                      onClick={() => setCurrentPage((p) => p + 1)}
                      aria-label="Next page"
                      data-testid={`next-page-${result.id}`}
                    >
                      <ChevronRight className="size-3" />
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* AI explanation */}
          {result.explanation && (
            <div className="mb-3" data-testid={`result-explanation-${result.id}`}>
              <p className="mb-1 text-xs font-medium text-muted-foreground">
                Explanation
              </p>
              <p className="text-sm text-foreground">{result.explanation}</p>
            </div>
          )}

          {/* Chart visualization */}
          {result.chartConfig && (
            <div className="mb-3" data-testid={`result-chart-${result.id}`}>
              <ChartRenderer
                chartConfig={result.chartConfig as ChartConfig}
                resolvedTheme={resolvedTheme}
              />
            </div>
          )}

          {/* Empty data state */}
          {(!result.data || result.data.length === 0) && !result.explanation && !result.error && (
            <p
              className="text-sm text-muted-foreground"
              data-testid={`result-empty-data-${result.id}`}
            >
              No data returned by this query.
            </p>
          )}
        </CardContent>
      )}
    </Card>
  );
}
