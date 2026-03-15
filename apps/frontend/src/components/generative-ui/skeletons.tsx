import { cn } from "@/lib/utils";

/**
 * Shimmer animation base class used by all skeleton shapes.
 * Uses Tailwind's animate-pulse for a smooth shimmer effect.
 */
const shimmer = "animate-pulse bg-muted rounded";

/* -------------------------------------------------------------------------- */
/*  Chart Skeleton                                                            */
/* -------------------------------------------------------------------------- */

interface ChartSkeletonProps {
  className?: string;
}

export function ChartSkeleton({ className }: ChartSkeletonProps) {
  return (
    <div
      data-testid="skeleton-chart"
      className={cn("flex flex-col gap-3 p-4", className)}
    >
      {/* Title bar */}
      <div className={cn(shimmer, "h-4 w-1/3")} />

      {/* Chart area with vertical bars to mimic a bar chart shape */}
      <div className="flex items-end gap-2 pt-2" style={{ height: 160 }}>
        <div className={cn(shimmer, "w-1/6")} style={{ height: "60%" }} />
        <div className={cn(shimmer, "w-1/6")} style={{ height: "85%" }} />
        <div className={cn(shimmer, "w-1/6")} style={{ height: "45%" }} />
        <div className={cn(shimmer, "w-1/6")} style={{ height: "70%" }} />
        <div className={cn(shimmer, "w-1/6")} style={{ height: "55%" }} />
        <div className={cn(shimmer, "w-1/6")} style={{ height: "90%" }} />
      </div>

      {/* X-axis labels */}
      <div className="flex gap-2">
        <div className={cn(shimmer, "h-3 w-1/6")} />
        <div className={cn(shimmer, "h-3 w-1/6")} />
        <div className={cn(shimmer, "h-3 w-1/6")} />
        <div className={cn(shimmer, "h-3 w-1/6")} />
        <div className={cn(shimmer, "h-3 w-1/6")} />
        <div className={cn(shimmer, "h-3 w-1/6")} />
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Table Skeleton                                                            */
/* -------------------------------------------------------------------------- */

interface TableSkeletonProps {
  rows?: number;
  columns?: number;
  className?: string;
}

export function TableSkeleton({
  rows = 5,
  columns = 4,
  className,
}: TableSkeletonProps) {
  return (
    <div
      data-testid="skeleton-table"
      className={cn("flex flex-col gap-2 p-4", className)}
    >
      {/* Header row */}
      <div className="flex gap-3">
        {Array.from({ length: columns }, (_, i) => (
          <div key={`header-${i}`} className={cn(shimmer, "h-4 flex-1")} />
        ))}
      </div>

      {/* Separator */}
      <div className={cn(shimmer, "h-px w-full opacity-50")} />

      {/* Data rows */}
      {Array.from({ length: rows }, (_, rowIdx) => (
        <div key={`row-${rowIdx}`} className="flex gap-3">
          {Array.from({ length: columns }, (_, colIdx) => (
            <div
              key={`cell-${rowIdx}-${colIdx}`}
              className={cn(shimmer, "h-3 flex-1")}
              style={{
                // Vary widths slightly for visual realism
                maxWidth: `${60 + ((rowIdx + colIdx) % 3) * 15}%`,
              }}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Profile Skeleton                                                          */
/* -------------------------------------------------------------------------- */

interface ProfileSkeletonProps {
  className?: string;
}

export function ProfileSkeleton({ className }: ProfileSkeletonProps) {
  return (
    <div
      data-testid="skeleton-profile"
      className={cn("flex flex-col gap-4 p-4", className)}
    >
      {/* Dataset title */}
      <div className={cn(shimmer, "h-5 w-2/5")} />

      {/* Summary stats row */}
      <div className="grid grid-cols-3 gap-3">
        <div className="flex flex-col gap-1.5">
          <div className={cn(shimmer, "h-3 w-16")} />
          <div className={cn(shimmer, "h-6 w-20")} />
        </div>
        <div className="flex flex-col gap-1.5">
          <div className={cn(shimmer, "h-3 w-14")} />
          <div className={cn(shimmer, "h-6 w-24")} />
        </div>
        <div className="flex flex-col gap-1.5">
          <div className={cn(shimmer, "h-3 w-18")} />
          <div className={cn(shimmer, "h-6 w-16")} />
        </div>
      </div>

      {/* Column stats list */}
      <div className="flex flex-col gap-2">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={`col-${i}`} className="flex items-center gap-3">
            <div className={cn(shimmer, "h-4 w-24")} />
            <div className={cn(shimmer, "h-4 w-16")} />
            <div className={cn(shimmer, "h-4 flex-1")} />
          </div>
        ))}
      </div>
    </div>
  );
}
