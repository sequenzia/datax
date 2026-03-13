"""Tests for Plotly chart configuration generation.

Covers:
- Functional: Valid config for each chart type (line, bar, pie, scatter,
  histogram, KPI), titles from query context, axis labels from columns,
  color palette, KPI for single values, valid JSON for react-plotly.js
- Edge Cases: Long labels truncated, 10k+ points sampled, multiple
  numerics multi-trace, NULL values handled
- Error Handling: Invalid data -> fall back to table
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.chart_config import (
    COLOR_PALETTE,
    MAX_DATA_POINTS,
    MAX_LABEL_LENGTH,
    PlotlyConfig,
    _build_layout,
    _extract_column_values,
    _filter_null_pairs,
    _find_column_index,
    _sample_rows,
    _truncate_label,
    _truncate_labels,
    generate_chart_config,
)
from app.services.chart_heuristics import ChartRecommendation, ChartType

# ---------------------------------------------------------------------------
# PlotlyConfig dataclass
# ---------------------------------------------------------------------------


class TestPlotlyConfig:
    """Test PlotlyConfig dataclass and serialization."""

    def test_to_dict_basic(self) -> None:
        config = PlotlyConfig(
            data=[{"type": "bar", "x": [1], "y": [2]}],
            layout={"title": {"text": "Test"}},
            chart_type="bar",
        )
        d = config.to_dict()
        assert d["data"] == [{"type": "bar", "x": [1], "y": [2]}]
        assert d["layout"]["title"]["text"] == "Test"
        assert d["chart_type"] == "bar"
        assert d["is_fallback"] is False

    def test_to_dict_fallback(self) -> None:
        config = PlotlyConfig(
            data=[],
            layout={},
            chart_type="table",
            is_fallback=True,
        )
        d = config.to_dict()
        assert d["is_fallback"] is True
        assert d["chart_type"] == "table"

    def test_default_values(self) -> None:
        config = PlotlyConfig()
        assert config.data == []
        assert config.layout == {}
        assert config.chart_type == "table"
        assert config.is_fallback is False


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestTruncateLabel:
    """Test label truncation."""

    def test_short_label_unchanged(self) -> None:
        assert _truncate_label("Hello") == "Hello"

    def test_exact_length_unchanged(self) -> None:
        label = "A" * MAX_LABEL_LENGTH
        assert _truncate_label(label) == label

    def test_long_label_truncated(self) -> None:
        label = "A" * (MAX_LABEL_LENGTH + 10)
        result = _truncate_label(label)
        assert len(result) == MAX_LABEL_LENGTH
        assert result.endswith("...")

    def test_custom_max_length(self) -> None:
        result = _truncate_label("Hello World", max_length=8)
        assert result == "Hello..."
        assert len(result) == 8


class TestTruncateLabels:
    """Test batch label truncation."""

    def test_truncates_long_labels(self) -> None:
        labels = ["Short", "A" * 50, None, 42]
        result = _truncate_labels(labels)
        assert result[0] == "Short"
        assert len(result[1]) == MAX_LABEL_LENGTH
        assert result[1].endswith("...")
        assert result[2] == ""
        assert result[3] == "42"


class TestSampleRows:
    """Test row sampling for large datasets."""

    def test_small_dataset_unchanged(self) -> None:
        rows = [[i] for i in range(100)]
        result = _sample_rows(rows)
        assert len(result) == 100
        assert result is rows  # Same object, not copied

    def test_exact_max_unchanged(self) -> None:
        rows = [[i] for i in range(MAX_DATA_POINTS)]
        result = _sample_rows(rows)
        assert len(result) == MAX_DATA_POINTS

    def test_large_dataset_sampled(self) -> None:
        rows = [[i] for i in range(MAX_DATA_POINTS + 5000)]
        result = _sample_rows(rows)
        assert len(result) == MAX_DATA_POINTS

    def test_sample_preserves_first_element(self) -> None:
        rows = [[i] for i in range(MAX_DATA_POINTS * 2)]
        result = _sample_rows(rows)
        assert result[0] == [0]

    def test_sample_includes_range_spread(self) -> None:
        """Sampled data should span the full range, not just early values."""
        n = MAX_DATA_POINTS * 3
        rows = [[i] for i in range(n)]
        result = _sample_rows(rows)
        # Last sampled value should be near the end of the original range
        last_val = result[-1][0]
        assert last_val > n * 0.9


class TestExtractColumnValues:
    """Test column value extraction."""

    def test_basic_extraction(self) -> None:
        rows = [[1, "a"], [2, "b"], [3, "c"]]
        assert _extract_column_values(rows, 0) == [1, 2, 3]
        assert _extract_column_values(rows, 1) == ["a", "b", "c"]

    def test_out_of_range_index(self) -> None:
        rows = [[1], [2]]
        result = _extract_column_values(rows, 5)
        assert result == [None, None]

    def test_empty_rows(self) -> None:
        assert _extract_column_values([], 0) == []


class TestFilterNullPairs:
    """Test NULL pair filtering."""

    def test_no_nulls(self) -> None:
        x, y = _filter_null_pairs([1, 2, 3], [4, 5, 6])
        assert x == [1, 2, 3]
        assert y == [4, 5, 6]

    def test_null_x(self) -> None:
        x, y = _filter_null_pairs([1, None, 3], [4, 5, 6])
        assert x == [1, 3]
        assert y == [4, 6]

    def test_null_y(self) -> None:
        x, y = _filter_null_pairs([1, 2, 3], [4, None, 6])
        assert x == [1, 3]
        assert y == [4, 6]

    def test_both_null(self) -> None:
        x, y = _filter_null_pairs([None, 2], [None, 5])
        assert x == [2]
        assert y == [5]

    def test_all_null(self) -> None:
        x, y = _filter_null_pairs([None, None], [None, None])
        assert x == []
        assert y == []


class TestFindColumnIndex:
    """Test column index lookup."""

    def test_found(self) -> None:
        assert _find_column_index(["a", "b", "c"], "b") == 1

    def test_case_insensitive(self) -> None:
        assert _find_column_index(["Name", "Value"], "name") == 0

    def test_not_found(self) -> None:
        assert _find_column_index(["a", "b"], "z") is None

    def test_none_name(self) -> None:
        assert _find_column_index(["a", "b"], None) is None


class TestBuildLayout:
    """Test layout construction."""

    def test_basic_layout(self) -> None:
        layout = _build_layout("My Title")
        assert layout["title"]["text"] == "My Title"
        assert "autosize" in layout
        assert "colorway" in layout

    def test_with_axis_labels(self) -> None:
        layout = _build_layout("Title", x_label="X Axis", y_label="Y Axis")
        assert layout["xaxis"]["title"]["text"] == "X Axis"
        assert layout["yaxis"]["title"]["text"] == "Y Axis"

    def test_without_axis_labels(self) -> None:
        layout = _build_layout("Title")
        assert "xaxis" not in layout
        assert "yaxis" not in layout

    def test_extra_params_merged(self) -> None:
        layout = _build_layout("Title", extra={"barmode": "group"})
        assert layout["barmode"] == "group"


# ---------------------------------------------------------------------------
# Functional: Line chart configuration
# ---------------------------------------------------------------------------


class TestLineChartConfig:
    """Line chart should produce valid Plotly config."""

    def test_basic_line_chart(self) -> None:
        columns = ["date", "revenue"]
        rows = [
            ["2024-01-01", 100],
            ["2024-01-02", 200],
            ["2024-01-03", 300],
        ]
        config = generate_chart_config(
            columns, rows, ["DATE", "FLOAT"],
        )
        assert config.chart_type == "line"
        assert len(config.data) >= 1
        trace = config.data[0]
        assert trace["type"] == "scatter"
        assert trace["mode"] == "lines+markers"
        assert len(trace["x"]) == 3
        assert len(trace["y"]) == 3
        assert config.layout["title"]["text"]

    def test_line_chart_with_title(self) -> None:
        columns = ["month", "sales"]
        rows = [["Jan", 10], ["Feb", 20]]
        config = generate_chart_config(
            columns, rows, ["DATE", "FLOAT"],
            title="Monthly Sales Trend",
        )
        assert config.layout["title"]["text"] == "Monthly Sales Trend"

    def test_line_chart_axis_labels(self) -> None:
        columns = ["date", "revenue"]
        rows = [["2024-01-01", 100], ["2024-01-02", 200]]
        config = generate_chart_config(
            columns, rows, ["DATE", "FLOAT"],
        )
        assert "xaxis" in config.layout
        assert config.layout["xaxis"]["title"]["text"] == "date"

    def test_line_chart_color_palette(self) -> None:
        columns = ["date", "revenue"]
        rows = [["2024-01-01", 100], ["2024-01-02", 200]]
        config = generate_chart_config(
            columns, rows, ["DATE", "FLOAT"],
        )
        trace = config.data[0]
        assert trace["marker"]["color"] in COLOR_PALETTE


# ---------------------------------------------------------------------------
# Functional: Bar chart configuration
# ---------------------------------------------------------------------------


class TestBarChartConfig:
    """Bar chart should produce valid Plotly config."""

    def test_basic_bar_chart(self) -> None:
        columns = ["department", "count"]
        rows = [
            ["Engineering", 50],
            ["Marketing", 30],
            ["Sales", 40],
            ["HR", 20],
            ["Finance", 25],
            ["Legal", 15],
            ["Support", 35],
            ["Operations", 28],
            ["Product", 22],
            ["Design", 18],
            ["QA", 12],
        ]
        config = generate_chart_config(
            columns, rows, ["VARCHAR", "INTEGER"],
        )
        assert config.chart_type == "bar"
        assert len(config.data) >= 1
        trace = config.data[0]
        assert trace["type"] == "bar"
        assert len(trace["x"]) == 11

    def test_bar_chart_axis_labels(self) -> None:
        columns = ["category", "value"]
        rows = [["A", 10], ["B", 20], ["C", 30]] + [
            [f"Cat{i}", i] for i in range(10)
        ]
        config = generate_chart_config(
            columns, rows, ["VARCHAR", "INTEGER"],
        )
        assert config.layout["xaxis"]["title"]["text"] == "category"
        assert config.layout["yaxis"]["title"]["text"] == "value"


# ---------------------------------------------------------------------------
# Functional: Pie chart configuration
# ---------------------------------------------------------------------------


class TestPieChartConfig:
    """Pie chart should produce valid Plotly config."""

    def test_basic_pie_chart(self) -> None:
        columns = ["region", "sales"]
        rows = [
            ["North", 400],
            ["South", 300],
            ["East", 200],
            ["West", 100],
        ]
        config = generate_chart_config(
            columns, rows, ["VARCHAR", "INTEGER"],
        )
        assert config.chart_type == "pie"
        assert len(config.data) == 1
        trace = config.data[0]
        assert trace["type"] == "pie"
        assert trace["labels"] == ["North", "South", "East", "West"]
        assert trace["values"] == [400, 300, 200, 100]

    def test_pie_chart_has_hole(self) -> None:
        """Pie charts should be donut-style with a hole."""
        columns = ["type", "count"]
        rows = [["A", 10], ["B", 20], ["C", 30]]
        config = generate_chart_config(
            columns, rows, ["VARCHAR", "INTEGER"],
        )
        assert config.data[0]["hole"] == 0.3

    def test_pie_chart_no_axes(self) -> None:
        """Pie charts should not have axis labels."""
        columns = ["type", "count"]
        rows = [["A", 10], ["B", 20], ["C", 30]]
        config = generate_chart_config(
            columns, rows, ["VARCHAR", "INTEGER"],
        )
        assert "xaxis" not in config.layout
        assert "yaxis" not in config.layout


# ---------------------------------------------------------------------------
# Functional: Scatter plot configuration
# ---------------------------------------------------------------------------


class TestScatterChartConfig:
    """Scatter plot should produce valid Plotly config."""

    def test_basic_scatter(self) -> None:
        columns = ["height", "weight"]
        rows = [
            [170, 65],
            [180, 80],
            [160, 55],
            [175, 70],
        ]
        config = generate_chart_config(
            columns, rows, ["FLOAT", "FLOAT"],
        )
        assert config.chart_type == "scatter"
        assert len(config.data) == 1
        trace = config.data[0]
        assert trace["type"] == "scatter"
        assert trace["mode"] == "markers"
        assert len(trace["x"]) == 4
        assert len(trace["y"]) == 4

    def test_scatter_axis_labels(self) -> None:
        columns = ["height", "weight"]
        rows = [[170, 65], [180, 80]]
        config = generate_chart_config(
            columns, rows, ["FLOAT", "FLOAT"],
        )
        assert config.layout["xaxis"]["title"]["text"] == "height"
        assert config.layout["yaxis"]["title"]["text"] == "weight"


# ---------------------------------------------------------------------------
# Functional: Histogram configuration
# ---------------------------------------------------------------------------


class TestHistogramConfig:
    """Histogram should produce valid Plotly config."""

    def test_basic_histogram(self) -> None:
        columns = ["score"]
        rows = [[i] for i in range(50)]
        config = generate_chart_config(
            columns, rows, ["FLOAT"],
        )
        assert config.chart_type == "histogram"
        assert len(config.data) == 1
        trace = config.data[0]
        assert trace["type"] == "histogram"
        assert len(trace["x"]) == 50

    def test_histogram_axis_labels(self) -> None:
        columns = ["age"]
        rows = [[25], [30], [35], [40]]
        config = generate_chart_config(
            columns, rows, ["INTEGER"],
        )
        assert config.layout["xaxis"]["title"]["text"] == "age"
        assert config.layout["yaxis"]["title"]["text"] == "Count"


# ---------------------------------------------------------------------------
# Functional: KPI configuration
# ---------------------------------------------------------------------------


class TestKPIConfig:
    """KPI cards should produce valid Plotly indicator config."""

    def test_single_value_kpi(self) -> None:
        columns = ["total_revenue"]
        rows = [[42000]]
        config = generate_chart_config(
            columns, rows, ["INTEGER"],
        )
        assert config.chart_type == "kpi"
        assert len(config.data) == 1
        trace = config.data[0]
        assert trace["type"] == "indicator"
        assert trace["mode"] == "number"
        assert trace["value"] == 42000
        assert trace["title"]["text"] == "total_revenue"

    def test_multi_value_kpi(self) -> None:
        columns = ["count", "average", "max"]
        rows = [[100, 45.5, 99]]
        config = generate_chart_config(
            columns, rows, ["INTEGER", "FLOAT", "INTEGER"],
        )
        assert config.chart_type == "kpi"
        assert len(config.data) == 3
        assert config.data[0]["value"] == 100
        assert config.data[1]["value"] == 45.5
        assert config.data[2]["value"] == 99

    def test_kpi_no_axes(self) -> None:
        """KPI cards should not have axis labels."""
        columns = ["total"]
        rows = [[42]]
        config = generate_chart_config(
            columns, rows, ["INTEGER"],
        )
        assert "xaxis" not in config.layout
        assert "yaxis" not in config.layout

    def test_kpi_non_numeric_single_row(self) -> None:
        """Single row with non-numeric should still be KPI."""
        columns = ["status"]
        rows = [["active"]]
        config = generate_chart_config(
            columns, rows, ["VARCHAR"],
        )
        assert config.chart_type == "kpi"
        assert config.data[0]["value"] == "active"


# ---------------------------------------------------------------------------
# Functional: Title from query context
# ---------------------------------------------------------------------------


class TestTitleFromQueryContext:
    """Titles should be derived from query context when available."""

    def test_explicit_title(self) -> None:
        columns = ["x", "y"]
        rows = [[1, 2], [3, 4]]
        config = generate_chart_config(
            columns, rows, ["FLOAT", "FLOAT"],
            title="My Custom Title",
        )
        assert config.layout["title"]["text"] == "My Custom Title"

    def test_query_context_as_title(self) -> None:
        columns = ["x", "y"]
        rows = [[1, 2], [3, 4]]
        config = generate_chart_config(
            columns, rows, ["FLOAT", "FLOAT"],
            query_context="Revenue by quarter for 2024",
        )
        assert config.layout["title"]["text"] == "Revenue by quarter for 2024"

    def test_explicit_title_beats_context(self) -> None:
        columns = ["x", "y"]
        rows = [[1, 2], [3, 4]]
        config = generate_chart_config(
            columns, rows, ["FLOAT", "FLOAT"],
            title="Explicit Title",
            query_context="Query Context Title",
        )
        assert config.layout["title"]["text"] == "Explicit Title"


# ---------------------------------------------------------------------------
# Functional: Valid JSON for react-plotly.js
# ---------------------------------------------------------------------------


class TestValidPlotlyJSON:
    """Output must be valid JSON renderable by react-plotly.js."""

    def test_to_dict_serializable(self) -> None:
        """The to_dict output should be JSON-serializable."""
        import json

        columns = ["date", "value"]
        rows = [["2024-01-01", 100], ["2024-01-02", 200]]
        config = generate_chart_config(
            columns, rows, ["DATE", "FLOAT"],
        )
        d = config.to_dict()
        serialized = json.dumps(d)
        assert isinstance(serialized, str)
        parsed = json.loads(serialized)
        assert "data" in parsed
        assert "layout" in parsed

    def test_has_data_and_layout(self) -> None:
        """Every config must have data and layout keys."""
        columns = ["x", "y"]
        rows = [[1, 2]]
        config = generate_chart_config(columns, rows, ["FLOAT", "FLOAT"])
        d = config.to_dict()
        assert "data" in d
        assert "layout" in d
        assert isinstance(d["data"], list)
        assert isinstance(d["layout"], dict)


# ---------------------------------------------------------------------------
# Functional: Color palette
# ---------------------------------------------------------------------------


class TestColorPalette:
    """Charts should use the consistent color palette."""

    def test_line_chart_uses_palette(self) -> None:
        columns = ["date", "a", "b"]
        rows = [["2024-01-01", 1, 2], ["2024-01-02", 3, 4]]
        recommendation = ChartRecommendation(
            chart_type=ChartType.LINE,
            reasoning="Time series",
            x_column="date",
            y_column=None,  # Let it detect all numerics
        )
        config = generate_chart_config(
            columns, rows, ["DATE", "FLOAT", "FLOAT"],
            recommendation=recommendation,
        )
        for i, trace in enumerate(config.data):
            assert trace["marker"]["color"] == COLOR_PALETTE[i % len(COLOR_PALETTE)]

    def test_bar_chart_uses_palette(self) -> None:
        columns = ["cat", "val"]
        rows = [["A", 10], ["B", 20], ["C", 30]] + [
            [f"Cat{i}", i] for i in range(10)
        ]
        config = generate_chart_config(
            columns, rows, ["VARCHAR", "INTEGER"],
        )
        assert config.data[0]["marker"]["color"] == COLOR_PALETTE[0]


# ---------------------------------------------------------------------------
# Edge Case: Long labels truncated
# ---------------------------------------------------------------------------


class TestLongLabelsTruncated:
    """Long category labels should be truncated in charts."""

    def test_bar_chart_truncates_x_labels(self) -> None:
        long_label = "A" * 60
        columns = ["category", "value"]
        rows = [[long_label, 100]] + [[f"Cat{i}", i] for i in range(15)]
        config = generate_chart_config(
            columns, rows, ["VARCHAR", "INTEGER"],
        )
        x_labels = config.data[0]["x"]
        for label in x_labels:
            assert len(label) <= MAX_LABEL_LENGTH

    def test_pie_chart_truncates_labels(self) -> None:
        long_label = "B" * 60
        columns = ["category", "value"]
        rows = [[long_label, 100], ["Short", 200], ["Medium", 300]]
        config = generate_chart_config(
            columns, rows, ["VARCHAR", "INTEGER"],
        )
        labels = config.data[0]["labels"]
        for label in labels:
            assert len(label) <= MAX_LABEL_LENGTH


# ---------------------------------------------------------------------------
# Edge Case: 10k+ points sampled
# ---------------------------------------------------------------------------


class TestLargeDatasetSampled:
    """Datasets exceeding MAX_DATA_POINTS should be sampled."""

    def test_large_scatter_sampled(self) -> None:
        n = MAX_DATA_POINTS + 5000
        columns = ["x", "y"]
        rows = [[i, i * 2] for i in range(n)]
        config = generate_chart_config(
            columns, rows, ["FLOAT", "FLOAT"],
        )
        # Data should be sampled down
        assert len(config.data[0]["x"]) <= MAX_DATA_POINTS

    def test_large_histogram_sampled(self) -> None:
        n = MAX_DATA_POINTS + 1000
        columns = ["value"]
        rows = [[i] for i in range(n)]
        config = generate_chart_config(
            columns, rows, ["FLOAT"],
        )
        assert len(config.data[0]["x"]) <= MAX_DATA_POINTS


# ---------------------------------------------------------------------------
# Edge Case: Multiple numerics -> multi-trace
# ---------------------------------------------------------------------------


class TestMultipleNumericsMultiTrace:
    """Multiple numeric columns should produce multi-trace charts."""

    def test_line_chart_multi_trace(self) -> None:
        columns = ["date", "revenue", "profit"]
        rows = [
            ["2024-01-01", 100, 30],
            ["2024-01-02", 200, 60],
            ["2024-01-03", 300, 90],
        ]
        recommendation = ChartRecommendation(
            chart_type=ChartType.LINE,
            reasoning="Time series",
            x_column="date",
            y_column=None,
        )
        config = generate_chart_config(
            columns, rows, ["DATE", "FLOAT", "FLOAT"],
            recommendation=recommendation,
        )
        assert config.chart_type == "line"
        assert len(config.data) == 2
        assert config.data[0]["name"] == "revenue"
        assert config.data[1]["name"] == "profit"

    def test_bar_chart_multi_trace_grouped(self) -> None:
        columns = ["quarter", "revenue", "costs"]
        rows = [
            ["Q1", 100, 80],
            ["Q2", 200, 150],
            ["Q3", 300, 220],
        ] + [[f"Q{i}", i * 10, i * 8] for i in range(4, 15)]
        recommendation = ChartRecommendation(
            chart_type=ChartType.BAR,
            reasoning="Categorical",
            x_column="quarter",
            y_column=None,
        )
        config = generate_chart_config(
            columns, rows, ["VARCHAR", "INTEGER", "INTEGER"],
            recommendation=recommendation,
        )
        assert config.chart_type == "bar"
        assert len(config.data) == 2
        assert config.layout.get("barmode") == "group"


# ---------------------------------------------------------------------------
# Edge Case: NULL values handled
# ---------------------------------------------------------------------------


class TestNullValuesHandled:
    """NULL values should be handled gracefully in all chart types."""

    def test_line_chart_skips_nulls(self) -> None:
        columns = ["date", "value"]
        rows = [
            ["2024-01-01", 100],
            ["2024-01-02", None],
            ["2024-01-03", 300],
        ]
        recommendation = ChartRecommendation(
            chart_type=ChartType.LINE,
            reasoning="Time series",
            x_column="date",
            y_column="value",
        )
        config = generate_chart_config(
            columns, rows, ["DATE", "FLOAT"],
            recommendation=recommendation,
        )
        trace = config.data[0]
        # NULL pairs should be filtered
        assert None not in trace["y"]
        assert len(trace["x"]) == 2
        assert len(trace["y"]) == 2

    def test_scatter_skips_nulls(self) -> None:
        columns = ["x", "y"]
        rows = [[1, None], [2, 20], [None, 30], [4, 40]]
        recommendation = ChartRecommendation(
            chart_type=ChartType.SCATTER,
            reasoning="Two numerics",
            x_column="x",
            y_column="y",
        )
        config = generate_chart_config(
            columns, rows, ["FLOAT", "FLOAT"],
            recommendation=recommendation,
        )
        trace = config.data[0]
        assert None not in trace["x"]
        assert None not in trace["y"]
        assert len(trace["x"]) == 2

    def test_pie_chart_skips_null_values(self) -> None:
        columns = ["category", "value"]
        rows = [["A", 100], ["B", None], ["C", 300]]
        recommendation = ChartRecommendation(
            chart_type=ChartType.PIE,
            reasoning="Proportional",
            x_column="category",
            y_column="value",
        )
        config = generate_chart_config(
            columns, rows, ["VARCHAR", "INTEGER"],
            recommendation=recommendation,
        )
        trace = config.data[0]
        assert None not in trace["values"]
        assert len(trace["labels"]) == 2
        assert len(trace["values"]) == 2

    def test_histogram_skips_nulls(self) -> None:
        columns = ["value"]
        rows = [[10], [None], [30], [None], [50]]
        recommendation = ChartRecommendation(
            chart_type=ChartType.HISTOGRAM,
            reasoning="Distribution",
            x_column="value",
        )
        config = generate_chart_config(
            columns, rows, ["FLOAT"],
            recommendation=recommendation,
        )
        trace = config.data[0]
        assert None not in trace["x"]
        assert len(trace["x"]) == 3

    def test_all_null_falls_to_table(self) -> None:
        columns = ["value"]
        rows = [[None], [None], [None]]
        config = generate_chart_config(columns, rows)
        assert config.chart_type == "table"
        assert config.is_fallback is True


# ---------------------------------------------------------------------------
# Error Handling: Invalid data -> fall back to table
# ---------------------------------------------------------------------------


class TestInvalidDataFallback:
    """Invalid or unchartable data should produce a table fallback."""

    def test_empty_data(self) -> None:
        config = generate_chart_config([], [])
        assert config.chart_type == "table"
        assert config.is_fallback is True

    def test_no_numeric_columns(self) -> None:
        columns = ["name", "city"]
        rows = [["Alice", "NYC"], ["Bob", "LA"]]
        config = generate_chart_config(
            columns, rows, ["VARCHAR", "VARCHAR"],
        )
        assert config.chart_type == "table"
        assert config.is_fallback is True

    def test_fallback_has_reasoning(self) -> None:
        config = generate_chart_config([], [])
        assert "annotations" in config.layout
        assert len(config.layout["annotations"]) > 0


# ---------------------------------------------------------------------------
# Integration: Full pipeline with auto-recommendation
# ---------------------------------------------------------------------------


class TestFullPipeline:
    """Test the full pipeline without pre-computed recommendation."""

    def test_auto_detects_line_chart(self) -> None:
        columns = ["date", "revenue"]
        rows = [
            ["2024-01-01", 100],
            ["2024-01-02", 200],
            ["2024-01-03", 300],
        ]
        config = generate_chart_config(columns, rows, ["DATE", "FLOAT"])
        assert config.chart_type == "line"
        assert config.is_fallback is False

    def test_auto_detects_bar_chart(self) -> None:
        columns = ["department", "employee_count"]
        rows = [
            [f"Dept_{i}", i * 10]
            for i in range(15)
        ]
        config = generate_chart_config(columns, rows, ["VARCHAR", "INTEGER"])
        assert config.chart_type == "bar"

    def test_auto_detects_kpi(self) -> None:
        columns = ["total"]
        rows = [[42]]
        config = generate_chart_config(columns, rows, ["INTEGER"])
        assert config.chart_type == "kpi"

    def test_auto_detects_scatter(self) -> None:
        columns = ["height", "weight"]
        rows = [[170, 65], [180, 80], [160, 55]]
        config = generate_chart_config(columns, rows, ["FLOAT", "FLOAT"])
        assert config.chart_type == "scatter"

    def test_auto_detects_histogram(self) -> None:
        columns = ["score"]
        rows = [[i] for i in range(50)]
        config = generate_chart_config(columns, rows, ["FLOAT"])
        assert config.chart_type == "histogram"

    def test_with_recommendation_override(self) -> None:
        """Using a pre-computed recommendation should use the specified type."""
        columns = ["x", "y"]
        rows = [[1, 2], [3, 4]]
        recommendation = ChartRecommendation(
            chart_type=ChartType.BAR,
            reasoning="User requested bar",
            x_column="x",
            y_column="y",
        )
        config = generate_chart_config(
            columns, rows, ["FLOAT", "FLOAT"],
            recommendation=recommendation,
        )
        assert config.chart_type == "bar"


# ---------------------------------------------------------------------------
# Layout consistency checks
# ---------------------------------------------------------------------------


class TestLayoutConsistency:
    """All charts should have consistent layout properties."""

    @pytest.mark.parametrize("chart_data", [
        {
            "columns": ["date", "value"],
            "rows": [["2024-01-01", 10], ["2024-01-02", 20]],
            "types": ["DATE", "FLOAT"],
        },
        {
            "columns": ["height", "weight"],
            "rows": [[170, 65], [180, 80]],
            "types": ["FLOAT", "FLOAT"],
        },
        {
            "columns": ["score"],
            "rows": [[i] for i in range(10)],
            "types": ["FLOAT"],
        },
    ])
    def test_layout_has_autosize(self, chart_data: dict[str, Any]) -> None:
        config = generate_chart_config(
            chart_data["columns"],
            chart_data["rows"],
            chart_data["types"],
        )
        if not config.is_fallback:
            assert config.layout.get("autosize") is True

    @pytest.mark.parametrize("chart_data", [
        {
            "columns": ["date", "value"],
            "rows": [["2024-01-01", 10], ["2024-01-02", 20]],
            "types": ["DATE", "FLOAT"],
        },
        {
            "columns": ["height", "weight"],
            "rows": [[170, 65], [180, 80]],
            "types": ["FLOAT", "FLOAT"],
        },
    ])
    def test_layout_has_font(self, chart_data: dict[str, Any]) -> None:
        config = generate_chart_config(
            chart_data["columns"],
            chart_data["rows"],
            chart_data["types"],
        )
        if not config.is_fallback:
            assert "font" in config.layout
            assert "family" in config.layout["font"]

    @pytest.mark.parametrize("chart_data", [
        {
            "columns": ["date", "value"],
            "rows": [["2024-01-01", 10], ["2024-01-02", 20]],
            "types": ["DATE", "FLOAT"],
        },
    ])
    def test_layout_has_transparent_bg(self, chart_data: dict[str, Any]) -> None:
        config = generate_chart_config(
            chart_data["columns"],
            chart_data["rows"],
            chart_data["types"],
        )
        if not config.is_fallback:
            assert config.layout.get("paper_bgcolor") == "rgba(0,0,0,0)"
            assert config.layout.get("plot_bgcolor") == "rgba(0,0,0,0)"
