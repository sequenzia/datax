import { useState, useMemo, useCallback } from "react";
import {
  ArrowUp,
  ArrowDown,
  ChevronLeft,
  ChevronRight,
  Download,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

type SortDirection = "asc" | "desc" | null;
interface SortState {
  column: string | null;
  direction: SortDirection;
}

const PAGE_SIZE = 100;
const MAX_CELL_LENGTH = 100;

function formatCellValue(value: unknown): string {
  if (value === null || value === undefined) return "NULL";
  return String(value);
}

function sortData(
  data: Record<string, unknown>[],
  sortState: SortState,
): Record<string, unknown>[] {
  if (!sortState.column || !sortState.direction) return data;
  const { column, direction } = sortState;

  return [...data].sort((a, b) => {
    const aVal = a[column];
    const bVal = b[column];
    if (aVal === null || aVal === undefined) return direction === "asc" ? -1 : 1;
    if (bVal === null || bVal === undefined) return direction === "asc" ? 1 : -1;
    if (typeof aVal === "number" && typeof bVal === "number") {
      return direction === "asc" ? aVal - bVal : bVal - aVal;
    }
    const cmp = String(aVal).localeCompare(String(bVal));
    return direction === "asc" ? cmp : -cmp;
  });
}

function generateCsv(columns: string[], data: Record<string, unknown>[]): string {
  const escape = (v: string): string =>
    v.includes(",") || v.includes('"') || v.includes("\n")
      ? `"${v.replace(/"/g, '""')}"`
      : v;
  const header = columns.map(escape).join(",");
  const rows = data.map((row) =>
    columns.map((col) => escape(formatCellValue(row[col]))).join(","),
  );
  return [header, ...rows].join("\n");
}

interface DataExplorerModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  columns: string[];
  data: Record<string, unknown>[];
  rowCount: number;
}

export function DataExplorerModal({
  open,
  onOpenChange,
  columns,
  data,
  rowCount,
}: DataExplorerModalProps) {
  const [sortState, setSortState] = useState<SortState>({
    column: null,
    direction: null,
  });
  const [currentPage, setCurrentPage] = useState(0);

  const sortedData = useMemo(() => sortData(data, sortState), [data, sortState]);
  const totalPages = Math.max(1, Math.ceil(sortedData.length / PAGE_SIZE));
  const paginatedData = useMemo(() => {
    const start = currentPage * PAGE_SIZE;
    return sortedData.slice(start, start + PAGE_SIZE);
  }, [sortedData, currentPage]);

  const handleSort = useCallback((column: string) => {
    setSortState((prev) => {
      if (prev.column !== column) return { column, direction: "asc" };
      if (prev.direction === "asc") return { column, direction: "desc" };
      return { column: null, direction: null };
    });
    setCurrentPage(0);
  }, []);

  const handleExportCsv = useCallback(() => {
    const csv = generateCsv(columns, data);
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `query_results_${Date.now()}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }, [columns, data]);

  const handleExportJson = useCallback(() => {
    const json = JSON.stringify(data, null, 2);
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `query_results_${Date.now()}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }, [data]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl max-h-[85vh] flex flex-col">
        <DialogHeader>
          <div className="flex items-center justify-between">
            <DialogTitle>
              Data Explorer &mdash; {rowCount.toLocaleString()} rows
            </DialogTitle>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="xs" onClick={handleExportCsv}>
                <Download className="size-3" /> CSV
              </Button>
              <Button variant="outline" size="xs" onClick={handleExportJson}>
                <Download className="size-3" /> JSON
              </Button>
            </div>
          </div>
        </DialogHeader>

        {/* Scrollable table */}
        <div className="flex-1 overflow-auto rounded-md border" data-testid="data-explorer-table">
          <table className="w-full text-xs">
            <thead className="sticky top-0 z-10">
              <tr className="bg-muted/80 backdrop-blur">
                {columns.map((col) => (
                  <th
                    key={col}
                    className="cursor-pointer select-none px-3 py-2 text-left font-medium text-muted-foreground hover:text-foreground"
                    onClick={() => handleSort(col)}
                  >
                    <span className="inline-flex items-center gap-1">
                      {col}
                      {sortState.column === col && sortState.direction === "asc" && (
                        <ArrowUp className="size-3" />
                      )}
                      {sortState.column === col && sortState.direction === "desc" && (
                        <ArrowDown className="size-3" />
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
                    rowIdx % 2 === 1 && "bg-muted/15",
                  )}
                >
                  {columns.map((col) => {
                    const raw = formatCellValue(row[col]);
                    const isNull = row[col] === null || row[col] === undefined;
                    const display =
                      raw.length > MAX_CELL_LENGTH
                        ? raw.slice(0, MAX_CELL_LENGTH) + "..."
                        : raw;
                    return (
                      <td
                        key={col}
                        className={cn(
                          "max-w-[300px] px-3 py-1.5",
                          isNull && "italic text-muted-foreground",
                        )}
                        title={raw.length > MAX_CELL_LENGTH ? raw : undefined}
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

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between pt-2 text-xs text-muted-foreground">
            <span>
              Page {currentPage + 1} of {totalPages}
            </span>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon-xs"
                disabled={currentPage === 0}
                onClick={() => setCurrentPage((p) => p - 1)}
              >
                <ChevronLeft className="size-3" />
              </Button>
              <Button
                variant="ghost"
                size="icon-xs"
                disabled={currentPage >= totalPages - 1}
                onClick={() => setCurrentPage((p) => p + 1)}
              >
                <ChevronRight className="size-3" />
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
