import { useState } from "react";
import { DataTable } from "./data-table";
import { PinToDashboardDialog } from "./pin-to-dashboard-dialog";
import type { DataTableColumn } from "./data-table";

export interface PinnableTableProps {
  columns: DataTableColumn[];
  rows: unknown[][];
  title?: string;
  sql?: string;
  sourceId?: string;
  sourceType?: string;
  className?: string;
}

export function PinnableTable({
  columns,
  rows,
  title,
  sql,
  sourceId,
  sourceType,
  className,
}: PinnableTableProps) {
  const [pinDialogOpen, setPinDialogOpen] = useState(false);

  return (
    <>
      <DataTable
        columns={columns}
        rows={rows}
        title={title}
        onPin={() => setPinDialogOpen(true)}
        className={className}
      />
      <PinToDashboardDialog
        open={pinDialogOpen}
        onOpenChange={setPinDialogOpen}
        bookmarkData={{
          title: title ?? "Table Result",
          sql,
          result_snapshot: { columns: columns.map((c) => c.name), rows: rows.slice(0, 50), row_count: rows.length },
          source_id: sourceId,
          source_type: sourceType,
        }}
      />
    </>
  );
}
