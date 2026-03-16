import { InlineSqlBlock } from "./inline-sql-block";
import { InlineTablePreview } from "./inline-table-preview";
import { InlineChartBlock } from "./inline-chart-block";
import type { ChartConfig } from "@/components/charts";

interface InlineResultBlockProps {
  metadata: Record<string, unknown>;
}

/**
 * Renders inline result blocks (SQL, table preview, chart) within
 * an assistant message based on the message's metadata.
 *
 * Metadata structure (populated from SSE events):
 * - sql: string — the generated SQL query
 * - query_result: { columns, data, row_count } — query execution results
 * - chart_config: ChartConfig — Plotly chart configuration
 */
export function InlineResultBlock({ metadata }: InlineResultBlockProps) {
  const sql = metadata.sql as string | undefined;
  const queryResult = metadata.query_result as
    | {
        columns?: string[];
        data?: Record<string, unknown>[];
        row_count?: number;
        rows?: unknown[][];
      }
    | undefined;
  let chartConfig = metadata.chart_config as ChartConfig | undefined;

  // Normalize backend's chart_type field to the type field ChartConfig expects
  if (chartConfig && !chartConfig.type && (chartConfig as unknown as Record<string, unknown>).chart_type) {
    chartConfig = {
      ...chartConfig,
      type: (chartConfig as unknown as Record<string, unknown>).chart_type as ChartConfig["type"],
    };
  }

  // Nothing to render
  if (!sql && !queryResult && !chartConfig) return null;

  // Transform row-based data (rows[][]) to record-based data (Record<string, unknown>[])
  // if the backend sends rows instead of data
  let columns: string[] = [];
  let data: Record<string, unknown>[] = [];
  let rowCount = 0;

  if (queryResult) {
    columns = queryResult.columns ?? [];
    rowCount = queryResult.row_count ?? 0;

    if (queryResult.data && Array.isArray(queryResult.data)) {
      data = queryResult.data;
    } else if (queryResult.rows && Array.isArray(queryResult.rows) && columns.length > 0) {
      data = queryResult.rows.map((row: unknown[]) => {
        const record: Record<string, unknown> = {};
        columns.forEach((col, i) => {
          record[col] = (row as unknown[])[i] ?? null;
        });
        return record;
      });
    }
  }

  return (
    <div className="mt-3 space-y-3" data-testid="inline-result-block">
      {sql && <InlineSqlBlock sql={sql} />}

      {columns.length > 0 && data.length > 0 && (
        <InlineTablePreview
          columns={columns}
          data={data}
          rowCount={rowCount || data.length}
        />
      )}

      {chartConfig && <InlineChartBlock chartConfig={chartConfig} />}
    </div>
  );
}
