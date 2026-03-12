"""Plotly chart configuration generator.

Transforms query results and chart type recommendations into valid
Plotly.js JSON configurations renderable by react-plotly.js. Supports
line, bar, pie, scatter, histogram, and KPI chart types.

The generator handles:
- Data trace construction for each chart type
- Layout configuration (titles, axis labels, color palette)
- Edge cases: NULL values filtered, long labels truncated,
  large datasets sampled, multiple numeric columns as multi-trace
- Fallback to table display when data is invalid for charting

The output structure matches the Plotly.js Figure schema:
  {"data": [...traces], "layout": {...}}

This is consumed by the frontend's react-plotly.js component and
streamed as a ``chart_config`` SSE event during conversations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from app.logging import get_logger
from app.services.chart_heuristics import (
    ChartRecommendation,
    ChartType,
    analyze_columns,
    recommend_chart_type,
)

logger = get_logger(__name__)

# Maximum label length before truncation (axis tick labels, legend entries)
MAX_LABEL_LENGTH = 40

# Maximum data points before sampling kicks in
MAX_DATA_POINTS = 10_000

# Consistent color palette for chart traces
COLOR_PALETTE = [
    "#636EFA",  # blue
    "#EF553B",  # red
    "#00CC96",  # green
    "#AB63FA",  # purple
    "#FFA15A",  # orange
    "#19D3F3",  # cyan
    "#FF6692",  # pink
    "#B6E880",  # lime
    "#FF97FF",  # magenta
    "#FECB52",  # yellow
]

# Default layout settings shared across all chart types
_BASE_LAYOUT: dict[str, Any] = {
    "autosize": True,
    "margin": {"l": 60, "r": 30, "t": 50, "b": 60},
    "font": {"family": "Inter, system-ui, sans-serif", "size": 12},
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor": "rgba(0,0,0,0)",
    "colorway": COLOR_PALETTE,
    "hovermode": "closest",
}


@dataclass
class PlotlyConfig:
    """A complete Plotly.js figure configuration.

    Attributes:
        data: List of Plotly trace objects.
        layout: Plotly layout object.
        chart_type: The chart type used (for frontend metadata).
        is_fallback: True if the config is a fallback (e.g., table).
    """

    data: list[dict[str, Any]] = field(default_factory=list)
    layout: dict[str, Any] = field(default_factory=dict)
    chart_type: str = "table"
    is_fallback: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary for react-plotly.js."""
        return {
            "data": self.data,
            "layout": self.layout,
            "chart_type": self.chart_type,
            "is_fallback": self.is_fallback,
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_chart_config(
    columns: list[str],
    rows: list[list[Any]],
    column_types: list[str] | None = None,
    title: str | None = None,
    recommendation: ChartRecommendation | None = None,
    query_context: str | None = None,
) -> PlotlyConfig:
    """Generate a Plotly.js chart configuration from query results.

    Args:
        columns: Column names from the query result.
        rows: Row data (list of lists).
        column_types: Optional data type strings for each column.
        title: Optional chart title. If not provided, derived from
            query context or column names.
        recommendation: Pre-computed chart recommendation. If None,
            one is computed via ``recommend_chart_type``.
        query_context: Optional natural language description of the
            query (used for generating titles).

    Returns:
        A PlotlyConfig with data traces and layout ready for
        react-plotly.js rendering.
    """
    if recommendation is None:
        recommendation = recommend_chart_type(columns, rows, column_types)

    chart_type = recommendation.chart_type

    # Table and uncharted types get a fallback
    if chart_type == ChartType.TABLE:
        return _build_fallback(recommendation, title, query_context)

    # Build chart title
    chart_title = _resolve_title(title, query_context, recommendation, columns)

    # Sample large datasets
    sampled_rows = _sample_rows(rows)

    # Dispatch to chart-type-specific builders
    builders: dict[ChartType, Any] = {
        ChartType.LINE: _build_line_config,
        ChartType.BAR: _build_bar_config,
        ChartType.PIE: _build_pie_config,
        ChartType.SCATTER: _build_scatter_config,
        ChartType.HISTOGRAM: _build_histogram_config,
        ChartType.KPI: _build_kpi_config,
    }

    builder = builders.get(chart_type)
    if builder is None:
        logger.warning("unsupported_chart_type", chart_type=str(chart_type))
        return _build_fallback(recommendation, title, query_context)

    try:
        config = builder(
            columns=columns,
            rows=sampled_rows,
            recommendation=recommendation,
            title=chart_title,
            column_types=column_types,
        )
        return config
    except Exception as exc:
        logger.error(
            "chart_config_generation_failed",
            chart_type=str(chart_type),
            error=str(exc),
        )
        return _build_fallback(recommendation, title, query_context)


# ---------------------------------------------------------------------------
# Title resolution
# ---------------------------------------------------------------------------


def _resolve_title(
    explicit_title: str | None,
    query_context: str | None,
    recommendation: ChartRecommendation,
    columns: list[str],
) -> str:
    """Determine the chart title from available context.

    Priority: explicit title > query context > generated from columns.
    """
    if explicit_title:
        return _truncate_label(explicit_title, 80)

    if query_context:
        return _truncate_label(query_context, 80)

    # Generate from recommendation and columns
    if recommendation.y_column and recommendation.x_column:
        return f"{recommendation.y_column} by {recommendation.x_column}"
    if recommendation.y_column:
        return recommendation.y_column
    if columns:
        return " vs ".join(columns[:2])

    return "Query Results"


# ---------------------------------------------------------------------------
# Data extraction helpers
# ---------------------------------------------------------------------------


def _extract_column_values(
    rows: list[list[Any]],
    col_index: int,
) -> list[Any]:
    """Extract values for a column index from rows, preserving order."""
    values: list[Any] = []
    for row in rows:
        if col_index < len(row):
            values.append(row[col_index])
        else:
            values.append(None)
    return values


def _filter_null_pairs(
    x_values: list[Any],
    y_values: list[Any],
) -> tuple[list[Any], list[Any]]:
    """Remove pairs where either x or y is None.

    Returns filtered x and y lists of equal length.
    """
    filtered_x: list[Any] = []
    filtered_y: list[Any] = []
    for x, y in zip(x_values, y_values):
        if x is not None and y is not None:
            filtered_x.append(x)
            filtered_y.append(y)
    return filtered_x, filtered_y


def _find_column_index(columns: list[str], name: str | None) -> int | None:
    """Find the index of a column by name, case-insensitive."""
    if name is None:
        return None
    lower = name.lower()
    for i, col in enumerate(columns):
        if col.lower() == lower:
            return i
    return None


def _truncate_label(label: str, max_length: int = MAX_LABEL_LENGTH) -> str:
    """Truncate a label string, adding ellipsis if needed."""
    if len(label) <= max_length:
        return label
    return label[: max_length - 3] + "..."


def _truncate_labels(labels: list[Any]) -> list[str]:
    """Truncate a list of label values to strings with max length."""
    result: list[str] = []
    for label in labels:
        s = str(label) if label is not None else ""
        result.append(_truncate_label(s))
    return result


def _sample_rows(rows: list[list[Any]]) -> list[list[Any]]:
    """Sample rows if the dataset exceeds MAX_DATA_POINTS.

    Uses systematic sampling (every Nth row) to maintain data
    distribution across the full range.
    """
    if len(rows) <= MAX_DATA_POINTS:
        return rows

    step = len(rows) / MAX_DATA_POINTS
    sampled: list[list[Any]] = []
    index = 0.0
    while len(sampled) < MAX_DATA_POINTS and int(index) < len(rows):
        sampled.append(rows[int(index)])
        index += step

    logger.info(
        "chart_data_sampled",
        original_count=len(rows),
        sampled_count=len(sampled),
    )
    return sampled


# ---------------------------------------------------------------------------
# Layout builder
# ---------------------------------------------------------------------------


def _build_layout(
    title: str,
    x_label: str | None = None,
    y_label: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a Plotly layout dict with title, axis labels, and defaults."""
    layout = {**_BASE_LAYOUT}
    layout["title"] = {"text": title, "font": {"size": 16}}

    if x_label is not None:
        layout["xaxis"] = {"title": {"text": x_label}}
    if y_label is not None:
        layout["yaxis"] = {"title": {"text": y_label}}

    if extra:
        layout.update(extra)

    return layout


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------


def _build_line_config(
    columns: list[str],
    rows: list[list[Any]],
    recommendation: ChartRecommendation,
    title: str,
    column_types: list[str] | None = None,
) -> PlotlyConfig:
    """Build a Plotly line chart configuration.

    Supports multi-trace when multiple numeric columns are present.
    """
    x_idx = _find_column_index(columns, recommendation.x_column)
    if x_idx is None:
        x_idx = 0

    x_values = _extract_column_values(rows, x_idx)
    x_label = columns[x_idx] if x_idx < len(columns) else "x"

    # Find all numeric columns except the x column
    analyses = analyze_columns(columns, rows, column_types)
    numeric_indices = [
        a.index for a in analyses
        if a.is_numeric and a.index != x_idx and not a.all_null
    ]

    # If recommendation specifies a y_column, use it; otherwise use all numerics
    if recommendation.y_column:
        y_idx = _find_column_index(columns, recommendation.y_column)
        if y_idx is not None:
            numeric_indices = [y_idx]

    # If no numeric columns found, use first non-x column
    if not numeric_indices:
        for i in range(len(columns)):
            if i != x_idx:
                numeric_indices = [i]
                break

    traces: list[dict[str, Any]] = []
    for i, col_idx in enumerate(numeric_indices):
        y_values = _extract_column_values(rows, col_idx)
        x_clean, y_clean = _filter_null_pairs(x_values, y_values)

        trace: dict[str, Any] = {
            "type": "scatter",
            "mode": "lines+markers",
            "x": x_clean,
            "y": y_clean,
            "name": columns[col_idx] if col_idx < len(columns) else f"Series {i + 1}",
            "marker": {"color": COLOR_PALETTE[i % len(COLOR_PALETTE)]},
            "line": {"width": 2},
        }
        traces.append(trace)

    y_label = (
        columns[numeric_indices[0]]
        if len(numeric_indices) == 1 and numeric_indices[0] < len(columns)
        else "Value"
    )

    layout = _build_layout(title, x_label=x_label, y_label=y_label)

    return PlotlyConfig(
        data=traces,
        layout=layout,
        chart_type=ChartType.LINE.value,
    )


def _build_bar_config(
    columns: list[str],
    rows: list[list[Any]],
    recommendation: ChartRecommendation,
    title: str,
    column_types: list[str] | None = None,
) -> PlotlyConfig:
    """Build a Plotly bar chart configuration.

    Supports multi-trace (grouped bars) when multiple numeric columns
    are present alongside a categorical column.
    """
    x_idx = _find_column_index(columns, recommendation.x_column)
    if x_idx is None:
        x_idx = 0

    x_values = _truncate_labels(_extract_column_values(rows, x_idx))
    x_label = columns[x_idx] if x_idx < len(columns) else "Category"

    # Find numeric columns for multi-trace support
    analyses = analyze_columns(columns, rows, column_types)
    numeric_indices = [
        a.index for a in analyses
        if a.is_numeric and a.index != x_idx and not a.all_null
    ]

    if recommendation.y_column:
        y_idx = _find_column_index(columns, recommendation.y_column)
        if y_idx is not None:
            numeric_indices = [y_idx]

    if not numeric_indices:
        for i in range(len(columns)):
            if i != x_idx:
                numeric_indices = [i]
                break

    traces: list[dict[str, Any]] = []
    for i, col_idx in enumerate(numeric_indices):
        y_values = _extract_column_values(rows, col_idx)
        # For bar charts, replace None y-values with 0
        y_clean = [v if v is not None else 0 for v in y_values]

        trace: dict[str, Any] = {
            "type": "bar",
            "x": x_values,
            "y": y_clean,
            "name": columns[col_idx] if col_idx < len(columns) else f"Series {i + 1}",
            "marker": {"color": COLOR_PALETTE[i % len(COLOR_PALETTE)]},
        }
        traces.append(trace)

    y_label = (
        columns[numeric_indices[0]]
        if len(numeric_indices) == 1 and numeric_indices[0] < len(columns)
        else "Value"
    )

    extra_layout: dict[str, Any] = {}
    if len(traces) > 1:
        extra_layout["barmode"] = "group"

    layout = _build_layout(title, x_label=x_label, y_label=y_label, extra=extra_layout)

    return PlotlyConfig(
        data=traces,
        layout=layout,
        chart_type=ChartType.BAR.value,
    )


def _build_pie_config(
    columns: list[str],
    rows: list[list[Any]],
    recommendation: ChartRecommendation,
    title: str,
    column_types: list[str] | None = None,
) -> PlotlyConfig:
    """Build a Plotly pie chart configuration."""
    x_idx = _find_column_index(columns, recommendation.x_column)
    y_idx = _find_column_index(columns, recommendation.y_column)

    if x_idx is None:
        x_idx = 0
    if y_idx is None:
        y_idx = 1 if len(columns) > 1 else 0

    labels = _truncate_labels(_extract_column_values(rows, x_idx))
    values = _extract_column_values(rows, y_idx)

    # Filter out None values from the pie chart
    clean_labels: list[str] = []
    clean_values: list[Any] = []
    for lbl, val in zip(labels, values):
        if val is not None:
            clean_labels.append(lbl)
            clean_values.append(val)

    trace: dict[str, Any] = {
        "type": "pie",
        "labels": clean_labels,
        "values": clean_values,
        "hole": 0.3,
        "marker": {"colors": COLOR_PALETTE[: len(clean_labels)]},
        "textinfo": "percent+label",
        "hoverinfo": "label+value+percent",
    }

    layout = _build_layout(title)
    # Pie charts don't need axis labels
    layout.pop("xaxis", None)
    layout.pop("yaxis", None)

    return PlotlyConfig(
        data=[trace],
        layout=layout,
        chart_type=ChartType.PIE.value,
    )


def _build_scatter_config(
    columns: list[str],
    rows: list[list[Any]],
    recommendation: ChartRecommendation,
    title: str,
    column_types: list[str] | None = None,
) -> PlotlyConfig:
    """Build a Plotly scatter plot configuration."""
    x_idx = _find_column_index(columns, recommendation.x_column)
    y_idx = _find_column_index(columns, recommendation.y_column)

    if x_idx is None:
        x_idx = 0
    if y_idx is None:
        y_idx = 1 if len(columns) > 1 else 0

    x_values = _extract_column_values(rows, x_idx)
    y_values = _extract_column_values(rows, y_idx)
    x_clean, y_clean = _filter_null_pairs(x_values, y_values)

    x_label = columns[x_idx] if x_idx < len(columns) else "X"
    y_label = columns[y_idx] if y_idx < len(columns) else "Y"

    trace: dict[str, Any] = {
        "type": "scatter",
        "mode": "markers",
        "x": x_clean,
        "y": y_clean,
        "name": f"{y_label} vs {x_label}",
        "marker": {
            "color": COLOR_PALETTE[0],
            "size": 8,
            "opacity": 0.7,
        },
    }

    layout = _build_layout(title, x_label=x_label, y_label=y_label)

    return PlotlyConfig(
        data=[trace],
        layout=layout,
        chart_type=ChartType.SCATTER.value,
    )


def _build_histogram_config(
    columns: list[str],
    rows: list[list[Any]],
    recommendation: ChartRecommendation,
    title: str,
    column_types: list[str] | None = None,
) -> PlotlyConfig:
    """Build a Plotly histogram configuration."""
    x_idx = _find_column_index(columns, recommendation.x_column)
    if x_idx is None:
        x_idx = 0

    x_values = _extract_column_values(rows, x_idx)
    # Filter None values for histograms
    x_clean = [v for v in x_values if v is not None]

    x_label = columns[x_idx] if x_idx < len(columns) else "Value"

    trace: dict[str, Any] = {
        "type": "histogram",
        "x": x_clean,
        "name": x_label,
        "marker": {
            "color": COLOR_PALETTE[0],
            "line": {"color": COLOR_PALETTE[0], "width": 1},
        },
        "opacity": 0.8,
    }

    layout = _build_layout(
        title,
        x_label=x_label,
        y_label="Count",
        extra={"bargap": 0.05},
    )

    return PlotlyConfig(
        data=[trace],
        layout=layout,
        chart_type=ChartType.HISTOGRAM.value,
    )


def _build_kpi_config(
    columns: list[str],
    rows: list[list[Any]],
    recommendation: ChartRecommendation,
    title: str,
    column_types: list[str] | None = None,
) -> PlotlyConfig:
    """Build a KPI/stat card configuration for single-value results.

    Uses Plotly's indicator trace type for a clean metric display.
    Handles single-value and multi-value (multiple columns) KPIs.
    """
    if not rows:
        return _build_fallback(
            ChartRecommendation(
                chart_type=ChartType.TABLE,
                reasoning="No data for KPI.",
            ),
            title,
            None,
        )

    row = rows[0]

    # Single value KPI
    if len(columns) == 1:
        value = row[0] if row else None
        label = columns[0]

        trace: dict[str, Any] = {
            "type": "indicator",
            "mode": "number",
            "value": value,
            "title": {"text": label, "font": {"size": 16}},
            "number": {"font": {"size": 48}},
        }

        layout = _build_layout(title)
        layout.pop("xaxis", None)
        layout.pop("yaxis", None)
        layout["margin"] = {"l": 30, "r": 30, "t": 60, "b": 30}

        return PlotlyConfig(
            data=[trace],
            layout=layout,
            chart_type=ChartType.KPI.value,
        )

    # Multi-value KPI (multiple columns in a single row)
    traces: list[dict[str, Any]] = []
    num_cols = len(columns)

    # Calculate grid layout for multiple indicators
    cols_per_row = min(num_cols, 3)
    num_rows = math.ceil(num_cols / cols_per_row)

    for i, col_name in enumerate(columns):
        value = row[i] if i < len(row) else None
        grid_row = i // cols_per_row
        grid_col = i % cols_per_row

        # Calculate domain positioning for each indicator
        x_start = grid_col / cols_per_row
        x_end = (grid_col + 1) / cols_per_row
        y_start = 1.0 - (grid_row + 1) / num_rows
        y_end = 1.0 - grid_row / num_rows

        trace = {
            "type": "indicator",
            "mode": "number",
            "value": value,
            "title": {"text": col_name, "font": {"size": 14}},
            "number": {"font": {"size": 36}},
            "domain": {
                "x": [x_start + 0.02, x_end - 0.02],
                "y": [y_start + 0.02, y_end - 0.02],
            },
        }
        traces.append(trace)

    layout = _build_layout(title)
    layout.pop("xaxis", None)
    layout.pop("yaxis", None)
    layout["margin"] = {"l": 20, "r": 20, "t": 60, "b": 20}

    return PlotlyConfig(
        data=traces,
        layout=layout,
        chart_type=ChartType.KPI.value,
    )


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------


def _build_fallback(
    recommendation: ChartRecommendation,
    title: str | None,
    query_context: str | None,
) -> PlotlyConfig:
    """Build a fallback table configuration when charting isn't possible."""
    chart_title = title or query_context or "Query Results"

    return PlotlyConfig(
        data=[],
        layout={
            "title": {"text": chart_title},
            "annotations": [
                {
                    "text": recommendation.reasoning,
                    "showarrow": False,
                    "xref": "paper",
                    "yref": "paper",
                    "x": 0.5,
                    "y": 0.5,
                    "font": {"size": 14},
                }
            ],
        },
        chart_type=ChartType.TABLE.value,
        is_fallback=True,
    )
