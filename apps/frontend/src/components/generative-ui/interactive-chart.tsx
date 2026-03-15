import { useState, useRef, useCallback, useMemo } from "react";
import Plot from "react-plotly.js";
import type { PlotParams } from "react-plotly.js";
import {
  ChartSkeleton,
  ComponentErrorBoundary,
  ActionToolbar,
} from "@/components/generative-ui";
import { cn } from "@/lib/utils";
import {
  BarChart3,
  LineChart,
  PieChart,
  ScatterChart,
  Activity,
  LayoutGrid,
  AlertTriangle,
} from "lucide-react";
import type { ReactNode } from "react";
import {
  ChartEditor,
  createInitialEditorState,
  applyEditorToPlotly,
} from "./chart-editor";
import type { ChartEditorState } from "./chart-editor";

/* -------------------------------------------------------------------------- */
/*  Types                                                                      */
/* -------------------------------------------------------------------------- */

/** Supported chart types matching the backend's ChartType enum. */
export const CHART_TYPES = [
  "line",
  "bar",
  "pie",
  "scatter",
  "kpi",
  "heatmap",
  "box",
  "area",
  "histogram",
  "dual-axis",
  "treemap",
  "waterfall",
  "funnel",
  "violin",
  "candlestick",
  "sankey",
] as const;

export type ChartTypeName = (typeof CHART_TYPES)[number];

/** The Plotly config shape from the backend's PlotlyConfig.to_dict(). */
export interface PlotlyChartConfig {
  data: Plotly.Data[];
  layout: Partial<Plotly.Layout>;
  chart_type: string;
  is_fallback?: boolean;
}

export interface InteractiveChartProps {
  /** The Plotly chart configuration from the agent. */
  chartConfig: PlotlyChartConfig;
  /** Column names from the query result (for axis assignment). */
  columns: string[];
  /** Row data from the query result (for re-rendering with new chart type). */
  rows: unknown[][];
  /** Title displayed above the chart. */
  title?: string;
  /** AI reasoning for the chart type selection. */
  reasoning?: string;
  /** Whether the chart data is still loading. */
  isLoading?: boolean;
  /** Callback when the pin/bookmark button is clicked. */
  onPin?: () => void;
  /** Whether this chart is already bookmarked. */
  isPinned?: boolean;
  /** Additional CSS classes. */
  className?: string;
}

/* -------------------------------------------------------------------------- */
/*  Chart type metadata                                                        */
/* -------------------------------------------------------------------------- */

interface ChartTypeMeta {
  label: string;
  icon: ReactNode;
  /** Chart types that require at least one x and one y axis column. */
  needsXY: boolean;
  /** Chart types that only need labels + values (no x/y axes). */
  needsLabelsValues: boolean;
}

const CHART_TYPE_META: Record<ChartTypeName, ChartTypeMeta> = {
  line: { label: "Line", icon: <LineChart className="size-4" />, needsXY: true, needsLabelsValues: false },
  bar: { label: "Bar", icon: <BarChart3 className="size-4" />, needsXY: true, needsLabelsValues: false },
  pie: { label: "Pie", icon: <PieChart className="size-4" />, needsXY: false, needsLabelsValues: true },
  scatter: { label: "Scatter", icon: <ScatterChart className="size-4" />, needsXY: true, needsLabelsValues: false },
  kpi: { label: "KPI", icon: <Activity className="size-4" />, needsXY: false, needsLabelsValues: false },
  heatmap: { label: "Heatmap", icon: <LayoutGrid className="size-4" />, needsXY: true, needsLabelsValues: false },
  box: { label: "Box Plot", icon: <BarChart3 className="size-4" />, needsXY: true, needsLabelsValues: false },
  area: { label: "Area", icon: <LineChart className="size-4" />, needsXY: true, needsLabelsValues: false },
  histogram: { label: "Histogram", icon: <BarChart3 className="size-4" />, needsXY: false, needsLabelsValues: false },
  "dual-axis": { label: "Dual Axis", icon: <LineChart className="size-4" />, needsXY: true, needsLabelsValues: false },
  treemap: { label: "Treemap", icon: <LayoutGrid className="size-4" />, needsXY: false, needsLabelsValues: true },
  waterfall: { label: "Waterfall", icon: <BarChart3 className="size-4" />, needsXY: true, needsLabelsValues: false },
  funnel: { label: "Funnel", icon: <BarChart3 className="size-4" />, needsXY: true, needsLabelsValues: false },
  violin: { label: "Violin", icon: <BarChart3 className="size-4" />, needsXY: true, needsLabelsValues: false },
  candlestick: { label: "Candlestick", icon: <BarChart3 className="size-4" />, needsXY: true, needsLabelsValues: false },
  sankey: { label: "Sankey", icon: <LayoutGrid className="size-4" />, needsXY: false, needsLabelsValues: false },
};

/* -------------------------------------------------------------------------- */
/*  Client-side chart builder                                                  */
/* -------------------------------------------------------------------------- */

/**
 * Build a Plotly trace configuration for a given chart type from raw data.
 * This runs entirely client-side -- no AI call is made.
 */
function buildTraces(
  chartType: ChartTypeName,
  columns: string[],
  rows: unknown[][],
  xColumn: string,
  yColumn: string,
): { data: Plotly.Data[]; layout: Partial<Plotly.Layout> } {
  const xIdx = columns.indexOf(xColumn);
  const yIdx = columns.indexOf(yColumn);

  const xValues = rows.map((r) => (xIdx >= 0 && xIdx < r.length ? r[xIdx] : null));
  const yValues = rows.map((r) => (yIdx >= 0 && yIdx < r.length ? r[yIdx] : null));

  const baseLayout: Partial<Plotly.Layout> = {
    autosize: true,
    margin: { l: 60, r: 30, t: 50, b: 60 },
    font: { family: "Inter, system-ui, sans-serif", size: 12 },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    hovermode: "closest" as const,
  };

  switch (chartType) {
    case "line":
      return {
        data: [{
          type: "scatter",
          mode: "lines+markers",
          x: xValues as Plotly.Datum[],
          y: yValues as Plotly.Datum[],
          name: yColumn,
        }],
        layout: { ...baseLayout, xaxis: { title: { text: xColumn } }, yaxis: { title: { text: yColumn } } },
      };

    case "bar":
      return {
        data: [{
          type: "bar",
          x: xValues as Plotly.Datum[],
          y: yValues as Plotly.Datum[],
          name: yColumn,
        }],
        layout: { ...baseLayout, xaxis: { title: { text: xColumn } }, yaxis: { title: { text: yColumn } } },
      };

    case "pie":
      return {
        data: [{
          type: "pie",
          labels: xValues as Plotly.Datum[],
          values: yValues as Plotly.Datum[],
          hole: 0.3,
        }],
        layout: baseLayout,
      };

    case "scatter":
      return {
        data: [{
          type: "scatter",
          mode: "markers",
          x: xValues as Plotly.Datum[],
          y: yValues as Plotly.Datum[],
          name: `${yColumn} vs ${xColumn}`,
          marker: { size: 8, opacity: 0.7 },
        }],
        layout: { ...baseLayout, xaxis: { title: { text: xColumn } }, yaxis: { title: { text: yColumn } } },
      };

    case "area":
      return {
        data: [{
          type: "scatter",
          mode: "lines",
          fill: "tozeroy",
          x: xValues as Plotly.Datum[],
          y: yValues as Plotly.Datum[],
          name: yColumn,
        }],
        layout: { ...baseLayout, xaxis: { title: { text: xColumn } }, yaxis: { title: { text: yColumn } } },
      };

    case "histogram":
      return {
        data: [{
          type: "histogram",
          x: xValues as Plotly.Datum[],
          name: xColumn,
        }],
        layout: { ...baseLayout, xaxis: { title: { text: xColumn } }, yaxis: { title: { text: "Count" } } },
      };

    case "box":
      return {
        data: [{
          type: "box",
          y: yValues as Plotly.Datum[],
          x: xValues as Plotly.Datum[],
          name: yColumn,
        }],
        layout: { ...baseLayout, xaxis: { title: { text: xColumn } }, yaxis: { title: { text: yColumn } } },
      };

    case "heatmap": {
      // Use WebGL-backed heatmapgl for large datasets (10k+ rows)
      const traceType = rows.length > 10_000 ? "heatmapgl" : "heatmap";
      return {
        data: [{
          type: traceType as Plotly.PlotType,
          x: xValues as Plotly.Datum[],
          y: yValues as Plotly.Datum[],
          z: rows.map((r) => r.map(Number)),
          colorscale: "Viridis",
        }],
        layout: { ...baseLayout, xaxis: { title: { text: xColumn } }, yaxis: { title: { text: yColumn } } },
      };
    }

    case "dual-axis": {
      // Find a second numeric column for the second y-axis
      const secondYIdx = columns.findIndex((c, i) => i !== xIdx && i !== yIdx);
      const y2Values = secondYIdx >= 0
        ? rows.map((r) => (secondYIdx < r.length ? r[secondYIdx] : null))
        : yValues;
      const y2Column = secondYIdx >= 0 ? columns[secondYIdx] : yColumn;

      return {
        data: [
          {
            type: "scatter",
            mode: "lines+markers",
            x: xValues as Plotly.Datum[],
            y: yValues as Plotly.Datum[],
            name: yColumn,
            yaxis: "y",
          },
          {
            type: "scatter",
            mode: "lines+markers",
            x: xValues as Plotly.Datum[],
            y: y2Values as Plotly.Datum[],
            name: y2Column,
            yaxis: "y2",
          },
        ],
        layout: {
          ...baseLayout,
          xaxis: { title: { text: xColumn } },
          yaxis: { title: { text: yColumn }, side: "left" },
          yaxis2: { title: { text: y2Column }, side: "right", overlaying: "y" },
        },
      };
    }

    case "treemap":
      return {
        data: [{
          type: "treemap",
          labels: xValues as Plotly.Datum[],
          parents: xValues.map(() => ""),
          values: yValues as Plotly.Datum[],
        }],
        layout: baseLayout,
      };

    case "waterfall":
      return {
        data: [{
          type: "waterfall",
          x: xValues as Plotly.Datum[],
          y: yValues as Plotly.Datum[],
          name: yColumn,
        }],
        layout: { ...baseLayout, xaxis: { title: { text: xColumn } }, yaxis: { title: { text: yColumn } } },
      };

    case "funnel":
      return {
        data: [{
          type: "funnel",
          x: yValues as Plotly.Datum[],
          y: xValues as Plotly.Datum[],
          name: yColumn,
        }],
        layout: baseLayout,
      };

    case "violin":
      return {
        data: [{
          type: "violin",
          y: yValues as Plotly.Datum[],
          x: xValues as Plotly.Datum[],
          name: yColumn,
          box: { visible: true },
          meanline: { visible: true },
        }],
        layout: { ...baseLayout, xaxis: { title: { text: xColumn } }, yaxis: { title: { text: yColumn } } },
      };

    case "candlestick": {
      // Candlestick needs open/high/low/close. Map first 4 numeric columns.
      const getCol = (idx: number) =>
        rows.map((r) => (idx < r.length ? r[idx] : null));
      const numericCols = columns
        .map((c, i) => ({ name: c, idx: i }))
        .filter((c) => c.idx !== xIdx)
        .slice(0, 4);

      if (numericCols.length >= 4) {
        return {
          data: [{
            type: "candlestick",
            x: xValues as Plotly.Datum[],
            open: getCol(numericCols[0].idx) as Plotly.Datum[],
            high: getCol(numericCols[1].idx) as Plotly.Datum[],
            low: getCol(numericCols[2].idx) as Plotly.Datum[],
            close: getCol(numericCols[3].idx) as Plotly.Datum[],
          }],
          layout: { ...baseLayout, xaxis: { title: { text: xColumn } } },
        };
      }
      // Fallback: treat as bar if not enough columns
      return {
        data: [{
          type: "bar",
          x: xValues as Plotly.Datum[],
          y: yValues as Plotly.Datum[],
          name: yColumn,
        }],
        layout: { ...baseLayout, xaxis: { title: { text: xColumn } }, yaxis: { title: { text: yColumn } } },
      };
    }

    case "sankey": {
      // Sankey needs source, target, value. Use first 3 columns.
      const srcIdx = 0;
      const tgtIdx = Math.min(1, columns.length - 1);
      const valIdx = Math.min(2, columns.length - 1);

      const sources = rows.map((r) => (srcIdx < r.length ? r[srcIdx] : null));
      const targets = rows.map((r) => (tgtIdx < r.length ? r[tgtIdx] : null));
      const values = rows.map((r) => (valIdx < r.length ? Number(r[valIdx]) : 0));

      // Build unique label list
      const labels = [...new Set([...sources, ...targets].filter(Boolean).map(String))];
      const labelIdx = (val: unknown) => labels.indexOf(String(val));

      return {
        data: [{
          type: "sankey",
          node: { label: labels },
          link: {
            source: sources.map(labelIdx),
            target: targets.map(labelIdx),
            value: values,
          },
        }],
        layout: baseLayout,
      };
    }

    case "kpi": {
      const value = rows[0]?.[yIdx >= 0 ? yIdx : 0];
      return {
        data: [{
          type: "indicator",
          mode: "number",
          value: Number(value),
          title: { text: yColumn },
          number: { font: { size: 48 } },
        }],
        layout: baseLayout,
      };
    }

    default:
      return { data: [], layout: baseLayout };
  }
}

/* -------------------------------------------------------------------------- */
/*  Compatibility checking                                                     */
/* -------------------------------------------------------------------------- */

/** Check if switching to a chart type is compatible with the current data. */
function checkCompatibility(
  chartType: ChartTypeName,
  columns: string[],
  rows: unknown[][],
): { compatible: boolean; warning?: string } {
  const meta = CHART_TYPE_META[chartType];

  if (chartType === "candlestick") {
    const numericCount = columns.length - 1; // Assuming first column is x-axis
    if (numericCount < 4) {
      return {
        compatible: false,
        warning: "Candlestick charts require at least 4 numeric columns (open, high, low, close).",
      };
    }
  }

  if (chartType === "sankey" && columns.length < 3) {
    return {
      compatible: false,
      warning: "Sankey diagrams require at least 3 columns (source, target, value).",
    };
  }

  if (meta.needsXY && columns.length < 2) {
    return {
      compatible: false,
      warning: `${meta.label} charts require at least 2 columns.`,
    };
  }

  if (chartType === "kpi" && rows.length !== 1) {
    return {
      compatible: true,
      warning: "KPI cards work best with single-row results. Only the first row will be shown.",
    };
  }

  if (chartType === "pie" && rows.length > 20) {
    return {
      compatible: true,
      warning: "Pie charts may be hard to read with many categories. Consider using a bar chart.",
    };
  }

  return { compatible: true };
}

/* -------------------------------------------------------------------------- */
/*  Export helpers                                                              */
/* -------------------------------------------------------------------------- */

function exportChart(plotRef: HTMLDivElement | null, format: "png" | "svg") {
  if (!plotRef) return;

  // Access Plotly via the global that react-plotly.js sets up
  const Plotly = (window as unknown as { Plotly?: typeof import("plotly.js") }).Plotly;
  if (!Plotly) {
    // Fallback: find the plotly instance from the Plot component's div
    const gd = plotRef.querySelector(".js-plotly-plot") as HTMLDivElement | null;
    if (gd && typeof (gd as unknown as { _fullLayout?: unknown })._fullLayout !== "undefined") {
      import("plotly.js").then((mod) => {
        mod.default.downloadImage(gd, {
          format,
          filename: `chart-export-${Date.now()}`,
          width: 1200,
          height: 700,
        });
      });
    }
    return;
  }

  const gd = plotRef.querySelector(".js-plotly-plot") as HTMLDivElement | null;
  if (gd) {
    (Plotly as unknown as typeof import("plotly.js").default).downloadImage(gd, {
      format,
      filename: `chart-export-${Date.now()}`,
      width: 1200,
      height: 700,
    });
  }
}

/* -------------------------------------------------------------------------- */
/*  InteractiveChart Component                                                 */
/* -------------------------------------------------------------------------- */

export function InteractiveChart({
  chartConfig,
  columns,
  rows,
  title,
  reasoning,
  isLoading,
  onPin,
  isPinned,
  className,
}: InteractiveChartProps) {
  return (
    <ComponentErrorBoundary componentName="InteractiveChart">
      <InteractiveChartInner
        chartConfig={chartConfig}
        columns={columns}
        rows={rows}
        title={title}
        reasoning={reasoning}
        isLoading={isLoading}
        onPin={onPin}
        isPinned={isPinned}
        className={className}
      />
    </ComponentErrorBoundary>
  );
}

function InteractiveChartInner({
  chartConfig,
  columns,
  rows,
  title,
  reasoning,
  isLoading,
  onPin,
  isPinned,
  className,
}: InteractiveChartProps) {
  const plotContainerRef = useRef<HTMLDivElement>(null);
  const [showExportMenu, setShowExportMenu] = useState(false);
  const [showEditor, setShowEditor] = useState(false);
  const [warning, setWarning] = useState<string | null>(null);

  // Derive initial chart type from the config
  const initialChartType = (chartConfig.chart_type || "bar") as ChartTypeName;

  // Full editor state
  const [editorState, setEditorState] = useState<ChartEditorState>(() =>
    createInitialEditorState(initialChartType, columns),
  );

  // Track whether user has customized (to know whether to use original or rebuilt config)
  const [isCustomized, setIsCustomized] = useState(false);

  // Check for zero/negative values in numeric data
  const hasZeroOrNegativeValues = useMemo(() => {
    for (const row of rows) {
      for (const val of row) {
        const num = Number(val);
        if (!isNaN(num) && num <= 0) return true;
      }
    }
    return false;
  }, [rows]);

  // Build the active chart data -- either original config or client-rebuilt
  const activeConfig = useMemo<PlotlyChartConfig>(() => {
    if (!isCustomized) {
      return chartConfig;
    }
    const { data, layout } = buildTraces(
      editorState.chartType,
      columns,
      rows,
      editorState.xColumn,
      editorState.yColumn,
    );
    return {
      data,
      layout: {
        ...chartConfig.layout,
        ...layout,
        title: chartConfig.layout.title,
      },
      chart_type: editorState.chartType,
    };
  }, [isCustomized, editorState.chartType, columns, rows, editorState.xColumn, editorState.yColumn, chartConfig]);

  // Apply editor customizations (colors, labels, scale, annotations) to the active config
  const finalConfig = useMemo(() => {
    if (!showEditor && !isCustomized) {
      return { data: activeConfig.data, layout: { ...activeConfig.layout, autosize: true } };
    }
    const { data, layout } = applyEditorToPlotly(
      activeConfig.data,
      activeConfig.layout,
      editorState,
    );
    return { data, layout: { ...layout, autosize: true } };
  }, [activeConfig, editorState, showEditor, isCustomized]);

  // Trace names for the editor
  const traceNames = useMemo(
    () => finalConfig.data.map((t, i) => (t as { name?: string }).name ?? `Series ${i + 1}`),
    [finalConfig.data],
  );

  const handleEditorChange = useCallback(
    (newState: ChartEditorState) => {
      // Check chart type compatibility before applying
      if (newState.chartType !== editorState.chartType) {
        const { compatible, warning: warn } = checkCompatibility(newState.chartType, columns, rows);
        setWarning(warn ?? null);
        if (!compatible) return;
      }
      setEditorState(newState);
      setIsCustomized(true);
    },
    [editorState.chartType, columns, rows],
  );

  const handleExport = useCallback(
    (format: "png" | "svg") => {
      exportChart(plotContainerRef.current, format);
      setShowExportMenu(false);
    },
    [],
  );

  if (isLoading) {
    return <ChartSkeleton className={className} />;
  }

  const plotConfig: Partial<PlotParams["config"]> = {
    responsive: true,
    displayModeBar: true,
    displaylogo: false,
    modeBarButtonsToRemove: ["sendDataToCloud", "lasso2d", "select2d"] as Plotly.ModeBarDefaultButtons[],
  };

  return (
    <div
      data-testid="interactive-chart"
      className={cn(
        "flex flex-col gap-3 rounded-lg border bg-card p-4 shadow-sm",
        className,
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="min-w-0 flex-1">
          {title && (
            <h3 className="truncate text-sm font-semibold text-foreground">
              {title}
            </h3>
          )}
          {reasoning && (
            <p className="truncate text-xs text-muted-foreground">{reasoning}</p>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button
            data-testid="chart-editor-toggle"
            onClick={() => setShowEditor((prev) => !prev)}
            className={cn(
              "rounded-md px-2 py-1 text-xs font-medium transition-colors",
              showEditor
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
          >
            Edit
          </button>
          <div className="relative">
            <ActionToolbar
              onExport={() => setShowExportMenu((prev) => !prev)}
              onPin={onPin}
              isPinned={isPinned}
            />
            {showExportMenu && (
              <div
                data-testid="export-menu"
                className="absolute right-0 top-full z-50 mt-1 min-w-[120px] rounded-md border bg-popover p-1 shadow-md"
              >
                <button
                  data-testid="export-png"
                  onClick={() => handleExport("png")}
                  className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm text-popover-foreground hover:bg-accent"
                >
                  Export PNG
                </button>
                <button
                  data-testid="export-svg"
                  onClick={() => handleExport("svg")}
                  className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm text-popover-foreground hover:bg-accent"
                >
                  Export SVG
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Warning banner */}
      {warning && (
        <div
          data-testid="chart-warning"
          className="flex items-center gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200"
        >
          <AlertTriangle className="size-3.5 shrink-0" />
          {warning}
        </div>
      )}

      {/* Full chart editor panel */}
      {showEditor && (
        <div data-testid="chart-editor">
          <ChartEditor
            columns={columns}
            state={editorState}
            traceCount={finalConfig.data.length}
            traceNames={traceNames}
            hasZeroOrNegativeValues={hasZeroOrNegativeValues}
            onChange={handleEditorChange}
          />
        </div>
      )}

      {/* Plotly chart */}
      <div ref={plotContainerRef} data-testid="chart-container" className="w-full">
        <Plot
          data={finalConfig.data}
          layout={finalConfig.layout}
          config={plotConfig}
          useResizeHandler
          className="w-full"
          style={{ width: "100%", minHeight: 350 }}
        />
      </div>
    </div>
  );
}
