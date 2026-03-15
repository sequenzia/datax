import { cn } from "@/lib/utils";
import { InteractiveChart } from "./interactive-chart";
import type { InteractiveChartProps } from "./interactive-chart";
import { X, LayoutGrid } from "lucide-react";

/* -------------------------------------------------------------------------- */
/*  Types                                                                      */
/* -------------------------------------------------------------------------- */

export interface MultiChartGridProps {
  /** Array of chart configurations to render side by side. */
  charts: InteractiveChartProps[];
  /** Number of columns in the grid (default 2). */
  gridColumns?: 1 | 2 | 3 | 4;
  /** Called when a chart is removed from the grid. */
  onRemoveChart?: (index: number) => void;
  /** Additional CSS classes. */
  className?: string;
}

/* -------------------------------------------------------------------------- */
/*  MultiChartGrid Component                                                   */
/* -------------------------------------------------------------------------- */

/**
 * Arranges multiple InteractiveChart components side by side in a
 * responsive flex/grid container. Each chart is fully independent
 * with its own editor state, chart type, and data.
 */
export function MultiChartGrid({
  charts,
  gridColumns = 2,
  onRemoveChart,
  className,
}: MultiChartGridProps) {
  if (charts.length === 0) {
    return (
      <div
        data-testid="multi-chart-empty"
        className="flex items-center justify-center rounded-lg border border-dashed bg-muted/30 p-8 text-sm text-muted-foreground"
      >
        <LayoutGrid className="mr-2 size-4" />
        No charts to display
      </div>
    );
  }

  const gridClass =
    gridColumns === 1
      ? "grid-cols-1"
      : gridColumns === 3
        ? "grid-cols-1 md:grid-cols-2 xl:grid-cols-3"
        : gridColumns === 4
          ? "grid-cols-1 md:grid-cols-2 xl:grid-cols-4"
          : "grid-cols-1 md:grid-cols-2";

  return (
    <div
      data-testid="multi-chart-grid"
      className={cn("grid gap-4", gridClass, className)}
    >
      {charts.map((chartProps, index) => (
        <div
          key={index}
          data-testid={`multi-chart-item-${index}`}
          className="relative min-w-0"
        >
          {onRemoveChart && (
            <button
              type="button"
              onClick={() => onRemoveChart(index)}
              data-testid={`remove-chart-${index}`}
              className="absolute right-2 top-2 z-10 rounded-full bg-background/80 p-1 text-muted-foreground shadow-sm hover:bg-destructive hover:text-destructive-foreground transition-colors"
              aria-label={`Remove chart ${index + 1}`}
            >
              <X className="size-3.5" />
            </button>
          )}
          <InteractiveChart {...chartProps} />
        </div>
      ))}
    </div>
  );
}
