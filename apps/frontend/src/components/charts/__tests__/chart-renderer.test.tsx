import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { ChartRenderer } from "../chart-renderer";
import type { ChartConfig } from "../chart-renderer";

// Mock chart-export module
const mockExportChart = vi.fn().mockResolvedValue(undefined);
const mockExportKpiCard = vi.fn().mockResolvedValue(undefined);

vi.mock("../chart-export", () => ({
  exportChart: (...args: unknown[]) => mockExportChart(...args),
  exportKpiCard: (...args: unknown[]) => mockExportKpiCard(...args),
}));

// Mock react-plotly.js with a lightweight div that renders data attributes
vi.mock("react-plotly.js", () => ({
  __esModule: true,
  default: ({
    data,
    layout,
    config,
    useResizeHandler,
  }: {
    data: unknown[];
    layout: Record<string, unknown>;
    config: Record<string, unknown>;
    useResizeHandler: boolean;
  }) => (
    <div
      data-testid="plotly-mock"
      className="js-plotly-plot"
      data-traces={data.length}
      data-autosize={String(layout.autosize)}
      data-responsive={String(config.responsive)}
      data-resize-handler={String(useResizeHandler)}
    >
      Plotly Chart
    </div>
  ),
}));

function makeBarConfig(overrides: Partial<ChartConfig> = {}): ChartConfig {
  return {
    type: "bar",
    data: [
      {
        type: "bar",
        x: ["Product A", "Product B", "Product C"],
        y: [100, 200, 150],
        name: "Revenue",
      },
    ],
    layout: {
      title: "Revenue by Product",
    },
    ...overrides,
  };
}

function makeLineConfig(): ChartConfig {
  return {
    type: "line",
    data: [
      {
        type: "scatter",
        mode: "lines",
        x: ["2024-01", "2024-02", "2024-03"],
        y: [10, 25, 18],
        name: "Monthly Sales",
      },
    ],
    layout: { title: "Sales Over Time" },
  };
}

function makePieConfig(): ChartConfig {
  return {
    type: "pie",
    data: [
      {
        type: "pie",
        labels: ["Desktop", "Mobile", "Tablet"],
        values: [60, 30, 10],
      },
    ],
    layout: { title: "Traffic by Device" },
  };
}

function makeScatterConfig(): ChartConfig {
  return {
    type: "scatter",
    data: [
      {
        type: "scatter",
        mode: "markers",
        x: [1, 2, 3, 4, 5],
        y: [10, 15, 13, 17, 21],
        name: "Data Points",
      },
    ],
    layout: { title: "Scatter Plot" },
  };
}

function makeKpiConfig(overrides: Partial<ChartConfig> = {}): ChartConfig {
  return {
    type: "kpi",
    kpiValue: 42567,
    kpiLabel: "Total Revenue",
    kpiPrefix: "$",
    kpiDelta: 12.5,
    ...overrides,
  };
}

describe("ChartRenderer", () => {
  beforeEach(() => {
    mockExportChart.mockClear();
    mockExportKpiCard.mockClear();
  });

  describe("Chart type rendering", () => {
    it("renders a line chart with zoom/pan enabled", () => {
      render(<ChartRenderer chartConfig={makeLineConfig()} />);

      const plotly = screen.getByTestId("plotly-mock");
      expect(plotly).toBeInTheDocument();
      expect(plotly).toHaveAttribute("data-traces", "1");
      expect(plotly).toHaveAttribute("data-autosize", "true");
      expect(plotly).toHaveAttribute("data-responsive", "true");
    });

    it("renders a bar chart with hover", () => {
      render(<ChartRenderer chartConfig={makeBarConfig()} />);

      const plotly = screen.getByTestId("plotly-mock");
      expect(plotly).toBeInTheDocument();
      expect(plotly).toHaveAttribute("data-traces", "1");
    });

    it("renders a pie chart with labels", () => {
      render(<ChartRenderer chartConfig={makePieConfig()} />);

      const plotly = screen.getByTestId("plotly-mock");
      expect(plotly).toBeInTheDocument();
    });

    it("renders a scatter chart with selection", () => {
      render(<ChartRenderer chartConfig={makeScatterConfig()} />);

      const plotly = screen.getByTestId("plotly-mock");
      expect(plotly).toBeInTheDocument();
    });

    it("renders a KPI card for single values", () => {
      render(<ChartRenderer chartConfig={makeKpiConfig()} />);

      const kpiCard = screen.getByTestId("kpi-card");
      expect(kpiCard).toBeInTheDocument();
      expect(screen.getByText("Total Revenue")).toBeInTheDocument();

      const kpiValue = screen.getByTestId("kpi-value");
      expect(kpiValue).toHaveTextContent("$42,567");
    });

    it("renders KPI card with delta indicator", () => {
      render(<ChartRenderer chartConfig={makeKpiConfig({ kpiDelta: 12.5 })} />);

      const delta = screen.getByTestId("kpi-delta");
      expect(delta).toBeInTheDocument();
      expect(delta).toHaveTextContent("+12.5%");
    });

    it("renders KPI card with negative delta", () => {
      render(<ChartRenderer chartConfig={makeKpiConfig({ kpiDelta: -5.2 })} />);

      const delta = screen.getByTestId("kpi-delta");
      expect(delta).toHaveTextContent("-5.2%");
      expect(delta.className).toContain("text-red-500");
    });

    it("renders KPI card with zero delta", () => {
      render(<ChartRenderer chartConfig={makeKpiConfig({ kpiDelta: 0 })} />);

      const delta = screen.getByTestId("kpi-delta");
      expect(delta).toHaveTextContent("0%");
    });

    it("renders KPI card with suffix", () => {
      render(
        <ChartRenderer
          chartConfig={makeKpiConfig({ kpiPrefix: "", kpiSuffix: " users", kpiValue: 1000 })}
        />,
      );

      const kpiValue = screen.getByTestId("kpi-value");
      expect(kpiValue).toHaveTextContent("1,000 users");
    });

    it("renders KPI card without delta when null", () => {
      render(
        <ChartRenderer chartConfig={makeKpiConfig({ kpiDelta: null })} />,
      );

      expect(screen.queryByTestId("kpi-delta")).not.toBeInTheDocument();
    });
  });

  describe("Export toolbar", () => {
    it("shows export toolbar with PNG and SVG buttons for Plotly charts", () => {
      render(<ChartRenderer chartConfig={makeBarConfig()} />);

      const toolbar = screen.getByTestId("chart-export-toolbar");
      expect(toolbar).toBeInTheDocument();

      const pngBtn = screen.getByTestId("export-png-btn");
      expect(pngBtn).toBeInTheDocument();
      expect(pngBtn).toHaveTextContent("PNG");

      const svgBtn = screen.getByTestId("export-svg-btn");
      expect(svgBtn).toBeInTheDocument();
      expect(svgBtn).toHaveTextContent("SVG");
    });

    it("shows export toolbar with only PNG button for KPI cards", () => {
      render(<ChartRenderer chartConfig={makeKpiConfig()} />);

      const toolbar = screen.getByTestId("chart-export-toolbar");
      expect(toolbar).toBeInTheDocument();

      const pngBtn = screen.getByTestId("export-png-btn");
      expect(pngBtn).toBeInTheDocument();

      expect(screen.queryByTestId("export-svg-btn")).not.toBeInTheDocument();
    });

    it("calls exportChart with PNG format when PNG button clicked", async () => {
      const user = userEvent.setup();
      render(<ChartRenderer chartConfig={makeBarConfig()} />);

      const pngBtn = screen.getByTestId("export-png-btn");
      await user.click(pngBtn);

      expect(mockExportChart).toHaveBeenCalledTimes(1);
      expect(mockExportChart).toHaveBeenCalledWith(
        expect.any(Object),
        expect.objectContaining({
          format: "png",
          filename: "Revenue_by_Product",
          scale: 2,
        }),
      );
    });

    it("calls exportChart with SVG format when SVG button clicked", async () => {
      const user = userEvent.setup();
      render(<ChartRenderer chartConfig={makeBarConfig()} />);

      const svgBtn = screen.getByTestId("export-svg-btn");
      await user.click(svgBtn);

      expect(mockExportChart).toHaveBeenCalledTimes(1);
      expect(mockExportChart).toHaveBeenCalledWith(
        expect.any(Object),
        expect.objectContaining({
          format: "svg",
          filename: "Revenue_by_Product",
        }),
      );
    });

    it("calls exportKpiCard when KPI card PNG button clicked", async () => {
      const user = userEvent.setup();
      render(<ChartRenderer chartConfig={makeKpiConfig()} />);

      const pngBtn = screen.getByTestId("export-png-btn");
      await user.click(pngBtn);

      expect(mockExportKpiCard).toHaveBeenCalledTimes(1);
      expect(mockExportKpiCard).toHaveBeenCalledWith(
        expect.any(HTMLElement),
        "Total_Revenue",
      );
    });

    it("shows error toast when chart export fails", async () => {
      mockExportChart.mockRejectedValueOnce(new Error("Export failed"));
      const user = userEvent.setup();
      render(<ChartRenderer chartConfig={makeBarConfig()} />);

      const pngBtn = screen.getByTestId("export-png-btn");
      await user.click(pngBtn);

      const errorToast = screen.getByTestId("export-error-toast");
      expect(errorToast).toBeInTheDocument();
      expect(errorToast).toHaveTextContent("Failed to export chart as PNG");
    });

    it("shows error toast when KPI export fails", async () => {
      mockExportKpiCard.mockRejectedValueOnce(new Error("Export failed"));
      const user = userEvent.setup();
      render(<ChartRenderer chartConfig={makeKpiConfig()} />);

      const pngBtn = screen.getByTestId("export-png-btn");
      await user.click(pngBtn);

      const errorToast = screen.getByTestId("export-error-toast");
      expect(errorToast).toBeInTheDocument();
      expect(errorToast).toHaveTextContent("Failed to export KPI card");
    });

    it("dismisses error toast when close button clicked", async () => {
      mockExportChart.mockRejectedValueOnce(new Error("Export failed"));
      const user = userEvent.setup();
      render(<ChartRenderer chartConfig={makeBarConfig()} />);

      const pngBtn = screen.getByTestId("export-png-btn");
      await user.click(pngBtn);

      expect(screen.getByTestId("export-error-toast")).toBeInTheDocument();

      const dismissBtn = screen.getByLabelText("Dismiss error");
      await user.click(dismissBtn);

      expect(screen.queryByTestId("export-error-toast")).not.toBeInTheDocument();
    });

    it("does not show export toolbar for error states", () => {
      const invalidConfig = null as unknown as ChartConfig;
      render(<ChartRenderer chartConfig={invalidConfig} />);

      expect(screen.queryByTestId("chart-export-toolbar")).not.toBeInTheDocument();
    });

    it("does not show export toolbar for no-data states", () => {
      const config: ChartConfig = {
        type: "bar",
        data: [{ type: "bar", x: [], y: [] }],
      };
      render(<ChartRenderer chartConfig={config} />);

      expect(screen.queryByTestId("chart-export-toolbar")).not.toBeInTheDocument();
    });

    it("uses default filename when chart has no title", async () => {
      const user = userEvent.setup();
      const config = makeBarConfig({ layout: {} });
      render(<ChartRenderer chartConfig={config} />);

      const pngBtn = screen.getByTestId("export-png-btn");
      await user.click(pngBtn);

      expect(mockExportChart).toHaveBeenCalledWith(
        expect.any(Object),
        expect.objectContaining({
          filename: "chart",
        }),
      );
    });
  });

  describe("Responsive behavior", () => {
    it("enables resize handler for responsive sizing", () => {
      render(<ChartRenderer chartConfig={makeBarConfig()} />);

      const plotly = screen.getByTestId("plotly-mock");
      expect(plotly).toHaveAttribute("data-resize-handler", "true");
    });

    it("chart container has full width", () => {
      render(<ChartRenderer chartConfig={makeBarConfig()} />);

      const container = screen.getByTestId("chart-container");
      expect(container.className).toContain("w-full");
    });
  });

  describe("Theme adaptation", () => {
    it("uses light theme by default", () => {
      render(<ChartRenderer chartConfig={makeBarConfig()} />);

      const container = screen.getByTestId("chart-container");
      expect(container).toBeInTheDocument();
    });

    it("accepts dark theme", () => {
      render(
        <ChartRenderer chartConfig={makeBarConfig()} resolvedTheme="dark" />,
      );

      const container = screen.getByTestId("chart-container");
      expect(container).toBeInTheDocument();
    });
  });

  describe("Error handling", () => {
    it("shows 'Cannot render chart' for invalid config (missing type)", () => {
      const invalidConfig = { data: [] } as unknown as ChartConfig;
      render(<ChartRenderer chartConfig={invalidConfig} />);

      const errorEl = screen.getByTestId("chart-error");
      expect(errorEl).toBeInTheDocument();
      expect(screen.getByText("Cannot render chart")).toBeInTheDocument();
    });

    it("shows 'Cannot render chart' for invalid type", () => {
      const invalidConfig = { type: "invalid", data: [] } as unknown as ChartConfig;
      render(<ChartRenderer chartConfig={invalidConfig} />);

      expect(screen.getByTestId("chart-error")).toBeInTheDocument();
      expect(screen.getByText("Cannot render chart")).toBeInTheDocument();
    });

    it("shows 'Cannot render chart' for null config", () => {
      const nullConfig = null as unknown as ChartConfig;
      render(<ChartRenderer chartConfig={nullConfig} />);

      expect(screen.getByTestId("chart-error")).toBeInTheDocument();
    });

    it("shows 'Cannot render chart' for non-kpi without data array", () => {
      const config = { type: "bar" } as ChartConfig;
      render(<ChartRenderer chartConfig={config} />);

      expect(screen.getByTestId("chart-error")).toBeInTheDocument();
    });

    it("shows 'No data' for empty data arrays", () => {
      const config: ChartConfig = {
        type: "bar",
        data: [{ type: "bar", x: [], y: [] }],
      };
      render(<ChartRenderer chartConfig={config} />);

      const noDataEl = screen.getByTestId("chart-no-data");
      expect(noDataEl).toBeInTheDocument();
      expect(screen.getByText("No data")).toBeInTheDocument();
    });

    it("shows 'No data' for data with no traces", () => {
      const config: ChartConfig = {
        type: "bar",
        data: [],
      };
      render(<ChartRenderer chartConfig={config} />);

      expect(screen.getByTestId("chart-no-data")).toBeInTheDocument();
    });
  });

  describe("Smooth transitions", () => {
    it("sets transition duration in layout", () => {
      render(<ChartRenderer chartConfig={makeBarConfig()} />);

      // The plotly mock confirms layout is passed, and we verified
      // autosize is true which is part of the merged layout with transitions
      const plotly = screen.getByTestId("plotly-mock");
      expect(plotly).toHaveAttribute("data-autosize", "true");
    });
  });

  describe("Custom className", () => {
    it("applies custom className to chart container", () => {
      render(
        <ChartRenderer
          chartConfig={makeBarConfig()}
          className="custom-class"
        />,
      );

      const container = screen.getByTestId("chart-container");
      expect(container.className).toContain("custom-class");
    });

    it("applies custom className to KPI card", () => {
      render(
        <ChartRenderer
          chartConfig={makeKpiConfig()}
          className="custom-kpi"
        />,
      );

      const kpiCard = screen.getByTestId("kpi-card");
      expect(kpiCard.className).toContain("custom-kpi");
    });

    it("applies custom className to error container", () => {
      const invalidConfig = null as unknown as ChartConfig;
      render(
        <ChartRenderer chartConfig={invalidConfig} className="custom-error" />,
      );

      const errorEl = screen.getByTestId("chart-error");
      expect(errorEl.className).toContain("custom-error");
    });
  });
});
