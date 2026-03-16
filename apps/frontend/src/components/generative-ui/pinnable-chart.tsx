import { useState } from "react";
import { InteractiveChart } from "./interactive-chart";
import { PinToDashboardDialog } from "./pin-to-dashboard-dialog";
import type { PlotlyChartConfig } from "./interactive-chart";

export interface PinnableChartProps {
  chartConfig: PlotlyChartConfig;
  columns: string[];
  rows: unknown[][];
  title?: string;
  reasoning?: string;
  isLoading?: boolean;
  sql?: string;
  sourceId?: string;
  sourceType?: string;
  className?: string;
}

export function PinnableChart({
  chartConfig,
  columns,
  rows,
  title,
  reasoning,
  isLoading,
  sql,
  sourceId,
  sourceType,
  className,
}: PinnableChartProps) {
  const [pinDialogOpen, setPinDialogOpen] = useState(false);

  return (
    <>
      <InteractiveChart
        chartConfig={chartConfig}
        columns={columns}
        rows={rows}
        title={title}
        reasoning={reasoning}
        isLoading={isLoading}
        onPin={() => setPinDialogOpen(true)}
        className={className}
      />
      <PinToDashboardDialog
        open={pinDialogOpen}
        onOpenChange={setPinDialogOpen}
        bookmarkData={{
          title: title ?? chartConfig.layout?.title?.toString(),
          sql,
          chart_config: chartConfig as unknown as Record<string, unknown>,
          result_snapshot: { columns, rows: rows.slice(0, 50), row_count: rows.length },
          source_id: sourceId,
          source_type: sourceType,
        }}
      />
    </>
  );
}
