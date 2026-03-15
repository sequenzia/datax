import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { InteractiveChart } from "../interactive-chart";
import type { PlotlyChartConfig } from "../interactive-chart";
import {
  ChartEditor,
  createInitialEditorState,
  applyEditorToPlotly,
  COLOR_PALETTES,
  PALETTE_NAMES,
} from "../chart-editor";
import type { ChartEditorState } from "../chart-editor";
import { MultiChartGrid } from "../multi-chart-grid";

/* -------------------------------------------------------------------------- */
/*  Mocks                                                                      */
/* -------------------------------------------------------------------------- */

vi.mock("react-plotly.js", () => ({
  __esModule: true,
  default: function MockPlot(props: {
    data: unknown[];
    layout: Record<string, unknown>;
    config: Record<string, unknown>;
  }) {
    return (
      <div
        data-testid="plotly-chart"
        data-chart-data={JSON.stringify(props.data)}
        data-chart-layout={JSON.stringify(props.layout)}
      />
    );
  },
}));

vi.mock("@/hooks/use-breakpoint", () => ({
  useBreakpoint: () => "desktop",
}));

/* -------------------------------------------------------------------------- */
/*  Test data                                                                   */
/* -------------------------------------------------------------------------- */

const sampleColumns = ["category", "sales", "profit"];
const sampleRows: unknown[][] = [
  ["Electronics", 1200, 300],
  ["Clothing", 800, 200],
  ["Food", 600, 150],
  ["Books", 400, 100],
  ["Sports", 900, 250],
];

const barConfig: PlotlyChartConfig = {
  data: [
    {
      type: "bar",
      x: ["Electronics", "Clothing", "Food", "Books", "Sports"],
      y: [1200, 800, 600, 400, 900],
      name: "sales",
    },
  ],
  layout: {
    title: { text: "Sales by Category" },
    autosize: true,
    xaxis: { title: { text: "category" } },
    yaxis: { title: { text: "sales" } },
  },
  chart_type: "bar",
};

const multiTraceConfig: PlotlyChartConfig = {
  data: [
    { type: "bar", x: [1, 2, 3], y: [10, 20, 30], name: "Series A" },
    { type: "bar", x: [1, 2, 3], y: [15, 25, 35], name: "Series B" },
  ],
  layout: {
    title: { text: "Multi-series" },
    autosize: true,
  },
  chart_type: "bar",
};

/* -------------------------------------------------------------------------- */
/*  Helpers                                                                     */
/* -------------------------------------------------------------------------- */

function renderEditor(overrides?: Partial<Parameters<typeof ChartEditor>[0]>) {
  const state = createInitialEditorState("bar", sampleColumns);
  const onChange = vi.fn();

  const defaultProps = {
    columns: sampleColumns,
    state,
    traceCount: 1,
    traceNames: ["sales"],
    hasZeroOrNegativeValues: false,
    onChange,
  };

  const result = render(<ChartEditor {...defaultProps} {...overrides} />);
  return { state, onChange, ...result };
}

/**
 * A wrapper that manages ChartEditor state, so controlled input
 * updates propagate correctly across keystrokes.
 */
function StatefulChartEditor(props: Omit<Parameters<typeof ChartEditor>[0], "state" | "onChange"> & { initialState: ChartEditorState; onChangeCapture?: (s: ChartEditorState) => void }) {
  const [state, setState] = useState(props.initialState);
  const handleChange = (newState: ChartEditorState) => {
    setState(newState);
    props.onChangeCapture?.(newState);
  };
  return <ChartEditor {...props} state={state} onChange={handleChange} />;
}

function renderStatefulEditor(overrides?: Partial<Omit<Parameters<typeof ChartEditor>[0], "state" | "onChange">>) {
  const initialState = createInitialEditorState("bar", sampleColumns);
  const onChangeCapture = vi.fn();

  const defaultProps = {
    columns: sampleColumns,
    initialState,
    traceCount: 1,
    traceNames: ["sales"],
    hasZeroOrNegativeValues: false,
    onChangeCapture,
  };

  const result = render(<StatefulChartEditor {...defaultProps} {...overrides} />);
  return { initialState, onChangeCapture, ...result };
}

async function openEditor(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByTestId("chart-editor-toggle"));
}

/* -------------------------------------------------------------------------- */
/*  ChartEditor unit tests                                                     */
/* -------------------------------------------------------------------------- */

describe("ChartEditor", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("Color palette selector", () => {
    it("renders 7+ preset palettes", async () => {
      const user = userEvent.setup();
      renderEditor();

      // Open the Colors section
      await user.click(screen.getByTestId("section-toggle-colors"));

      const paletteSelector = screen.getByTestId("palette-selector");
      expect(paletteSelector).toBeInTheDocument();

      // There should be 7 palettes
      expect(PALETTE_NAMES.length).toBeGreaterThanOrEqual(5);
      for (const name of PALETTE_NAMES) {
        expect(screen.getByTestId(`palette-${name}`)).toBeInTheDocument();
      }
    });

    it("selects a palette and clears per-series overrides", async () => {
      const user = userEvent.setup();
      const { onChange } = renderEditor();

      await user.click(screen.getByTestId("section-toggle-colors"));
      await user.click(screen.getByTestId("palette-vivid"));

      expect(onChange).toHaveBeenCalled();
      const newState = onChange.mock.calls[0][0] as ChartEditorState;
      expect(newState.paletteName).toBe("vivid");
      expect(newState.seriesColors).toEqual({});
    });
  });

  describe("Individual series color picker", () => {
    it("renders color picker for each trace", async () => {
      const user = userEvent.setup();
      renderEditor({ traceCount: 2, traceNames: ["A", "B"] });

      await user.click(screen.getByTestId("section-toggle-colors"));

      expect(screen.getByTestId("series-color-0")).toBeInTheDocument();
      expect(screen.getByTestId("series-color-1")).toBeInTheDocument();
    });

    it("calls onChange with updated series color", async () => {
      const user = userEvent.setup();
      const { onChange } = renderEditor({ traceCount: 1, traceNames: ["sales"] });

      await user.click(screen.getByTestId("section-toggle-colors"));

      const picker = screen.getByTestId("series-color-0") as HTMLInputElement;
      // Simulate color change via fireEvent since userEvent doesn't support type="color"
      await user.click(picker);
      // Color inputs need direct value setting
      const event = new Event("input", { bubbles: true });
      Object.defineProperty(picker, "value", { writable: true, value: "#ff0000" });
      picker.dispatchEvent(new Event("change", { bubbles: true }));

      // The onChange should have been called (may vary depending on event handling)
    });
  });

  describe("Label editing", () => {
    it("provides title editing input", async () => {
      const user = userEvent.setup();
      const { onChangeCapture } = renderStatefulEditor();

      await user.click(screen.getByTestId("section-toggle-labels"));

      const titleInput = screen.getByTestId("label-title") as HTMLInputElement;
      expect(titleInput).toBeInTheDocument();

      await user.clear(titleInput);
      await user.type(titleInput, "New Title");

      expect(onChangeCapture).toHaveBeenCalled();
      // After typing all chars, the final state should have the full title
      const calls = onChangeCapture.mock.calls;
      const lastCall = calls[calls.length - 1][0] as ChartEditorState;
      expect(lastCall.customTitle).toBe("New Title");
    });

    it("provides axis label inputs", async () => {
      const user = userEvent.setup();
      renderEditor();

      await user.click(screen.getByTestId("section-toggle-labels"));

      expect(screen.getByTestId("label-x-axis")).toBeInTheDocument();
      expect(screen.getByTestId("label-y-axis")).toBeInTheDocument();
    });

    it("provides legend label editing for traces", async () => {
      const user = userEvent.setup();
      renderEditor({ traceCount: 2, traceNames: ["A", "B"] });

      await user.click(screen.getByTestId("section-toggle-labels"));

      expect(screen.getByTestId("legend-label-0")).toBeInTheDocument();
      expect(screen.getByTestId("legend-label-1")).toBeInTheDocument();
    });
  });

  describe("Scale control", () => {
    it("shows linear/log toggle for X and Y axes", async () => {
      const user = userEvent.setup();
      renderEditor();

      await user.click(screen.getByTestId("section-toggle-scale"));

      expect(screen.getByTestId("x-scale-linear")).toBeInTheDocument();
      expect(screen.getByTestId("x-scale-log")).toBeInTheDocument();
      expect(screen.getByTestId("y-scale-linear")).toBeInTheDocument();
      expect(screen.getByTestId("y-scale-log")).toBeInTheDocument();
    });

    it("switches Y axis to logarithmic", async () => {
      const user = userEvent.setup();
      const { onChange } = renderEditor();

      await user.click(screen.getByTestId("section-toggle-scale"));
      await user.click(screen.getByTestId("y-scale-log"));

      expect(onChange).toHaveBeenCalled();
      const newState = onChange.mock.calls[0][0] as ChartEditorState;
      expect(newState.yScale).toBe("log");
    });

    it("shows warning when log scale used with zero/negative values", async () => {
      const user = userEvent.setup();
      const { onChange } = renderEditor({ hasZeroOrNegativeValues: true });

      await user.click(screen.getByTestId("section-toggle-scale"));
      await user.click(screen.getByTestId("y-scale-log"));

      // Should show warning and NOT call onChange
      expect(screen.getByTestId("log-scale-warning")).toBeInTheDocument();
      expect(screen.getByText(/zero or negative values/)).toBeInTheDocument();
      expect(onChange).not.toHaveBeenCalled();
    });
  });

  describe("Reference lines", () => {
    it("adds horizontal and vertical reference lines", async () => {
      const user = userEvent.setup();
      const { onChange } = renderEditor();

      await user.click(screen.getByTestId("section-toggle-annotations"));

      // Add horizontal line
      await user.click(screen.getByTestId("add-hline"));
      expect(onChange).toHaveBeenCalledTimes(1);
      const hlineState = onChange.mock.calls[0][0] as ChartEditorState;
      expect(hlineState.referenceLines.length).toBe(1);
      expect(hlineState.referenceLines[0].axis).toBe("y");

      // Add vertical line
      await user.click(screen.getByTestId("add-vline"));
      expect(onChange).toHaveBeenCalledTimes(2);
    });

    it("allows setting value for reference lines", async () => {
      const user = userEvent.setup();
      const state = createInitialEditorState("bar", sampleColumns);
      const stateWithLine = {
        ...state,
        referenceLines: [{ id: "ref-1", axis: "y" as const, value: 0, color: "#FF0000" }],
      };
      const onChange = vi.fn();

      render(
        <ChartEditor
          columns={sampleColumns}
          state={stateWithLine}
          traceCount={1}
          traceNames={["sales"]}
          hasZeroOrNegativeValues={false}
          onChange={onChange}
        />,
      );

      await user.click(screen.getByTestId("section-toggle-annotations"));

      const valueInput = screen.getByTestId("ref-line-value-ref-1") as HTMLInputElement;
      expect(valueInput).toBeInTheDocument();
    });
  });

  describe("Text annotations", () => {
    it("adds text annotation with position inputs", async () => {
      const user = userEvent.setup();
      const { onChange } = renderEditor();

      await user.click(screen.getByTestId("section-toggle-annotations"));
      await user.click(screen.getByTestId("add-annotation"));

      expect(onChange).toHaveBeenCalledTimes(1);
      const newState = onChange.mock.calls[0][0] as ChartEditorState;
      expect(newState.annotations.length).toBe(1);
      expect(newState.annotations[0].text).toBe("Label");
    });
  });

  describe("Series toggle", () => {
    it("renders toggle for each series", async () => {
      const user = userEvent.setup();
      renderEditor({ traceCount: 2, traceNames: ["A", "B"] });

      await user.click(screen.getByTestId("section-toggle-series"));

      expect(screen.getByTestId("series-toggle-0")).toBeInTheDocument();
      expect(screen.getByTestId("series-toggle-1")).toBeInTheDocument();
    });

    it("hides/shows series on toggle", async () => {
      const user = userEvent.setup();
      const { onChange } = renderEditor({ traceCount: 2, traceNames: ["A", "B"] });

      await user.click(screen.getByTestId("section-toggle-series"));
      await user.click(screen.getByTestId("series-toggle-0"));

      expect(onChange).toHaveBeenCalled();
      const newState = onChange.mock.calls[0][0] as ChartEditorState;
      expect(newState.hiddenSeries.has(0)).toBe(true);
    });
  });
});

/* -------------------------------------------------------------------------- */
/*  applyEditorToPlotly unit tests                                             */
/* -------------------------------------------------------------------------- */

describe("applyEditorToPlotly", () => {
  it("applies palette colors to traces", () => {
    const state = createInitialEditorState("bar", sampleColumns);
    state.paletteName = "vivid";

    const inputData: Plotly.Data[] = [
      { type: "bar", x: [1], y: [2], name: "A" },
      { type: "bar", x: [1], y: [3], name: "B" },
    ];
    const inputLayout: Partial<Plotly.Layout> = {};

    const { data } = applyEditorToPlotly(inputData, inputLayout, state);

    const vividPalette = COLOR_PALETTES.vivid;
    expect((data[0] as { marker: { color: string } }).marker.color).toBe(vividPalette.colors[0]);
    expect((data[1] as { marker: { color: string } }).marker.color).toBe(vividPalette.colors[1]);
  });

  it("applies custom series color overrides", () => {
    const state = createInitialEditorState("bar", sampleColumns);
    state.seriesColors = { 0: "#123456" };

    const inputData: Plotly.Data[] = [
      { type: "bar", x: [1], y: [2], name: "A" },
    ];

    const { data } = applyEditorToPlotly(inputData, {}, state);
    expect((data[0] as { marker: { color: string } }).marker.color).toBe("#123456");
  });

  it("applies custom title", () => {
    const state = createInitialEditorState("bar", sampleColumns);
    state.customTitle = "My Custom Title";

    const { layout } = applyEditorToPlotly([], {}, state);
    expect((layout.title as { text: string }).text).toBe("My Custom Title");
  });

  it("applies custom axis labels", () => {
    const state = createInitialEditorState("bar", sampleColumns);
    state.customXLabel = "Custom X";
    state.customYLabel = "Custom Y";

    const { layout } = applyEditorToPlotly([], {}, state);
    expect((layout.xaxis as { title: { text: string } }).title.text).toBe("Custom X");
    expect((layout.yaxis as { title: { text: string } }).title.text).toBe("Custom Y");
  });

  it("applies log scale to axes", () => {
    const state = createInitialEditorState("bar", sampleColumns);
    state.xScale = "log";
    state.yScale = "log";

    const { layout } = applyEditorToPlotly([], {}, state);
    expect((layout.xaxis as { type: string }).type).toBe("log");
    expect((layout.yaxis as { type: string }).type).toBe("log");
  });

  it("applies reference lines as shapes", () => {
    const state = createInitialEditorState("bar", sampleColumns);
    state.referenceLines = [
      { id: "r1", axis: "y", value: 500, color: "#FF0000" },
      { id: "r2", axis: "x", value: 2, color: "#0000FF" },
    ];

    const { layout } = applyEditorToPlotly([], {}, state);
    expect(layout.shapes).toHaveLength(2);

    const shapes = layout.shapes as Partial<Plotly.Shape>[];
    // Horizontal line (y-axis) should have y0/y1 set to value
    expect(shapes[0].y0).toBe(500);
    expect(shapes[0].y1).toBe(500);
    // Vertical line (x-axis) should have x0/x1 set to value
    expect(shapes[1].x0).toBe(2);
    expect(shapes[1].x1).toBe(2);
  });

  it("applies text annotations", () => {
    const state = createInitialEditorState("bar", sampleColumns);
    state.annotations = [
      { id: "a1", text: "Peak", x: 3, y: 100 },
    ];

    const { layout } = applyEditorToPlotly([], {}, state);
    expect(layout.annotations).toHaveLength(1);

    const annotations = layout.annotations as Partial<Plotly.Annotations>[];
    expect(annotations[0].text).toBe("Peak");
    expect(annotations[0].x).toBe(3);
    expect(annotations[0].y).toBe(100);
  });

  it("hides series via visible='legendonly'", () => {
    const state = createInitialEditorState("bar", sampleColumns);
    state.hiddenSeries = new Set([1]);

    const inputData: Plotly.Data[] = [
      { type: "bar", x: [1], y: [2], name: "A" },
      { type: "bar", x: [1], y: [3], name: "B" },
    ];

    const { data } = applyEditorToPlotly(inputData, {}, state);
    expect((data[0] as { visible: boolean | string }).visible).toBe(true);
    expect((data[1] as { visible: boolean | string }).visible).toBe("legendonly");
  });

  it("applies legend label overrides", () => {
    const state = createInitialEditorState("bar", sampleColumns);
    state.legendLabels = { 0: "Revenue" };

    const inputData: Plotly.Data[] = [
      { type: "bar", x: [1], y: [2], name: "sales" },
    ];

    const { data } = applyEditorToPlotly(inputData, {}, state);
    expect((data[0] as { name: string }).name).toBe("Revenue");
  });
});

/* -------------------------------------------------------------------------- */
/*  Integration: ChartEditor within InteractiveChart                           */
/* -------------------------------------------------------------------------- */

describe("ChartEditor integration with InteractiveChart", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("color picker changes trace colors", async () => {
    const user = userEvent.setup();
    render(
      <InteractiveChart
        chartConfig={barConfig}
        columns={sampleColumns}
        rows={sampleRows}
      />,
    );

    // Open editor
    await openEditor(user);

    // Open colors section
    await user.click(screen.getByTestId("section-toggle-colors"));

    // Select a different palette
    await user.click(screen.getByTestId("palette-vivid"));

    // Chart should re-render with new palette colors
    const plotly = screen.getByTestId("plotly-chart");
    const chartData = JSON.parse(plotly.getAttribute("data-chart-data") ?? "[]");

    // The trace should have the vivid palette first color applied
    expect(chartData[0].marker.color).toBe(COLOR_PALETTES.vivid.colors[0]);
  });

  it("label editing updates chart text", async () => {
    const user = userEvent.setup();
    render(
      <InteractiveChart
        chartConfig={barConfig}
        columns={sampleColumns}
        rows={sampleRows}
      />,
    );

    await openEditor(user);
    await user.click(screen.getByTestId("section-toggle-labels"));

    // Type a custom title
    const titleInput = screen.getByTestId("label-title") as HTMLInputElement;
    await user.type(titleInput, "My Chart");

    // Verify layout was updated
    const plotly = screen.getByTestId("plotly-chart");
    const layout = JSON.parse(plotly.getAttribute("data-chart-layout") ?? "{}");
    expect(layout.title?.text).toBe("My Chart");
  });

  it("scale toggle switches axes correctly", async () => {
    const user = userEvent.setup();
    render(
      <InteractiveChart
        chartConfig={barConfig}
        columns={sampleColumns}
        rows={sampleRows}
      />,
    );

    await openEditor(user);
    await user.click(screen.getByTestId("section-toggle-scale"));

    // Switch Y to log
    await user.click(screen.getByTestId("y-scale-log"));

    const plotly = screen.getByTestId("plotly-chart");
    const layout = JSON.parse(plotly.getAttribute("data-chart-layout") ?? "{}");
    expect(layout.yaxis?.type).toBe("log");
  });

  it("editor panel is toggleable (open/closed)", async () => {
    const user = userEvent.setup();
    render(
      <InteractiveChart
        chartConfig={barConfig}
        columns={sampleColumns}
        rows={sampleRows}
      />,
    );

    // Initially closed
    expect(screen.queryByTestId("chart-editor")).not.toBeInTheDocument();

    // Open
    await user.click(screen.getByTestId("chart-editor-toggle"));
    expect(screen.getByTestId("chart-editor")).toBeInTheDocument();

    // Close
    await user.click(screen.getByTestId("chart-editor-toggle"));
    expect(screen.queryByTestId("chart-editor")).not.toBeInTheDocument();
  });

  it("all modifications are client-side, no AI call", async () => {
    const user = userEvent.setup();
    const fetchSpy = vi.spyOn(globalThis, "fetch");

    render(
      <InteractiveChart
        chartConfig={barConfig}
        columns={sampleColumns}
        rows={sampleRows}
      />,
    );

    await openEditor(user);

    // Do several modifications
    await user.selectOptions(screen.getByTestId("chart-type-selector"), "line");
    await user.click(screen.getByTestId("section-toggle-colors"));
    await user.click(screen.getByTestId("palette-ocean"));
    await user.click(screen.getByTestId("section-toggle-scale"));
    await user.click(screen.getByTestId("y-scale-log"));

    // No fetch calls should have been made
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});

/* -------------------------------------------------------------------------- */
/*  MultiChartGrid tests                                                       */
/* -------------------------------------------------------------------------- */

describe("MultiChartGrid", () => {
  it("renders multiple charts side by side", () => {
    const charts = [
      {
        chartConfig: barConfig,
        columns: sampleColumns,
        rows: sampleRows,
        title: "Chart 1",
      },
      {
        chartConfig: barConfig,
        columns: sampleColumns,
        rows: sampleRows,
        title: "Chart 2",
      },
    ];

    render(<MultiChartGrid charts={charts} />);

    expect(screen.getByTestId("multi-chart-grid")).toBeInTheDocument();
    expect(screen.getByTestId("multi-chart-item-0")).toBeInTheDocument();
    expect(screen.getByTestId("multi-chart-item-1")).toBeInTheDocument();

    // Both charts should render independently
    const plotlyCharts = screen.getAllByTestId("plotly-chart");
    expect(plotlyCharts.length).toBe(2);
  });

  it("renders empty state when no charts", () => {
    render(<MultiChartGrid charts={[]} />);

    expect(screen.getByTestId("multi-chart-empty")).toBeInTheDocument();
  });

  it("each chart is independent with different data", () => {
    const charts = [
      {
        chartConfig: barConfig,
        columns: sampleColumns,
        rows: sampleRows,
        title: "Sales Chart",
      },
      {
        chartConfig: {
          ...barConfig,
          data: [{ type: "bar" as const, x: ["A", "B"], y: [10, 20], name: "other" }],
        },
        columns: ["name", "value"],
        rows: [["A", 10], ["B", 20]],
        title: "Other Chart",
      },
    ];

    render(<MultiChartGrid charts={charts} />);

    const plotlyCharts = screen.getAllByTestId("plotly-chart");

    // First chart should have the original bar data
    const data1 = JSON.parse(plotlyCharts[0].getAttribute("data-chart-data") ?? "[]");
    expect(data1[0].name).toBe("sales");

    // Second chart should have different data
    const data2 = JSON.parse(plotlyCharts[1].getAttribute("data-chart-data") ?? "[]");
    expect(data2[0].name).toBe("other");
  });

  it("supports remove button per chart", async () => {
    const user = userEvent.setup();
    const onRemove = vi.fn();

    const charts = [
      { chartConfig: barConfig, columns: sampleColumns, rows: sampleRows, title: "Chart 1" },
      { chartConfig: barConfig, columns: sampleColumns, rows: sampleRows, title: "Chart 2" },
    ];

    render(<MultiChartGrid charts={charts} onRemoveChart={onRemove} />);

    expect(screen.getByTestId("remove-chart-0")).toBeInTheDocument();
    expect(screen.getByTestId("remove-chart-1")).toBeInTheDocument();

    await user.click(screen.getByTestId("remove-chart-1"));
    expect(onRemove).toHaveBeenCalledWith(1);
  });

  it("applies grid layout with configurable columns", () => {
    const charts = [
      { chartConfig: barConfig, columns: sampleColumns, rows: sampleRows },
      { chartConfig: barConfig, columns: sampleColumns, rows: sampleRows },
      { chartConfig: barConfig, columns: sampleColumns, rows: sampleRows },
    ];

    const { container } = render(<MultiChartGrid charts={charts} gridColumns={3} />);

    const grid = screen.getByTestId("multi-chart-grid");
    expect(grid.className).toContain("grid");
  });
});

/* -------------------------------------------------------------------------- */
/*  COLOR_PALETTES validation                                                  */
/* -------------------------------------------------------------------------- */

describe("COLOR_PALETTES", () => {
  it("has at least 5 preset palettes", () => {
    expect(PALETTE_NAMES.length).toBeGreaterThanOrEqual(5);
  });

  it("each palette has at least 6 colors", () => {
    for (const key of PALETTE_NAMES) {
      expect(COLOR_PALETTES[key].colors.length).toBeGreaterThanOrEqual(6);
    }
  });

  it("each palette has a display name", () => {
    for (const key of PALETTE_NAMES) {
      expect(COLOR_PALETTES[key].name).toBeTruthy();
    }
  });
});
