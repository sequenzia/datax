import { useState, useCallback, useMemo } from "react";
import { cn } from "@/lib/utils";
import { useBreakpoint } from "@/hooks/use-breakpoint";
import {
  Palette,
  Type,
  TrendingUp,
  Minus,
  Eye,
  EyeOff,
  Plus,
  X,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import type { ChartTypeName } from "./interactive-chart";
import { CHART_TYPES } from "./interactive-chart";

/* -------------------------------------------------------------------------- */
/*  Types                                                                      */
/* -------------------------------------------------------------------------- */

export interface ChartEditorState {
  /** Active chart type */
  chartType: ChartTypeName;
  /** X-axis column name */
  xColumn: string;
  /** Y-axis column name */
  yColumn: string;
  /** Custom title (undefined = use original) */
  customTitle?: string;
  /** Custom X-axis label */
  customXLabel?: string;
  /** Custom Y-axis label */
  customYLabel?: string;
  /** Custom legend labels per trace index */
  legendLabels: Record<number, string>;
  /** Active color palette name */
  paletteName: string;
  /** Custom per-series colors (trace index -> color) */
  seriesColors: Record<number, string>;
  /** Axis scale types */
  xScale: "linear" | "log";
  yScale: "linear" | "log";
  /** Reference lines */
  referenceLines: ReferenceLine[];
  /** Text annotations */
  annotations: TextAnnotation[];
  /** Hidden series indices */
  hiddenSeries: Set<number>;
}

export interface ReferenceLine {
  id: string;
  axis: "x" | "y";
  value: number;
  label?: string;
  color: string;
}

export interface TextAnnotation {
  id: string;
  text: string;
  x: number;
  y: number;
}

export interface ChartEditorProps {
  /** Column names for axis selectors */
  columns: string[];
  /** Current editor state */
  state: ChartEditorState;
  /** Number of data traces in the chart */
  traceCount: number;
  /** Trace names for series toggle */
  traceNames: string[];
  /** Whether the chart has data with zero/negative values (for log scale warning) */
  hasZeroOrNegativeValues: boolean;
  /** Called when any editor state changes */
  onChange: (state: ChartEditorState) => void;
  /** Additional CSS classes */
  className?: string;
}

/* -------------------------------------------------------------------------- */
/*  Color palettes                                                             */
/* -------------------------------------------------------------------------- */

export const COLOR_PALETTES: Record<string, { name: string; colors: string[] }> = {
  default: {
    name: "Default",
    colors: ["#636EFA", "#EF553B", "#00CC96", "#AB63FA", "#FFA15A", "#19D3F3", "#FF6692", "#B6E880"],
  },
  vivid: {
    name: "Vivid",
    colors: ["#E45756", "#4C78A8", "#54A24B", "#EECA3B", "#B279A2", "#FF9DA6", "#9D755D", "#BAB0AC"],
  },
  pastel: {
    name: "Pastel",
    colors: ["#A1C9F4", "#FFB482", "#8DE5A1", "#FF9F9B", "#D0BBFF", "#DEBB9B", "#FAB0E4", "#CFCFCF"],
  },
  ocean: {
    name: "Ocean",
    colors: ["#023E8A", "#0077B6", "#0096C7", "#00B4D8", "#48CAE4", "#90E0EF", "#ADE8F4", "#CAF0F8"],
  },
  sunset: {
    name: "Sunset",
    colors: ["#FF006E", "#FB5607", "#FF8900", "#FFBE0B", "#FFE66D", "#F72585", "#B5179E", "#7209B7"],
  },
  earth: {
    name: "Earth",
    colors: ["#606C38", "#283618", "#DDA15E", "#BC6C25", "#FEFAE0", "#6B705C", "#A5A58D", "#B7B7A4"],
  },
  monochrome: {
    name: "Monochrome",
    colors: ["#1a1a2e", "#3d3d6b", "#5f5fa8", "#8181c5", "#a3a3d2", "#c5c5df", "#d7d7e9", "#e9e9f3"],
  },
};

export const PALETTE_NAMES = Object.keys(COLOR_PALETTES);

/* -------------------------------------------------------------------------- */
/*  Initial state factory                                                      */
/* -------------------------------------------------------------------------- */

export function createInitialEditorState(
  chartType: ChartTypeName,
  columns: string[],
): ChartEditorState {
  return {
    chartType,
    xColumn: columns[0] ?? "",
    yColumn: columns[1] ?? columns[0] ?? "",
    legendLabels: {},
    paletteName: "default",
    seriesColors: {},
    xScale: "linear",
    yScale: "linear",
    referenceLines: [],
    annotations: [],
    hiddenSeries: new Set(),
  };
}

/* -------------------------------------------------------------------------- */
/*  Apply editor state to Plotly config                                        */
/* -------------------------------------------------------------------------- */

export function applyEditorToPlotly(
  data: Plotly.Data[],
  layout: Partial<Plotly.Layout>,
  state: ChartEditorState,
): { data: Plotly.Data[]; layout: Partial<Plotly.Layout> } {
  // Apply colors
  const palette = COLOR_PALETTES[state.paletteName] ?? COLOR_PALETTES.default;
  const coloredData = data.map((trace, i) => {
    const color = state.seriesColors[i] ?? palette.colors[i % palette.colors.length];
    const visible = !state.hiddenSeries.has(i);
    const name = state.legendLabels[i] ?? (trace as { name?: string }).name;

    return {
      ...trace,
      marker: { ...((trace as { marker?: object }).marker ?? {}), color },
      line: { ...((trace as { line?: object }).line ?? {}), color },
      visible: visible ? true : "legendonly",
      ...(name !== undefined ? { name } : {}),
    } as Plotly.Data;
  });

  // Apply layout modifications
  const modifiedLayout: Partial<Plotly.Layout> = { ...layout };

  // Custom title
  if (state.customTitle !== undefined) {
    modifiedLayout.title = { text: state.customTitle };
  }

  // Custom axis labels
  if (state.customXLabel !== undefined) {
    modifiedLayout.xaxis = {
      ...(modifiedLayout.xaxis ?? {}),
      title: { text: state.customXLabel },
    };
  }
  if (state.customYLabel !== undefined) {
    modifiedLayout.yaxis = {
      ...(modifiedLayout.yaxis ?? {}),
      title: { text: state.customYLabel },
    };
  }

  // Axis scale
  modifiedLayout.xaxis = {
    ...(modifiedLayout.xaxis ?? {}),
    type: state.xScale,
  };
  modifiedLayout.yaxis = {
    ...(modifiedLayout.yaxis ?? {}),
    type: state.yScale,
  };

  // Reference lines via shapes
  const shapes: Partial<Plotly.Shape>[] = state.referenceLines.map((rl) => {
    if (rl.axis === "x") {
      return {
        type: "line" as const,
        x0: rl.value,
        x1: rl.value,
        y0: 0,
        y1: 1,
        yref: "paper" as const,
        line: { color: rl.color, width: 2, dash: "dash" as const },
      };
    }
    return {
      type: "line" as const,
      x0: 0,
      x1: 1,
      xref: "paper" as const,
      y0: rl.value,
      y1: rl.value,
      line: { color: rl.color, width: 2, dash: "dash" as const },
    };
  });

  if (shapes.length > 0) {
    modifiedLayout.shapes = shapes as Plotly.Layout["shapes"];
  }

  // Text annotations
  const plotlyAnnotations: Partial<Plotly.Annotations>[] = state.annotations.map((a) => ({
    text: a.text,
    x: a.x,
    y: a.y,
    showarrow: true,
    arrowhead: 2,
    ax: 0,
    ay: -30,
    font: { size: 12 },
  }));

  if (plotlyAnnotations.length > 0) {
    modifiedLayout.annotations = plotlyAnnotations as Plotly.Layout["annotations"];
  }

  return { data: coloredData, layout: modifiedLayout };
}

/* -------------------------------------------------------------------------- */
/*  Editor sub-sections                                                        */
/* -------------------------------------------------------------------------- */

interface SectionProps {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  defaultOpen?: boolean;
}

function EditorSection({ title, icon, children, defaultOpen = false }: SectionProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="border-b border-border last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen((p) => !p)}
        className="flex w-full items-center gap-2 px-3 py-2 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
        data-testid={`section-toggle-${title.toLowerCase().replace(/\s/g, "-")}`}
      >
        {icon}
        <span className="flex-1 text-left">{title}</span>
        {open ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />}
      </button>
      {open && <div className="px-3 pb-3 pt-1">{children}</div>}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  ChartEditor Component                                                      */
/* -------------------------------------------------------------------------- */

export function ChartEditor({
  columns,
  state,
  traceCount,
  traceNames,
  hasZeroOrNegativeValues,
  onChange,
  className,
}: ChartEditorProps) {
  const breakpoint = useBreakpoint();
  const isMobile = breakpoint === "mobile";

  const [logScaleWarning, setLogScaleWarning] = useState<string | null>(null);

  const update = useCallback(
    (partial: Partial<ChartEditorState>) => {
      onChange({ ...state, ...partial });
    },
    [state, onChange],
  );

  const handleScaleChange = useCallback(
    (axis: "x" | "y", scale: "linear" | "log") => {
      if (scale === "log" && hasZeroOrNegativeValues) {
        setLogScaleWarning(
          `Data contains zero or negative values. Logarithmic scale cannot display these — falling back to linear.`,
        );
        return;
      }
      setLogScaleWarning(null);
      if (axis === "x") {
        update({ xScale: scale });
      } else {
        update({ yScale: scale });
      }
    },
    [hasZeroOrNegativeValues, update],
  );

  const addReferenceLine = useCallback(
    (axis: "x" | "y") => {
      const newLine: ReferenceLine = {
        id: `ref-${Date.now()}`,
        axis,
        value: 0,
        color: "#FF0000",
      };
      update({ referenceLines: [...state.referenceLines, newLine] });
    },
    [state.referenceLines, update],
  );

  const removeReferenceLine = useCallback(
    (id: string) => {
      update({
        referenceLines: state.referenceLines.filter((rl) => rl.id !== id),
      });
    },
    [state.referenceLines, update],
  );

  const updateReferenceLine = useCallback(
    (id: string, updates: Partial<ReferenceLine>) => {
      update({
        referenceLines: state.referenceLines.map((rl) =>
          rl.id === id ? { ...rl, ...updates } : rl,
        ),
      });
    },
    [state.referenceLines, update],
  );

  const addAnnotation = useCallback(() => {
    const newAnnotation: TextAnnotation = {
      id: `ann-${Date.now()}`,
      text: "Label",
      x: 0,
      y: 0,
    };
    update({ annotations: [...state.annotations, newAnnotation] });
  }, [state.annotations, update]);

  const removeAnnotation = useCallback(
    (id: string) => {
      update({
        annotations: state.annotations.filter((a) => a.id !== id),
      });
    },
    [state.annotations, update],
  );

  const updateAnnotation = useCallback(
    (id: string, updates: Partial<TextAnnotation>) => {
      update({
        annotations: state.annotations.map((a) =>
          a.id === id ? { ...a, ...updates } : a,
        ),
      });
    },
    [state.annotations, update],
  );

  const toggleSeries = useCallback(
    (index: number) => {
      const newHidden = new Set(state.hiddenSeries);
      if (newHidden.has(index)) {
        newHidden.delete(index);
      } else {
        newHidden.add(index);
      }
      update({ hiddenSeries: newHidden });
    },
    [state.hiddenSeries, update],
  );

  const containerClass = isMobile
    ? "fixed inset-x-0 bottom-0 z-50 max-h-[60vh] overflow-y-auto rounded-t-xl border-t bg-card shadow-lg"
    : "flex flex-col rounded-md border bg-muted/50";

  return (
    <div
      data-testid="chart-editor-panel"
      className={cn(containerClass, className)}
    >
      {/* Mobile drag handle */}
      {isMobile && (
        <div className="sticky top-0 flex justify-center bg-card pb-1 pt-2">
          <div className="h-1 w-8 rounded-full bg-muted-foreground/30" />
        </div>
      )}

      {/* Chart Type & Axes (always open) */}
      <EditorSection
        title="Chart Type"
        icon={<TrendingUp className="size-3.5" />}
        defaultOpen
      >
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              Type
            </label>
            <select
              data-testid="chart-type-selector"
              value={state.chartType}
              onChange={(e) => update({ chartType: e.target.value as ChartTypeName })}
              className="rounded-md border bg-background px-2 py-1.5 text-sm text-foreground"
            >
              {CHART_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type.charAt(0).toUpperCase() + type.slice(1).replace("-", " ")}
                </option>
              ))}
            </select>
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              X Axis
            </label>
            <select
              data-testid="x-axis-selector"
              value={state.xColumn}
              onChange={(e) => update({ xColumn: e.target.value })}
              className="rounded-md border bg-background px-2 py-1.5 text-sm text-foreground"
            >
              {columns.map((col) => (
                <option key={col} value={col}>{col}</option>
              ))}
            </select>
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              Y Axis
            </label>
            <select
              data-testid="y-axis-selector"
              value={state.yColumn}
              onChange={(e) => update({ yColumn: e.target.value })}
              className="rounded-md border bg-background px-2 py-1.5 text-sm text-foreground"
            >
              {columns.map((col) => (
                <option key={col} value={col}>{col}</option>
              ))}
            </select>
          </div>
        </div>
      </EditorSection>

      {/* Colors */}
      <EditorSection
        title="Colors"
        icon={<Palette className="size-3.5" />}
      >
        <div className="flex flex-col gap-3">
          {/* Palette selector */}
          <div className="flex flex-col gap-1.5">
            <label className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              Palette
            </label>
            <div className="flex flex-wrap gap-1.5" data-testid="palette-selector">
              {PALETTE_NAMES.map((key) => {
                const p = COLOR_PALETTES[key];
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => update({ paletteName: key, seriesColors: {} })}
                    data-testid={`palette-${key}`}
                    className={cn(
                      "flex items-center gap-1 rounded-md border px-2 py-1 text-[10px] transition-colors",
                      state.paletteName === key
                        ? "border-primary bg-primary/10 text-primary"
                        : "border-border text-muted-foreground hover:border-foreground/30",
                    )}
                  >
                    <div className="flex gap-0.5">
                      {p.colors.slice(0, 4).map((c, i) => (
                        <div
                          key={i}
                          className="size-2.5 rounded-full"
                          style={{ backgroundColor: c }}
                        />
                      ))}
                    </div>
                    <span>{p.name}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Individual series color pickers */}
          {traceCount > 0 && (
            <div className="flex flex-col gap-1.5">
              <label className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                Series Colors
              </label>
              <div className="flex flex-wrap gap-2" data-testid="series-color-pickers">
                {Array.from({ length: traceCount }, (_, i) => {
                  const palette = COLOR_PALETTES[state.paletteName] ?? COLOR_PALETTES.default;
                  const currentColor = state.seriesColors[i] ?? palette.colors[i % palette.colors.length];
                  return (
                    <div key={i} className="flex items-center gap-1.5">
                      <input
                        type="color"
                        value={currentColor}
                        onChange={(e) =>
                          update({
                            seriesColors: { ...state.seriesColors, [i]: e.target.value },
                          })
                        }
                        data-testid={`series-color-${i}`}
                        className="size-6 cursor-pointer rounded border-0 bg-transparent p-0"
                        title={traceNames[i] ?? `Series ${i + 1}`}
                      />
                      <span className="text-[10px] text-muted-foreground">
                        {traceNames[i] ?? `Series ${i + 1}`}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </EditorSection>

      {/* Labels */}
      <EditorSection
        title="Labels"
        icon={<Type className="size-3.5" />}
      >
        <div className="flex flex-col gap-2">
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              Chart Title
            </label>
            <input
              type="text"
              data-testid="label-title"
              value={state.customTitle ?? ""}
              onChange={(e) => update({ customTitle: e.target.value || undefined })}
              placeholder="Chart title"
              className="rounded-md border bg-background px-2 py-1.5 text-sm text-foreground placeholder:text-muted-foreground"
            />
          </div>
          <div className="flex gap-2">
            <div className="flex flex-1 flex-col gap-1">
              <label className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                X Axis Label
              </label>
              <input
                type="text"
                data-testid="label-x-axis"
                value={state.customXLabel ?? ""}
                onChange={(e) => update({ customXLabel: e.target.value || undefined })}
                placeholder="X axis"
                className="rounded-md border bg-background px-2 py-1.5 text-sm text-foreground placeholder:text-muted-foreground"
              />
            </div>
            <div className="flex flex-1 flex-col gap-1">
              <label className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                Y Axis Label
              </label>
              <input
                type="text"
                data-testid="label-y-axis"
                value={state.customYLabel ?? ""}
                onChange={(e) => update({ customYLabel: e.target.value || undefined })}
                placeholder="Y axis"
                className="rounded-md border bg-background px-2 py-1.5 text-sm text-foreground placeholder:text-muted-foreground"
              />
            </div>
          </div>

          {/* Legend labels */}
          {traceCount > 0 && (
            <div className="flex flex-col gap-1.5">
              <label className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                Legend Labels
              </label>
              <div className="flex flex-col gap-1" data-testid="legend-label-editors">
                {Array.from({ length: traceCount }, (_, i) => (
                  <input
                    key={i}
                    type="text"
                    data-testid={`legend-label-${i}`}
                    value={state.legendLabels[i] ?? ""}
                    onChange={(e) =>
                      update({
                        legendLabels: {
                          ...state.legendLabels,
                          [i]: e.target.value || undefined!,
                        },
                      })
                    }
                    placeholder={traceNames[i] ?? `Series ${i + 1}`}
                    className="rounded-md border bg-background px-2 py-1.5 text-sm text-foreground placeholder:text-muted-foreground"
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      </EditorSection>

      {/* Scale */}
      <EditorSection
        title="Scale"
        icon={<TrendingUp className="size-3.5" />}
      >
        <div className="flex flex-col gap-2">
          {logScaleWarning && (
            <div
              data-testid="log-scale-warning"
              className="flex items-center gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200"
            >
              <AlertTriangle className="size-3.5 shrink-0" />
              {logScaleWarning}
            </div>
          )}
          <div className="flex gap-4">
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                X Scale
              </label>
              <div className="flex rounded-md border">
                <button
                  type="button"
                  data-testid="x-scale-linear"
                  onClick={() => handleScaleChange("x", "linear")}
                  className={cn(
                    "rounded-l-md px-3 py-1 text-xs transition-colors",
                    state.xScale === "linear"
                      ? "bg-primary text-primary-foreground"
                      : "bg-background text-muted-foreground hover:text-foreground",
                  )}
                >
                  Linear
                </button>
                <button
                  type="button"
                  data-testid="x-scale-log"
                  onClick={() => handleScaleChange("x", "log")}
                  className={cn(
                    "rounded-r-md border-l px-3 py-1 text-xs transition-colors",
                    state.xScale === "log"
                      ? "bg-primary text-primary-foreground"
                      : "bg-background text-muted-foreground hover:text-foreground",
                  )}
                >
                  Log
                </button>
              </div>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                Y Scale
              </label>
              <div className="flex rounded-md border">
                <button
                  type="button"
                  data-testid="y-scale-linear"
                  onClick={() => handleScaleChange("y", "linear")}
                  className={cn(
                    "rounded-l-md px-3 py-1 text-xs transition-colors",
                    state.yScale === "linear"
                      ? "bg-primary text-primary-foreground"
                      : "bg-background text-muted-foreground hover:text-foreground",
                  )}
                >
                  Linear
                </button>
                <button
                  type="button"
                  data-testid="y-scale-log"
                  onClick={() => handleScaleChange("y", "log")}
                  className={cn(
                    "rounded-r-md border-l px-3 py-1 text-xs transition-colors",
                    state.yScale === "log"
                      ? "bg-primary text-primary-foreground"
                      : "bg-background text-muted-foreground hover:text-foreground",
                  )}
                >
                  Log
                </button>
              </div>
            </div>
          </div>
        </div>
      </EditorSection>

      {/* Annotations */}
      <EditorSection
        title="Annotations"
        icon={<Minus className="size-3.5" />}
      >
        <div className="flex flex-col gap-3">
          {/* Reference lines */}
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <label className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                Reference Lines
              </label>
              <div className="flex gap-1">
                <button
                  type="button"
                  data-testid="add-hline"
                  onClick={() => addReferenceLine("y")}
                  className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-muted-foreground hover:bg-muted hover:text-foreground"
                >
                  <Plus className="size-3" /> H-Line
                </button>
                <button
                  type="button"
                  data-testid="add-vline"
                  onClick={() => addReferenceLine("x")}
                  className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-muted-foreground hover:bg-muted hover:text-foreground"
                >
                  <Plus className="size-3" /> V-Line
                </button>
              </div>
            </div>

            {state.referenceLines.length > 0 && (
              <div className="flex flex-col gap-1" data-testid="reference-lines-list">
                {state.referenceLines.map((rl) => (
                  <div key={rl.id} className="flex items-center gap-2" data-testid={`ref-line-${rl.id}`}>
                    <span className="text-[10px] font-medium text-muted-foreground w-6">
                      {rl.axis === "x" ? "V" : "H"}
                    </span>
                    <input
                      type="number"
                      value={rl.value}
                      onChange={(e) =>
                        updateReferenceLine(rl.id, { value: parseFloat(e.target.value) || 0 })
                      }
                      data-testid={`ref-line-value-${rl.id}`}
                      className="w-20 rounded border bg-background px-2 py-1 text-xs text-foreground"
                    />
                    <input
                      type="color"
                      value={rl.color}
                      onChange={(e) => updateReferenceLine(rl.id, { color: e.target.value })}
                      data-testid={`ref-line-color-${rl.id}`}
                      className="size-5 cursor-pointer rounded border-0 bg-transparent p-0"
                    />
                    <button
                      type="button"
                      onClick={() => removeReferenceLine(rl.id)}
                      data-testid={`ref-line-remove-${rl.id}`}
                      className="text-muted-foreground hover:text-destructive"
                    >
                      <X className="size-3" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Text annotations */}
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <label className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                Text Annotations
              </label>
              <button
                type="button"
                data-testid="add-annotation"
                onClick={addAnnotation}
                className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <Plus className="size-3" /> Add
              </button>
            </div>

            {state.annotations.length > 0 && (
              <div className="flex flex-col gap-1" data-testid="annotations-list">
                {state.annotations.map((ann) => (
                  <div key={ann.id} className="flex items-center gap-2" data-testid={`annotation-${ann.id}`}>
                    <input
                      type="text"
                      value={ann.text}
                      onChange={(e) => updateAnnotation(ann.id, { text: e.target.value })}
                      data-testid={`annotation-text-${ann.id}`}
                      placeholder="Label text"
                      className="flex-1 rounded border bg-background px-2 py-1 text-xs text-foreground"
                    />
                    <input
                      type="number"
                      value={ann.x}
                      onChange={(e) => updateAnnotation(ann.id, { x: parseFloat(e.target.value) || 0 })}
                      data-testid={`annotation-x-${ann.id}`}
                      placeholder="X"
                      className="w-16 rounded border bg-background px-2 py-1 text-xs text-foreground"
                    />
                    <input
                      type="number"
                      value={ann.y}
                      onChange={(e) => updateAnnotation(ann.id, { y: parseFloat(e.target.value) || 0 })}
                      data-testid={`annotation-y-${ann.id}`}
                      placeholder="Y"
                      className="w-16 rounded border bg-background px-2 py-1 text-xs text-foreground"
                    />
                    <button
                      type="button"
                      onClick={() => removeAnnotation(ann.id)}
                      data-testid={`annotation-remove-${ann.id}`}
                      className="text-muted-foreground hover:text-destructive"
                    >
                      <X className="size-3" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </EditorSection>

      {/* Series Toggle */}
      {traceCount > 0 && (
        <EditorSection
          title="Series"
          icon={<Eye className="size-3.5" />}
        >
          <div className="flex flex-col gap-1" data-testid="series-toggle-list">
            {Array.from({ length: traceCount }, (_, i) => {
              const isHidden = state.hiddenSeries.has(i);
              const palette = COLOR_PALETTES[state.paletteName] ?? COLOR_PALETTES.default;
              const color = state.seriesColors[i] ?? palette.colors[i % palette.colors.length];
              return (
                <button
                  key={i}
                  type="button"
                  onClick={() => toggleSeries(i)}
                  data-testid={`series-toggle-${i}`}
                  className={cn(
                    "flex items-center gap-2 rounded px-2 py-1 text-xs transition-colors",
                    isHidden
                      ? "text-muted-foreground/50"
                      : "text-foreground hover:bg-muted",
                  )}
                >
                  {isHidden ? (
                    <EyeOff className="size-3" />
                  ) : (
                    <Eye className="size-3" />
                  )}
                  <div
                    className="size-2.5 rounded-full"
                    style={{ backgroundColor: isHidden ? "#ccc" : color }}
                  />
                  <span className={cn(isHidden && "line-through")}>
                    {traceNames[i] ?? `Series ${i + 1}`}
                  </span>
                </button>
              );
            })}
          </div>
        </EditorSection>
      )}
    </div>
  );
}
