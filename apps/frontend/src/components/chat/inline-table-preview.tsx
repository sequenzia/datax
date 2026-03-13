import { useState, useMemo } from "react";
import { Maximize2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { DataExplorerModal } from "./data-explorer-modal";

const MAX_PREVIEW_ROWS = 8;
const MAX_CELL_LENGTH = 60;

function formatCellValue(value: unknown): string {
  if (value === null || value === undefined) return "NULL";
  return String(value);
}

function truncate(value: string, max: number): string {
  return value.length <= max ? value : value.slice(0, max) + "...";
}

interface InlineTablePreviewProps {
  columns: string[];
  data: Record<string, unknown>[];
  rowCount: number;
  className?: string;
}

export function InlineTablePreview({
  columns,
  data,
  rowCount,
  className,
}: InlineTablePreviewProps) {
  const [modalOpen, setModalOpen] = useState(false);

  const previewData = useMemo(() => data.slice(0, MAX_PREVIEW_ROWS), [data]);
  const hasMore = data.length > MAX_PREVIEW_ROWS;

  return (
    <>
      <div
        className={cn("rounded-lg border overflow-hidden", className)}
        data-testid="inline-table-preview"
      >
        {/* Header */}
        <div className="flex items-center justify-between bg-muted/30 px-3 py-1.5">
          <span className="text-[11px] font-medium text-muted-foreground">
            {rowCount.toLocaleString()} row{rowCount !== 1 ? "s" : ""}
          </span>
          <Button
            variant="ghost"
            size="icon-xs"
            onClick={() => setModalOpen(true)}
            aria-label="Expand table"
            data-testid="expand-table-button"
          >
            <Maximize2 className="size-3" />
          </Button>
        </div>

        {/* Compact table */}
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b bg-muted/20">
                {columns.map((col) => (
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
              {previewData.map((row, rowIdx) => (
                <tr
                  key={rowIdx}
                  className={cn(
                    "border-b last:border-b-0",
                    rowIdx % 2 === 1 && "bg-muted/10",
                  )}
                >
                  {columns.map((col) => {
                    const raw = formatCellValue(row[col]);
                    const isNull = row[col] === null || row[col] === undefined;
                    return (
                      <td
                        key={col}
                        className={cn(
                          "max-w-[200px] px-3 py-1",
                          isNull && "italic text-muted-foreground",
                        )}
                        title={raw.length > MAX_CELL_LENGTH ? raw : undefined}
                      >
                        {truncate(raw, MAX_CELL_LENGTH)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* "Show more" hint */}
        {hasMore && (
          <button
            onClick={() => setModalOpen(true)}
            className="w-full border-t py-1.5 text-center text-[11px] text-muted-foreground hover:bg-muted/30 transition-colors"
          >
            + {data.length - MAX_PREVIEW_ROWS} more rows &mdash; click to expand
          </button>
        )}
      </div>

      <DataExplorerModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        columns={columns}
        data={data}
        rowCount={rowCount}
      />
    </>
  );
}
