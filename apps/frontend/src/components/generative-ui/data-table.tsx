import { useState, useMemo, useCallback, useRef } from "react";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  flexRender,
  type ColumnDef,
  type SortingState,
  type ColumnFiltersState,
  type VisibilityState,
  type ColumnOrderState,
  type Row,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import {
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Search,
  Columns3,
  GripVertical,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  ComponentErrorBoundary,
  ActionToolbar,
} from "@/components/generative-ui";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";

/* -------------------------------------------------------------------------- */
/*  Types                                                                      */
/* -------------------------------------------------------------------------- */

export interface DataTableColumn {
  name: string;
  type?: string;
}

export interface DataTableProps {
  columns: DataTableColumn[];
  rows: unknown[][];
  title?: string;
  /** Callback when the pin/bookmark button is clicked. */
  onPin?: () => void;
  /** Whether this table is already bookmarked. */
  isPinned?: boolean;
  className?: string;
}

type RowData = Record<string, unknown>;

/* -------------------------------------------------------------------------- */
/*  Constants                                                                  */
/* -------------------------------------------------------------------------- */

const PAGE_SIZE_OPTIONS = [25, 50, 100, 250];
const DEFAULT_PAGE_SIZE = 50;
const ROW_HEIGHT = 36;
const VIRTUAL_OVERSCAN = 10;

/* -------------------------------------------------------------------------- */
/*  DataTable (public wrapper with error boundary)                             */
/* -------------------------------------------------------------------------- */

export function DataTable({
  columns,
  rows,
  title,
  onPin,
  isPinned,
  className,
}: DataTableProps) {
  return (
    <ComponentErrorBoundary componentName="DataTable">
      <DataTableInner
        columns={columns}
        rows={rows}
        title={title}
        onPin={onPin}
        isPinned={isPinned}
        className={className}
      />
    </ComponentErrorBoundary>
  );
}

/* -------------------------------------------------------------------------- */
/*  DataTableInner                                                             */
/* -------------------------------------------------------------------------- */

function DataTableInner({
  columns: columnDefs,
  rows: rawRows,
  title,
  onPin,
  isPinned,
  className,
}: DataTableProps) {
  /* -- State -- */
  const [sorting, setSorting] = useState<SortingState>([]);
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);
  const [globalFilter, setGlobalFilter] = useState("");
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({});
  const [columnOrder, setColumnOrder] = useState<ColumnOrderState>([]);
  const [showColumnPicker, setShowColumnPicker] = useState(false);
  const columnPickerRef = useRef<HTMLDivElement>(null);
  const tableContainerRef = useRef<HTMLDivElement>(null);

  /* -- Transform raw data into row objects -- */
  const data: RowData[] = useMemo(() => {
    return rawRows.map((row) => {
      const obj: RowData = {};
      columnDefs.forEach((col, idx) => {
        obj[col.name] = row[idx] ?? null;
      });
      return obj;
    });
  }, [rawRows, columnDefs]);

  /* -- Build TanStack Table column definitions -- */
  const tanstackColumns: ColumnDef<RowData>[] = useMemo(() => {
    return columnDefs.map((col) => ({
      accessorKey: col.name,
      header: col.name,
      cell: ({ getValue }) => {
        const value = getValue();
        if (value === null || value === undefined) {
          return <span className="text-muted-foreground/50 italic">null</span>;
        }
        return <span className="truncate" title={String(value)}>{String(value)}</span>;
      },
      filterFn: "auto" as const,
    }));
  }, [columnDefs]);

  /* -- Initialize column order -- */
  const effectiveColumnOrder = useMemo(() => {
    if (columnOrder.length > 0) return columnOrder;
    return columnDefs.map((c) => c.name);
  }, [columnOrder, columnDefs]);

  /* -- Table instance -- */
  const table = useReactTable({
    data,
    columns: tanstackColumns,
    state: {
      sorting,
      columnFilters,
      globalFilter,
      columnVisibility,
      columnOrder: effectiveColumnOrder,
    },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onGlobalFilterChange: setGlobalFilter,
    onColumnVisibilityChange: setColumnVisibility,
    onColumnOrderChange: setColumnOrder,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: {
      pagination: {
        pageSize: DEFAULT_PAGE_SIZE,
      },
    },
  });

  const { rows: tableRows } = table.getRowModel();
  const filteredRowCount = table.getFilteredRowModel().rows.length;
  const totalRowCount = data.length;
  const isFiltered = globalFilter !== "" || columnFilters.length > 0;
  const isWideTable = columnDefs.length > 10;

  /* -- Virtual scrolling -- */
  const rowVirtualizer = useVirtualizer({
    count: tableRows.length,
    getScrollElement: () => tableContainerRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: VIRTUAL_OVERSCAN,
  });

  /* -- Column drag-and-drop -- */
  const dragColumnRef = useRef<string | null>(null);

  const handleDragStart = useCallback((columnId: string) => {
    dragColumnRef.current = columnId;
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
  }, []);

  const handleDrop = useCallback(
    (targetColumnId: string) => {
      const sourceId = dragColumnRef.current;
      if (!sourceId || sourceId === targetColumnId) return;

      const currentOrder = effectiveColumnOrder.slice();
      const sourceIdx = currentOrder.indexOf(sourceId);
      const targetIdx = currentOrder.indexOf(targetColumnId);
      if (sourceIdx === -1 || targetIdx === -1) return;

      currentOrder.splice(sourceIdx, 1);
      currentOrder.splice(targetIdx, 0, sourceId);
      setColumnOrder(currentOrder);
      dragColumnRef.current = null;
    },
    [effectiveColumnOrder],
  );

  /* -- Empty state -- */
  if (columnDefs.length === 0 || rawRows.length === 0) {
    return (
      <div
        data-testid="data-table-empty"
        className={cn(
          "flex flex-col items-center justify-center gap-2 rounded-lg border bg-card p-8 text-center shadow-sm",
          className,
        )}
      >
        <p className="text-sm font-medium text-foreground">No data</p>
        <p className="text-xs text-muted-foreground">
          The query returned no results.
        </p>
      </div>
    );
  }

  const headerGroups = table.getHeaderGroups();

  return (
    <div
      data-testid="data-table"
      className={cn(
        "flex flex-col gap-3 rounded-lg border bg-card shadow-sm",
        className,
      )}
    >
      {/* -- Header bar -- */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b px-4 pt-3 pb-2">
        <div className="flex items-center gap-2">
          {title && (
            <h3 className="text-sm font-semibold text-foreground">{title}</h3>
          )}
          <Badge variant="secondary" data-testid="row-count-badge">
            {isFiltered
              ? `${filteredRowCount} of ${totalRowCount} rows`
              : `${totalRowCount} rows`}
          </Badge>
          {isFiltered && (
            <Badge variant="outline" data-testid="filter-status-badge">
              Filtered
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-2">
          {/* Global search */}
          <div className="relative">
            <Search className="absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              data-testid="global-search"
              placeholder="Search all columns..."
              value={globalFilter}
              onChange={(e) => setGlobalFilter(e.target.value)}
              className="h-7 w-48 pl-7 text-xs"
            />
          </div>

          {/* Column picker */}
          <div className="relative" ref={columnPickerRef}>
            <Button
              variant="outline"
              size="xs"
              onClick={() => setShowColumnPicker((prev) => !prev)}
              data-testid="column-picker-toggle"
              aria-label="Toggle columns"
            >
              <Columns3 className="size-3.5" />
              Columns
            </Button>
            {showColumnPicker && (
              <ColumnPickerDropdown
                table={table}
                onClose={() => setShowColumnPicker(false)}
              />
            )}
          </div>

          <ActionToolbar onPin={onPin} isPinned={isPinned} onExport={() => {}} />
        </div>
      </div>

      {/* -- Table container with virtual scrolling -- */}
      <div
        ref={tableContainerRef}
        data-testid="table-scroll-container"
        className={cn(
          "overflow-auto px-1",
          isWideTable ? "max-h-[480px]" : "max-h-[400px]",
        )}
        style={{ contain: "strict", height: Math.min(tableRows.length * ROW_HEIGHT + ROW_HEIGHT + 16, 480) }}
      >
        <table className="w-full border-collapse text-xs">
          <thead className="sticky top-0 z-10 bg-card">
            {headerGroups.map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header, colIdx) => {
                  const isSorted = header.column.getIsSorted();
                  const canSort = header.column.getCanSort();

                  return (
                    <th
                      key={header.id}
                      data-testid={`column-header-${header.column.id}`}
                      className={cn(
                        "whitespace-nowrap border-b px-3 py-2 text-left font-medium text-muted-foreground",
                        canSort && "cursor-pointer select-none hover:text-foreground",
                        colIdx === 0 && isWideTable && "sticky left-0 z-20 bg-card",
                      )}
                      style={{ minWidth: 100 }}
                      onClick={canSort ? header.column.getToggleSortingHandler() : undefined}
                      draggable
                      onDragStart={() => handleDragStart(header.column.id)}
                      onDragOver={handleDragOver}
                      onDrop={() => handleDrop(header.column.id)}
                    >
                      <div className="flex items-center gap-1">
                        <GripVertical className="size-3 text-muted-foreground/40 shrink-0" />
                        <span>
                          {flexRender(
                            header.column.columnDef.header,
                            header.getContext(),
                          )}
                        </span>
                        {canSort && (
                          <span className="ml-auto shrink-0">
                            {isSorted === "asc" ? (
                              <ArrowUp className="size-3" data-testid="sort-asc" />
                            ) : isSorted === "desc" ? (
                              <ArrowDown className="size-3" data-testid="sort-desc" />
                            ) : (
                              <ArrowUpDown className="size-3 opacity-30" />
                            )}
                          </span>
                        )}
                      </div>
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody
            style={{
              height: `${rowVirtualizer.getTotalSize()}px`,
              position: "relative",
            }}
          >
            {rowVirtualizer.getVirtualItems().map((virtualRow) => {
              const row = tableRows[virtualRow.index] as Row<RowData>;
              return (
                <tr
                  key={row.id}
                  data-testid="data-row"
                  className="border-b border-border/50 hover:bg-muted/50"
                  style={{
                    height: `${virtualRow.size}px`,
                    position: "absolute",
                    top: 0,
                    left: 0,
                    width: "100%",
                    transform: `translateY(${virtualRow.start}px)`,
                  }}
                >
                  {row.getVisibleCells().map((cell, cellIdx) => (
                    <td
                      key={cell.id}
                      className={cn(
                        "whitespace-nowrap px-3 py-1.5 text-foreground",
                        cellIdx === 0 && isWideTable && "sticky left-0 z-10 bg-card",
                      )}
                      style={{ minWidth: 100 }}
                    >
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* -- Pagination footer -- */}
      <div
        data-testid="table-pagination"
        className="flex flex-wrap items-center justify-between gap-2 border-t px-4 py-2 text-xs text-muted-foreground"
      >
        <div className="flex items-center gap-2">
          <span>Rows per page:</span>
          <select
            data-testid="page-size-select"
            value={table.getState().pagination.pageSize}
            onChange={(e) => table.setPageSize(Number(e.target.value))}
            className="h-6 rounded border bg-background px-1 text-xs text-foreground"
          >
            {PAGE_SIZE_OPTIONS.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-2">
          <span>
            Page {table.getState().pagination.pageIndex + 1} of{" "}
            {table.getPageCount()}
          </span>
          <Button
            variant="outline"
            size="icon-xs"
            onClick={() => table.previousPage()}
            disabled={!table.getCanPreviousPage()}
            data-testid="prev-page"
            aria-label="Previous page"
          >
            <ChevronLeft className="size-3" />
          </Button>
          <Button
            variant="outline"
            size="icon-xs"
            onClick={() => table.nextPage()}
            disabled={!table.getCanNextPage()}
            data-testid="next-page"
            aria-label="Next page"
          >
            <ChevronRight className="size-3" />
          </Button>
        </div>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Column Picker Dropdown                                                     */
/* -------------------------------------------------------------------------- */

function ColumnPickerDropdown({
  table,
  onClose,
}: {
  table: ReturnType<typeof useReactTable<RowData>>;
  onClose: () => void;
}) {
  const allColumns = table.getAllLeafColumns();

  return (
    <div
      data-testid="column-picker-dropdown"
      className="absolute right-0 top-full z-50 mt-1 max-h-64 min-w-[180px] overflow-auto rounded-md border bg-popover p-2 shadow-md dark:border-border"
    >
      <div className="mb-2 flex items-center justify-between border-b pb-2">
        <span className="text-xs font-medium text-foreground">Visible Columns</span>
        <button
          onClick={onClose}
          className="text-xs text-muted-foreground hover:text-foreground"
          data-testid="column-picker-close"
        >
          Done
        </button>
      </div>
      {allColumns.map((column) => (
        <label
          key={column.id}
          className="flex items-center gap-2 rounded px-2 py-1 text-xs hover:bg-accent cursor-pointer"
        >
          <input
            type="checkbox"
            checked={column.getIsVisible()}
            onChange={column.getToggleVisibilityHandler()}
            data-testid={`column-toggle-${column.id}`}
            className="rounded border-input"
          />
          <span className="text-foreground">{column.id}</span>
        </label>
      ))}
    </div>
  );
}
