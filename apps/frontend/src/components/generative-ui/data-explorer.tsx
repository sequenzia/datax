import { useState, useMemo, useCallback, useRef } from "react";
import {
  Search,
  Hash,
  Type,
  Calendar,
  ToggleLeft,
  Binary,
  ChevronRight,
  Filter,
  X,
  AlertCircle,
  Loader2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useDatasetProfile } from "@/hooks/use-datasets";
import {
  ProfileSkeleton,
  ComponentErrorBoundary,
  ActionToolbar,
} from "@/components/generative-ui";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import type { ColumnSummary, DatasetProfile } from "@/types/api";

/* -------------------------------------------------------------------------- */
/*  Constants                                                                  */
/* -------------------------------------------------------------------------- */

/** Height (px) of each row in the virtualized column list. */
const COLUMN_ROW_HEIGHT = 52;
/** Max visible rows before scrolling kicks in. */
const MAX_VISIBLE_ROWS = 12;
/** Threshold for marking a column as "all unique". */
const ALL_UNIQUE_THRESHOLD = 0.98;

/* -------------------------------------------------------------------------- */
/*  Type helpers                                                               */
/* -------------------------------------------------------------------------- */

type ColumnTypeCategory = "numeric" | "text" | "date" | "boolean" | "other";

function classifyColumnType(colType: string): ColumnTypeCategory {
  const upper = colType.toUpperCase();
  if (
    ["BIGINT", "INTEGER", "DOUBLE", "FLOAT", "DECIMAL", "HUGEINT", "SMALLINT", "TINYINT", "NUMERIC", "REAL"].some(
      (t) => upper.includes(t),
    )
  ) {
    return "numeric";
  }
  if (["VARCHAR", "TEXT", "STRING", "CHAR", "BLOB"].some((t) => upper.includes(t))) {
    return "text";
  }
  if (["DATE", "TIMESTAMP", "TIME", "INTERVAL"].some((t) => upper.includes(t))) {
    return "date";
  }
  if (upper.includes("BOOLEAN") || upper.includes("BOOL")) {
    return "boolean";
  }
  return "other";
}

/** Renders a type-appropriate icon for a column category. */
function TypeIcon({ category, className }: { category: ColumnTypeCategory; className?: string }) {
  const colorClass = (() => {
    switch (category) {
      case "numeric": return "text-blue-500";
      case "text": return "text-green-500";
      case "date": return "text-orange-500";
      case "boolean": return "text-purple-500";
      default: return "text-gray-500";
    }
  })();

  const mergedClass = cn(className, colorClass);

  switch (category) {
    case "numeric": return <Hash className={mergedClass} />;
    case "text": return <Type className={mergedClass} />;
    case "date": return <Calendar className={mergedClass} />;
    case "boolean": return <ToggleLeft className={mergedClass} />;
    default: return <Binary className={mergedClass} />;
  }
}

/* -------------------------------------------------------------------------- */
/*  DataExplorer Component                                                     */
/* -------------------------------------------------------------------------- */

export interface DataExplorerProps {
  datasetId: string;
  datasetName?: string;
  /** When true, renders in full-screen mode (for the /explore page). */
  fullScreen?: boolean;
  className?: string;
}

export function DataExplorer({
  datasetId,
  datasetName,
  fullScreen = false,
  className,
}: DataExplorerProps) {
  return (
    <ComponentErrorBoundary componentName="DataExplorer">
      <DataExplorerInner
        datasetId={datasetId}
        datasetName={datasetName}
        fullScreen={fullScreen}
        className={className}
      />
    </ComponentErrorBoundary>
  );
}

function DataExplorerInner({
  datasetId,
  datasetName,
  fullScreen,
  className,
}: DataExplorerProps) {
  const {
    data: profile,
    isLoading,
    isError,
    error,
    refetch,
  } = useDatasetProfile(datasetId);

  const [searchQuery, setSearchQuery] = useState("");
  const [selectedColumn, setSelectedColumn] = useState<string | null>(null);
  const [activeFilters, setActiveFilters] = useState<
    Map<string, string>
  >(new Map());

  if (isLoading) {
    return <ProfileSkeleton className={className} />;
  }

  if (isError) {
    return (
      <div
        data-testid="data-explorer-error"
        className={cn(
          "flex flex-col items-center gap-3 rounded-lg border border-destructive/30 bg-destructive/5 p-6 text-sm",
          className,
        )}
      >
        <AlertCircle className="size-5 text-destructive" />
        <p className="text-destructive">
          Failed to load profile:{" "}
          {error instanceof Error ? error.message : "Unknown error"}
        </p>
        <Button variant="outline" size="sm" onClick={() => void refetch()}>
          Retry
        </Button>
      </div>
    );
  }

  if (!profile) {
    return (
      <div
        data-testid="data-explorer-no-profile"
        className={cn(
          "flex flex-col items-center gap-3 rounded-lg border border-dashed p-6 text-sm text-muted-foreground",
          className,
        )}
      >
        <Loader2 className="size-5 animate-spin" />
        <p>No profiling data available. Triggering on-demand profiling...</p>
      </div>
    );
  }

  return (
    <DataExplorerContent
      profile={profile}
      datasetName={datasetName}
      fullScreen={fullScreen}
      className={className}
      searchQuery={searchQuery}
      setSearchQuery={setSearchQuery}
      selectedColumn={selectedColumn}
      setSelectedColumn={setSelectedColumn}
      activeFilters={activeFilters}
      setActiveFilters={setActiveFilters}
    />
  );
}

/* -------------------------------------------------------------------------- */
/*  Main content with column browser + detail                                  */
/* -------------------------------------------------------------------------- */

interface DataExplorerContentProps {
  profile: DatasetProfile;
  datasetName?: string;
  fullScreen?: boolean;
  className?: string;
  searchQuery: string;
  setSearchQuery: (q: string) => void;
  selectedColumn: string | null;
  setSelectedColumn: (col: string | null) => void;
  activeFilters: Map<string, string>;
  setActiveFilters: React.Dispatch<React.SetStateAction<Map<string, string>>>;
}

function DataExplorerContent({
  profile,
  datasetName,
  fullScreen,
  className,
  searchQuery,
  setSearchQuery,
  selectedColumn,
  setSelectedColumn,
  activeFilters,
  setActiveFilters,
}: DataExplorerContentProps) {
  const columns = profile.summarize_results;
  const sampleValues = profile.sample_values;

  // Filter columns based on search query
  const filteredColumns = useMemo(() => {
    if (!searchQuery.trim()) return columns;
    const q = searchQuery.toLowerCase();
    return columns.filter((col) => col.column_name.toLowerCase().includes(q));
  }, [columns, searchQuery]);

  // Find the selected column data
  const selectedColumnData = useMemo(
    () => columns.find((c) => c.column_name === selectedColumn) ?? null,
    [columns, selectedColumn],
  );

  const handleQuickFilter = useCallback(
    (columnName: string, value: string) => {
      setActiveFilters((prev) => {
        const next = new Map(prev);
        if (next.get(columnName) === value) {
          next.delete(columnName);
        } else {
          next.set(columnName, value);
        }
        return next;
      });
    },
    [setActiveFilters],
  );

  const clearFilters = useCallback(() => {
    setActiveFilters(new Map());
  }, [setActiveFilters]);

  const containerHeight = fullScreen ? "h-full" : "max-h-[600px]";

  return (
    <div
      data-testid="data-explorer"
      className={cn(
        "flex flex-col rounded-lg border bg-card shadow-sm",
        containerHeight,
        className,
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div>
          <h3 className="text-sm font-semibold text-foreground">
            {datasetName ? `Explore: ${datasetName}` : "Data Explorer"}
          </h3>
          <p className="text-xs text-muted-foreground">
            {columns.length} column{columns.length !== 1 ? "s" : ""}
            {profile.profiled_at && (
              <span>
                {" "}
                &middot; profiled{" "}
                {new Date(profile.profiled_at).toLocaleString()}
              </span>
            )}
          </p>
        </div>
        <ActionToolbar onExport={() => {}} />
      </div>

      {/* Active filters bar */}
      {activeFilters.size > 0 && (
        <div
          data-testid="active-filters"
          className="flex flex-wrap items-center gap-2 border-b px-4 py-2"
        >
          <Filter className="size-3.5 text-muted-foreground" />
          {Array.from(activeFilters.entries()).map(([col, val]) => (
            <Badge
              key={col}
              variant="secondary"
              className="flex items-center gap-1 text-xs"
            >
              {col}: {val}
              <button
                onClick={() => handleQuickFilter(col, val)}
                className="ml-1 rounded-full p-0.5 hover:bg-muted"
                aria-label={`Remove filter ${col}`}
              >
                <X className="size-3" />
              </button>
            </Badge>
          ))}
          <button
            onClick={clearFilters}
            className="text-xs text-muted-foreground hover:text-foreground"
          >
            Clear all
          </button>
        </div>
      )}

      {/* Body: Column browser + detail */}
      <div className="flex min-h-0 flex-1">
        {/* Column browser panel */}
        <div
          data-testid="column-browser"
          className={cn(
            "flex flex-col border-r",
            selectedColumn ? "w-1/2 lg:w-2/5" : "w-full",
          )}
        >
          {/* Column search */}
          <div className="border-b px-3 py-2">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                data-testid="column-search"
                type="text"
                placeholder="Search columns..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="h-8 pl-8 text-xs"
              />
            </div>
          </div>

          {/* Column list */}
          <ColumnList
            columns={filteredColumns}
            sampleValues={sampleValues}
            selectedColumn={selectedColumn}
            onSelect={setSelectedColumn}
          />

          {filteredColumns.length === 0 && searchQuery && (
            <div className="flex flex-col items-center gap-2 p-6 text-muted-foreground">
              <Search className="size-5" />
              <p className="text-xs">No columns match "{searchQuery}"</p>
            </div>
          )}
        </div>

        {/* Column detail panel */}
        {selectedColumn && selectedColumnData && (
          <div
            data-testid="column-detail"
            className="flex min-h-0 w-1/2 flex-col overflow-y-auto lg:w-3/5"
          >
            <ColumnDetail
              column={selectedColumnData}
              samples={sampleValues[selectedColumnData.column_name] ?? []}
              totalRowCount={
                columns[0]?.count ? parseInt(columns[0].count, 10) : 0
              }
              onClose={() => setSelectedColumn(null)}
              onQuickFilter={handleQuickFilter}
            />
          </div>
        )}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Column List (virtualized for 500+ columns)                                 */
/* -------------------------------------------------------------------------- */

interface ColumnListProps {
  columns: ColumnSummary[];
  sampleValues: Record<string, unknown[]>;
  selectedColumn: string | null;
  onSelect: (col: string) => void;
}

function ColumnList({
  columns,
  selectedColumn,
  onSelect,
}: ColumnListProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const useVirtual = columns.length > MAX_VISIBLE_ROWS;

  // For virtual scrolling: calculate total height
  const totalHeight = useVirtual
    ? columns.length * COLUMN_ROW_HEIGHT
    : undefined;
  const [scrollTop, setScrollTop] = useState(0);

  const handleScroll = useCallback(() => {
    if (containerRef.current) {
      setScrollTop(containerRef.current.scrollTop);
    }
  }, []);

  // Calculate visible range for virtual scrolling
  const visibleRange = useMemo(() => {
    if (!useVirtual) return { start: 0, end: columns.length };
    const containerHeight = MAX_VISIBLE_ROWS * COLUMN_ROW_HEIGHT;
    const start = Math.max(0, Math.floor(scrollTop / COLUMN_ROW_HEIGHT) - 2);
    const end = Math.min(
      columns.length,
      Math.ceil((scrollTop + containerHeight) / COLUMN_ROW_HEIGHT) + 2,
    );
    return { start, end };
  }, [useVirtual, scrollTop, columns.length]);

  const visibleColumns = columns.slice(visibleRange.start, visibleRange.end);

  return (
    <div
      ref={containerRef}
      data-testid="column-list"
      className="min-h-0 flex-1 overflow-y-auto"
      style={{
        maxHeight: useVirtual
          ? MAX_VISIBLE_ROWS * COLUMN_ROW_HEIGHT
          : undefined,
      }}
      onScroll={handleScroll}
    >
      {useVirtual && totalHeight !== undefined && (
        <div style={{ height: totalHeight, position: "relative" }}>
          {visibleColumns.map((col, idx) => {
            const actualIdx = visibleRange.start + idx;
            return (
              <div
                key={col.column_name}
                style={{
                  position: "absolute",
                  top: actualIdx * COLUMN_ROW_HEIGHT,
                  height: COLUMN_ROW_HEIGHT,
                  left: 0,
                  right: 0,
                }}
              >
                <ColumnRow
                  column={col}
                  isSelected={selectedColumn === col.column_name}
                  onSelect={() => onSelect(col.column_name)}
                />
              </div>
            );
          })}
        </div>
      )}
      {!useVirtual &&
        columns.map((col) => (
          <ColumnRow
            key={col.column_name}
            column={col}
            isSelected={selectedColumn === col.column_name}
            onSelect={() => onSelect(col.column_name)}
          />
        ))}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Column Row                                                                 */
/* -------------------------------------------------------------------------- */

interface ColumnRowProps {
  column: ColumnSummary;
  isSelected: boolean;
  onSelect: () => void;
}

function ColumnRow({ column, isSelected, onSelect }: ColumnRowProps) {
  const category = classifyColumnType(column.column_type);

  // Calculate null percentage as a number for the badge
  const nullPct = column.null_percentage
    ? parseFloat(column.null_percentage)
    : 0;

  const distinctCount = column.approx_unique ?? 0;

  return (
    <button
      data-testid="column-row"
      onClick={onSelect}
      className={cn(
        "flex w-full items-center gap-3 border-b px-3 py-2.5 text-left transition-colors hover:bg-accent/50",
        isSelected && "bg-accent",
      )}
    >
      <TypeIcon category={category} className="size-4 shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-foreground">
          {column.column_name}
        </p>
        <p className="text-[10px] text-muted-foreground">{column.column_type}</p>
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        {nullPct > 0 && (
          <Badge
            variant="outline"
            className={cn(
              "text-[10px] px-1.5 py-0",
              nullPct > 50 ? "border-orange-400 text-orange-600" : "",
            )}
          >
            {column.null_percentage} null
          </Badge>
        )}
        <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
          {distinctCount.toLocaleString()} distinct
        </Badge>
      </div>
      <ChevronRight className="size-3.5 shrink-0 text-muted-foreground" />
    </button>
  );
}

/* -------------------------------------------------------------------------- */
/*  Column Detail Panel                                                        */
/* -------------------------------------------------------------------------- */

interface ColumnDetailProps {
  column: ColumnSummary;
  samples: unknown[];
  totalRowCount: number;
  onClose: () => void;
  onQuickFilter: (columnName: string, value: string) => void;
}

function ColumnDetail({
  column,
  samples,
  totalRowCount,
  onClose,
  onQuickFilter,
}: ColumnDetailProps) {
  const category = classifyColumnType(column.column_type);
  const isNumeric = category === "numeric";

  const distinctCount = column.approx_unique ?? 0;
  const isAllUnique =
    totalRowCount > 0 && distinctCount / totalRowCount >= ALL_UNIQUE_THRESHOLD;

  return (
    <div className="flex flex-col gap-4 p-4">
      {/* Detail header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <TypeIcon category={category} className="size-5" />
          <div>
            <h4 className="text-sm font-semibold text-foreground">
              {column.column_name}
            </h4>
            <p className="text-xs text-muted-foreground">{column.column_type}</p>
          </div>
        </div>
        <Button
          variant="ghost"
          size="icon-xs"
          onClick={onClose}
          aria-label="Close detail"
          data-testid="close-detail"
        >
          <X className="size-4" />
        </Button>
      </div>

      {/* Statistics grid */}
      <div data-testid="column-stats" className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {column.count != null && (
          <StatCard label="Total Rows" value={column.count} />
        )}
        {column.approx_unique != null && (
          <StatCard
            label="Distinct"
            value={
              isAllUnique
                ? `${distinctCount.toLocaleString()} (all unique)`
                : distinctCount.toLocaleString()
            }
          />
        )}
        {column.null_percentage != null && (
          <StatCard label="Null %" value={column.null_percentage} />
        )}
        {isNumeric && column.min != null && (
          <StatCard label="Min" value={column.min} />
        )}
        {isNumeric && column.max != null && (
          <StatCard label="Max" value={column.max} />
        )}
        {isNumeric && column.avg != null && (
          <StatCard label="Avg" value={formatNumber(column.avg)} />
        )}
        {isNumeric && column.std != null && (
          <StatCard label="Std Dev" value={formatNumber(column.std)} />
        )}
      </div>

      {/* Distribution histogram for numeric columns */}
      {isNumeric && column.q25 != null && column.q50 != null && column.q75 != null && (
        <div data-testid="distribution-histogram">
          <h5 className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Distribution
          </h5>
          <DistributionChart
            min={Number(column.min)}
            q25={Number(column.q25)}
            q50={Number(column.q50)}
            q75={Number(column.q75)}
            max={Number(column.max)}
          />
        </div>
      )}

      {/* Top values / samples with quick filter */}
      <div>
        <h5 className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
          {isAllUnique ? "Sample Values (All Unique)" : "Top Values"}
        </h5>
        {samples.length > 0 ? (
          <div className="flex flex-wrap gap-1.5" data-testid="top-values">
            {samples.slice(0, 10).map((val, idx) => (
              <button
                key={idx}
                onClick={() =>
                  onQuickFilter(column.column_name, String(val))
                }
                className="inline-block max-w-[200px] truncate rounded-md border bg-muted/50 px-2 py-1 text-xs text-foreground transition-colors hover:bg-primary/10 hover:border-primary/30"
                title={`Filter by ${column.column_name} = ${String(val)}`}
                data-testid="quick-filter-value"
              >
                {String(val)}
              </button>
            ))}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">No sample values available.</p>
        )}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Distribution Chart (box-plot style)                                        */
/* -------------------------------------------------------------------------- */

function DistributionChart({
  min,
  q25,
  q50,
  q75,
  max,
}: {
  min: number;
  q25: number;
  q50: number;
  q75: number;
  max: number;
}) {
  const range = max - min;
  if (range === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        All values are identical ({min}).
      </p>
    );
  }

  const leftPct = ((q25 - min) / range) * 100;
  const widthPct = ((q75 - q25) / range) * 100;
  const medianPct = ((q50 - min) / range) * 100;

  return (
    <div className="space-y-2">
      {/* Box plot visualization */}
      <div className="relative h-8 w-full rounded-md bg-muted">
        {/* Whisker lines */}
        <div
          className="absolute top-1/2 h-px bg-muted-foreground/40"
          style={{ left: 0, right: 0, transform: "translateY(-50%)" }}
        />
        {/* IQR box */}
        <div
          className="absolute top-1 bottom-1 rounded bg-primary/25"
          style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
        />
        {/* Median line */}
        <div
          className="absolute top-0.5 bottom-0.5 w-0.5 rounded bg-primary"
          style={{ left: `${medianPct}%` }}
        />
        {/* Min marker */}
        <div
          className="absolute top-1 bottom-1 w-0.5 bg-muted-foreground/60"
          style={{ left: "0%" }}
        />
        {/* Max marker */}
        <div
          className="absolute top-1 bottom-1 w-0.5 bg-muted-foreground/60"
          style={{ right: "0%" }}
        />
      </div>

      {/* Labels */}
      <div className="flex justify-between text-[10px] text-muted-foreground">
        <span>Min: {formatNumber(String(min))}</span>
        <span>Q25: {formatNumber(String(q25))}</span>
        <span>Med: {formatNumber(String(q50))}</span>
        <span>Q75: {formatNumber(String(q75))}</span>
        <span>Max: {formatNumber(String(max))}</span>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Stat Card                                                                  */
/* -------------------------------------------------------------------------- */

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border bg-muted/30 p-2.5">
      <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </p>
      <p className="mt-0.5 truncate text-sm font-semibold text-foreground" title={value}>
        {value}
      </p>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Helpers                                                                    */
/* -------------------------------------------------------------------------- */

function formatNumber(val: string): string {
  const num = Number(val);
  if (Number.isNaN(num)) return val;
  if (Number.isInteger(num)) return String(num);
  return num.toFixed(2);
}
