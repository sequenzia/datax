import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { InteractiveChart } from "../interactive-chart";
import type { PlotlyChartConfig } from "../interactive-chart";

/* -------------------------------------------------------------------------- */
/*  Mocks                                                                      */
/* -------------------------------------------------------------------------- */

// Mock react-plotly.js -- the real Plotly bundle is too heavy for unit tests
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

// Mock useBreakpoint for ActionToolbar
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

const lineConfig: PlotlyChartConfig = {
  data: [
    {
      type: "scatter",
      mode: "lines+markers",
      x: [1, 2, 3, 4, 5],
      y: [10, 20, 30, 40, 50],
      name: "trend",
    },
  ],
  layout: {
    title: { text: "Trend Line" },
    autosize: true,
  },
  chart_type: "line",
};

/* -------------------------------------------------------------------------- */
/*  Helper: open the editor and its Chart Type section                         */
/* -------------------------------------------------------------------------- */

async function openEditor(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByTestId("chart-editor-toggle"));
  // The "Chart Type" section defaults to open, so selectors should be visible
}

/* -------------------------------------------------------------------------- */
/*  Tests                                                                      */
/* -------------------------------------------------------------------------- */

describe("InteractiveChart", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders with valid Plotly config", () => {
    render(
      <InteractiveChart
        chartConfig={barConfig}
        columns={sampleColumns}
        rows={sampleRows}
        title="Sales by Category"
      />,
    );

    expect(screen.getByTestId("interactive-chart")).toBeInTheDocument();
    expect(screen.getByTestId("plotly-chart")).toBeInTheDocument();
    expect(screen.getByText("Sales by Category")).toBeInTheDocument();
  });

  it("renders loading skeleton when isLoading is true", () => {
    render(
      <InteractiveChart
        chartConfig={barConfig}
        columns={sampleColumns}
        rows={sampleRows}
        isLoading
      />,
    );

    expect(screen.getByTestId("skeleton-chart")).toBeInTheDocument();
    expect(screen.queryByTestId("interactive-chart")).not.toBeInTheDocument();
  });

  it("displays AI reasoning text", () => {
    render(
      <InteractiveChart
        chartConfig={barConfig}
        columns={sampleColumns}
        rows={sampleRows}
        reasoning="Bar chart is best for comparing categories"
      />,
    );

    expect(
      screen.getByText("Bar chart is best for comparing categories"),
    ).toBeInTheDocument();
  });

  it("wraps content in ComponentErrorBoundary", () => {
    render(
      <InteractiveChart
        chartConfig={barConfig}
        columns={sampleColumns}
        rows={sampleRows}
      />,
    );

    // Should render successfully (error boundary does not intercept)
    expect(screen.getByTestId("interactive-chart")).toBeInTheDocument();
  });

  describe("Chart type switching", () => {
    it("shows chart editor when Edit button is clicked", async () => {
      const user = userEvent.setup();
      render(
        <InteractiveChart
          chartConfig={barConfig}
          columns={sampleColumns}
          rows={sampleRows}
        />,
      );

      // Editor should be hidden initially
      expect(screen.queryByTestId("chart-editor")).not.toBeInTheDocument();

      // Click Edit button
      await openEditor(user);

      // Editor should be visible with full ChartEditor panel
      expect(screen.getByTestId("chart-editor")).toBeInTheDocument();
      expect(screen.getByTestId("chart-editor-panel")).toBeInTheDocument();
      expect(screen.getByTestId("chart-type-selector")).toBeInTheDocument();
      expect(screen.getByTestId("x-axis-selector")).toBeInTheDocument();
      expect(screen.getByTestId("y-axis-selector")).toBeInTheDocument();
    });

    it("re-renders chart on type switch without AI call", async () => {
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

      // Switch to line chart
      const typeSelector = screen.getByTestId("chart-type-selector");
      await user.selectOptions(typeSelector, "line");

      // Verify chart re-rendered (plotly chart still present, data changed)
      const plotly = screen.getByTestId("plotly-chart");
      expect(plotly).toBeInTheDocument();

      // The data should now contain a scatter trace (line = scatter with lines+markers)
      const chartData = JSON.parse(
        plotly.getAttribute("data-chart-data") ?? "[]",
      );
      expect(chartData[0].type).toBe("scatter");
      expect(chartData[0].mode).toBe("lines+markers");
    });

    it("offers all 16 chart types in the selector", async () => {
      const user = userEvent.setup();
      render(
        <InteractiveChart
          chartConfig={barConfig}
          columns={sampleColumns}
          rows={sampleRows}
        />,
      );

      await openEditor(user);

      const typeSelector = screen.getByTestId(
        "chart-type-selector",
      ) as HTMLSelectElement;
      const options = Array.from(typeSelector.options);

      expect(options.length).toBe(16);
      expect(options.map((o) => o.value)).toEqual([
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
      ]);
    });
  });

  describe("Axis assignment", () => {
    it("allows swapping X axis column", async () => {
      const user = userEvent.setup();
      render(
        <InteractiveChart
          chartConfig={barConfig}
          columns={sampleColumns}
          rows={sampleRows}
        />,
      );

      await openEditor(user);

      // Change X axis to "sales"
      const xSelector = screen.getByTestId("x-axis-selector");
      await user.selectOptions(xSelector, "sales");

      // Chart should re-render with new x-axis data
      const plotly = screen.getByTestId("plotly-chart");
      expect(plotly).toBeInTheDocument();

      const chartData = JSON.parse(
        plotly.getAttribute("data-chart-data") ?? "[]",
      );
      // X values should now be sales values
      expect(chartData[0].x).toEqual([1200, 800, 600, 400, 900]);
    });

    it("allows swapping Y axis column", async () => {
      const user = userEvent.setup();
      render(
        <InteractiveChart
          chartConfig={barConfig}
          columns={sampleColumns}
          rows={sampleRows}
        />,
      );

      await openEditor(user);

      // Change Y axis to "profit"
      const ySelector = screen.getByTestId("y-axis-selector");
      await user.selectOptions(ySelector, "profit");

      // Chart should re-render with profit data
      const plotly = screen.getByTestId("plotly-chart");
      const chartData = JSON.parse(
        plotly.getAttribute("data-chart-data") ?? "[]",
      );
      expect(chartData[0].y).toEqual([300, 200, 150, 100, 250]);
    });
  });

  describe("Incompatible chart type warnings", () => {
    it("shows warning when switching to pie with many rows", async () => {
      const manyRows = Array.from({ length: 25 }, (_, i) => [
        `Item ${i}`,
        i * 100,
        i * 50,
      ]);

      const user = userEvent.setup();
      render(
        <InteractiveChart
          chartConfig={barConfig}
          columns={sampleColumns}
          rows={manyRows}
        />,
      );

      await openEditor(user);
      await user.selectOptions(screen.getByTestId("chart-type-selector"), "pie");

      expect(screen.getByTestId("chart-warning")).toBeInTheDocument();
      expect(screen.getByText(/hard to read/)).toBeInTheDocument();
    });

    it("disables incompatible chart types (candlestick with insufficient columns)", async () => {
      const twoColConfig: PlotlyChartConfig = {
        data: [{ type: "bar", x: [1, 2], y: [10, 20] }],
        layout: { autosize: true },
        chart_type: "bar",
      };

      const user = userEvent.setup();
      render(
        <InteractiveChart
          chartConfig={twoColConfig}
          columns={["a", "b"]}
          rows={[
            [1, 10],
            [2, 20],
          ]}
        />,
      );

      await openEditor(user);
      await user.selectOptions(
        screen.getByTestId("chart-type-selector"),
        "candlestick",
      );

      // Should show warning about insufficient columns
      expect(screen.getByTestId("chart-warning")).toBeInTheDocument();
      expect(screen.getByText(/4 numeric columns/)).toBeInTheDocument();
    });
  });

  describe("Export", () => {
    it("shows export menu with PNG and SVG options", async () => {
      const user = userEvent.setup();
      render(
        <InteractiveChart
          chartConfig={barConfig}
          columns={sampleColumns}
          rows={sampleRows}
        />,
      );

      // Click the export button in the ActionToolbar
      await user.click(screen.getByTestId("toolbar-export"));

      expect(screen.getByTestId("export-menu")).toBeInTheDocument();
      expect(screen.getByTestId("export-png")).toBeInTheDocument();
      expect(screen.getByTestId("export-svg")).toBeInTheDocument();
    });
  });

  describe("Design system integration", () => {
    it("uses design system card styling", () => {
      render(
        <InteractiveChart
          chartConfig={barConfig}
          columns={sampleColumns}
          rows={sampleRows}
        />,
      );

      const chart = screen.getByTestId("interactive-chart");
      expect(chart.className).toContain("rounded-lg");
      expect(chart.className).toContain("border");
      expect(chart.className).toContain("bg-card");
      expect(chart.className).toContain("shadow-sm");
    });

    it("applies custom className", () => {
      render(
        <InteractiveChart
          chartConfig={barConfig}
          columns={sampleColumns}
          rows={sampleRows}
          className="my-custom-class"
        />,
      );

      const chart = screen.getByTestId("interactive-chart");
      expect(chart.className).toContain("my-custom-class");
    });

    it("includes ActionToolbar with export action", () => {
      render(
        <InteractiveChart
          chartConfig={barConfig}
          columns={sampleColumns}
          rows={sampleRows}
        />,
      );

      expect(screen.getByTestId("toolbar-export")).toBeInTheDocument();
    });
  });

  describe("WebGL for large datasets", () => {
    it("uses heatmapgl for heatmap with 10k+ rows", async () => {
      const largeRows = Array.from({ length: 10_001 }, (_, i) => [
        i,
        i % 100,
        Math.random(),
      ]);

      const user = userEvent.setup();
      render(
        <InteractiveChart
          chartConfig={{
            ...barConfig,
            chart_type: "bar",
          }}
          columns={["x", "y", "z"]}
          rows={largeRows}
        />,
      );

      await openEditor(user);
      await user.selectOptions(
        screen.getByTestId("chart-type-selector"),
        "heatmap",
      );

      const plotly = screen.getByTestId("plotly-chart");
      const chartData = JSON.parse(
        plotly.getAttribute("data-chart-data") ?? "[]",
      );
      expect(chartData[0].type).toBe("heatmapgl");
    });
  });
});
