import { useState } from "react";
import { cn } from "@/lib/utils";
import { useDatasetProfile } from "@/hooks/use-datasets";
import {
  ProfileSkeleton,
  ComponentErrorBoundary,
  ActionToolbar,
} from "@/components/generative-ui";
import type { ColumnSummary } from "@/types/api";

/* -------------------------------------------------------------------------- */
/*  Constants                                                                  */
/* -------------------------------------------------------------------------- */

/** Number of columns to display per page for wide tables. */
const COLUMNS_PER_PAGE = 20;

/* -------------------------------------------------------------------------- */
/*  DataProfile Component                                                      */
/* -------------------------------------------------------------------------- */

interface DataProfileProps {
  datasetId: string;
  datasetName?: string;
  className?: string;
}

export function DataProfile({
  datasetId,
  datasetName,
  className,
}: DataProfileProps) {
  return (
    <ComponentErrorBoundary componentName="DataProfile">
      <DataProfileInner
        datasetId={datasetId}
        datasetName={datasetName}
        className={className}
      />
    </ComponentErrorBoundary>
  );
}

function DataProfileInner({
  datasetId,
  datasetName,
  className,
}: DataProfileProps) {
  const { data: profile, isLoading, isError, error } = useDatasetProfile(datasetId);
  const [page, setPage] = useState(0);

  if (isLoading) {
    return <ProfileSkeleton className={className} />;
  }

  if (isError) {
    return (
      <div
        data-testid="data-profile-error"
        className={cn(
          "rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive",
          className,
        )}
      >
        Failed to load profile:{" "}
        {error instanceof Error ? error.message : "Unknown error"}
      </div>
    );
  }

  if (!profile) {
    return null;
  }

  const columns = profile.summarize_results;
  const sampleValues = profile.sample_values;
  const totalColumns = columns.length;
  const totalPages = Math.max(1, Math.ceil(totalColumns / COLUMNS_PER_PAGE));
  const startIdx = page * COLUMNS_PER_PAGE;
  const endIdx = Math.min(startIdx + COLUMNS_PER_PAGE, totalColumns);
  const visibleColumns = columns.slice(startIdx, endIdx);

  return (
    <div
      data-testid="data-profile"
      className={cn(
        "flex flex-col gap-4 rounded-lg border bg-card p-4 shadow-sm",
        className,
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-foreground">
            {datasetName ? `Profile: ${datasetName}` : "Data Profile"}
          </h3>
          <p className="text-xs text-muted-foreground">
            {totalColumns} column{totalColumns !== 1 ? "s" : ""} profiled
            {profile.profiled_at && (
              <span>
                {" "}
                &middot;{" "}
                {new Date(profile.profiled_at).toLocaleString()}
              </span>
            )}
          </p>
        </div>
        <ActionToolbar onExport={() => {}} />
      </div>

      {/* Column statistics cards */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {visibleColumns.map((col) => (
          <ColumnStatCard
            key={col.column_name}
            column={col}
            samples={sampleValues[col.column_name] ?? []}
          />
        ))}
      </div>

      {/* Pagination for wide tables */}
      {totalPages > 1 && (
        <div
          data-testid="profile-pagination"
          className="flex items-center justify-between border-t pt-3 text-xs text-muted-foreground"
        >
          <span>
            Showing columns {startIdx + 1}–{endIdx} of {totalColumns}
          </span>
          <div className="flex gap-2">
            <button
              disabled={page === 0}
              onClick={() => setPage((p) => p - 1)}
              className="rounded px-2 py-1 hover:bg-muted disabled:opacity-40"
              data-testid="profile-prev"
            >
              Prev
            </button>
            <button
              disabled={page >= totalPages - 1}
              onClick={() => setPage((p) => p + 1)}
              className="rounded px-2 py-1 hover:bg-muted disabled:opacity-40"
              data-testid="profile-next"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Column Stat Card                                                           */
/* -------------------------------------------------------------------------- */

interface ColumnStatCardProps {
  column: ColumnSummary;
  samples: unknown[];
}

function ColumnStatCard({ column, samples }: ColumnStatCardProps) {
  const isNumeric = ["BIGINT", "INTEGER", "DOUBLE", "FLOAT", "DECIMAL", "HUGEINT", "SMALLINT", "TINYINT"].some(
    (t) => column.column_type?.toUpperCase().includes(t),
  );

  // Build mini-histogram data from quartiles for numeric columns
  const quartileValues = isNumeric
    ? [column.q25, column.q50, column.q75].filter(Boolean).map(Number)
    : [];

  return (
    <div
      data-testid="column-stat-card"
      className="flex flex-col gap-2 rounded-md border bg-background p-3"
    >
      {/* Column header */}
      <div className="flex items-center justify-between">
        <span className="truncate text-sm font-medium text-foreground">
          {column.column_name}
        </span>
        <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground">
          {column.column_type}
        </span>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
        {column.min != null && (
          <StatRow label="Min" value={column.min} />
        )}
        {column.max != null && (
          <StatRow label="Max" value={column.max} />
        )}
        {column.avg != null && (
          <StatRow label="Avg" value={formatNumber(column.avg)} />
        )}
        {column.std != null && (
          <StatRow label="Std" value={formatNumber(column.std)} />
        )}
        {column.null_percentage != null && (
          <StatRow label="Null %" value={column.null_percentage} />
        )}
        {column.approx_unique != null && (
          <StatRow label="Unique" value={String(column.approx_unique)} />
        )}
        {column.q25 != null && (
          <StatRow label="Q25" value={column.q25} />
        )}
        {column.q50 != null && (
          <StatRow label="Q50" value={column.q50} />
        )}
        {column.q75 != null && (
          <StatRow label="Q75" value={column.q75} />
        )}
        {column.count != null && (
          <StatRow label="Count" value={column.count} />
        )}
      </div>

      {/* Mini visualization for numeric columns */}
      {quartileValues.length > 0 && (
        <MiniQuartileBar q25={quartileValues[0]} q50={quartileValues[1]} q75={quartileValues[2]} min={Number(column.min)} max={Number(column.max)} />
      )}

      {/* Sample values */}
      {samples.length > 0 && (
        <div className="border-t pt-2">
          <p className="mb-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
            Samples
          </p>
          <div className="flex flex-wrap gap-1">
            {samples.slice(0, 5).map((val, idx) => (
              <span
                key={idx}
                className="inline-block max-w-[120px] truncate rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground"
                title={String(val)}
              >
                {String(val)}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Mini Quartile Bar (sparkline alternative)                                   */
/* -------------------------------------------------------------------------- */

function MiniQuartileBar({
  q25,
  q50,
  q75,
  min,
  max,
}: {
  q25: number;
  q50: number;
  q75: number;
  min: number;
  max: number;
}) {
  const range = max - min;
  if (range === 0) return null;

  const leftPct = ((q25 - min) / range) * 100;
  const widthPct = ((q75 - q25) / range) * 100;
  const medianPct = ((q50 - min) / range) * 100;

  return (
    <div
      data-testid="quartile-bar"
      className="relative h-2 w-full rounded-full bg-muted"
    >
      {/* IQR range */}
      <div
        className="absolute top-0 h-full rounded-full bg-primary/30"
        style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
      />
      {/* Median marker */}
      <div
        className="absolute top-0 h-full w-0.5 rounded-full bg-primary"
        style={{ left: `${medianPct}%` }}
      />
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Helpers                                                                    */
/* -------------------------------------------------------------------------- */

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <>
      <span className="text-muted-foreground">{label}</span>
      <span className="truncate text-foreground" title={value}>
        {value}
      </span>
    </>
  );
}

function formatNumber(val: string): string {
  const num = Number(val);
  if (Number.isNaN(num)) return val;
  if (Number.isInteger(num)) return String(num);
  return num.toFixed(2);
}
