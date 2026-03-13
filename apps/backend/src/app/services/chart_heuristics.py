"""Chart type selection heuristics for AI-generated visualizations.

Analyzes query result data shape (columns, types, value distributions) to
recommend the best chart type. The recommendation includes reasoning so
the AI agent and user understand why a particular chart was selected.

Heuristic priority order:
1. Single value (1 row, 1 numeric column) -> KPI card
2. Single row with multiple columns -> KPI card
3. All NULL data -> no chart (table only)
4. No numeric columns -> table only
5. Time series (date/time column + numeric) -> line chart
6. Proportional data (categorical + single numeric, few categories) -> pie chart
7. Categorical + numeric -> bar chart
8. Two numeric columns -> scatter plot
9. Single numeric column with many rows -> histogram
10. Fallback -> table

The AI agent can override the heuristic by specifying a chart type directly.
Users can also request a different chart type via follow-up conversation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from app.logging import get_logger

logger = get_logger(__name__)


class ChartType(StrEnum):
    """Supported chart types for visualization."""

    LINE = "line"
    BAR = "bar"
    PIE = "pie"
    SCATTER = "scatter"
    HISTOGRAM = "histogram"
    KPI = "kpi"
    TABLE = "table"


# Date/time column name patterns (case-insensitive)
_DATE_NAME_PATTERNS = re.compile(
    r"(date|time|timestamp|created|updated|modified|year|month|day|"
    r"week|hour|minute|period|quarter|_at$|_on$|_dt$)",
    re.IGNORECASE,
)

# Date/time data type patterns (from database type strings)
_DATE_TYPE_PATTERNS = re.compile(
    r"(date|time|timestamp|datetime|interval)",
    re.IGNORECASE,
)

# Numeric data type patterns
_NUMERIC_TYPE_PATTERNS = re.compile(
    r"(int|float|double|decimal|numeric|real|number|bigint|smallint|"
    r"tinyint|serial|money|currency)",
    re.IGNORECASE,
)

# Threshold for treating a column as categorical (distinct values < this)
CATEGORICAL_DISTINCT_THRESHOLD = 20

# Threshold for suggesting aggregation (row count above this)
LARGE_RESULT_THRESHOLD = 100_000

# Maximum categories for a pie chart to be readable
PIE_MAX_CATEGORIES = 10


@dataclass
class ColumnAnalysis:
    """Analysis of a single column's characteristics."""

    name: str
    index: int
    is_numeric: bool = False
    is_datetime: bool = False
    is_categorical: bool = False
    distinct_count: int = 0
    null_count: int = 0
    total_count: int = 0
    sample_values: list[Any] = field(default_factory=list)

    @property
    def all_null(self) -> bool:
        """Return True if all values in this column are NULL."""
        return self.total_count > 0 and self.null_count == self.total_count

    @property
    def null_ratio(self) -> float:
        """Return the ratio of NULL values (0.0 to 1.0)."""
        if self.total_count == 0:
            return 0.0
        return self.null_count / self.total_count


@dataclass
class ChartRecommendation:
    """Recommendation for chart type with reasoning."""

    chart_type: ChartType
    reasoning: str
    x_column: str | None = None
    y_column: str | None = None
    group_column: str | None = None
    suggest_aggregation: bool = False
    aggregation_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary."""
        result: dict[str, Any] = {
            "chart_type": self.chart_type.value,
            "reasoning": self.reasoning,
        }
        if self.x_column is not None:
            result["x_column"] = self.x_column
        if self.y_column is not None:
            result["y_column"] = self.y_column
        if self.group_column is not None:
            result["group_column"] = self.group_column
        if self.suggest_aggregation:
            result["suggest_aggregation"] = True
            result["aggregation_message"] = self.aggregation_message
        return result


# ---------------------------------------------------------------------------
# Column classification helpers
# ---------------------------------------------------------------------------


def _is_datetime_column(
    name: str,
    data_type: str | None,
    sample_values: list[Any],
) -> bool:
    """Determine if a column contains date/time data.

    Checks the column name pattern, declared data type, and sample values.
    """
    # Check data type string first
    if data_type and _DATE_TYPE_PATTERNS.search(data_type):
        return True

    # Check column name pattern
    if _DATE_NAME_PATTERNS.search(name):
        return True

    # Check sample values
    for val in sample_values:
        if val is None:
            continue
        if isinstance(val, (datetime, date)):
            return True
        if isinstance(val, str):
            # Try to detect ISO date-like strings
            if re.match(r"\d{4}-\d{2}-\d{2}", val):
                return True
        break  # Only need to check one non-null value

    return False


def _is_numeric_value(value: Any) -> bool:
    """Check if a value is numeric (int or float)."""
    if value is None:
        return False
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        try:
            float(value)
            return True
        except (ValueError, TypeError):
            return False
    return False


def _is_numeric_column(
    data_type: str | None,
    sample_values: list[Any],
) -> bool:
    """Determine if a column contains numeric data.

    Checks the declared data type and sample values.
    """
    if data_type and _NUMERIC_TYPE_PATTERNS.search(data_type):
        return True

    # Check sample values for numeric content
    non_null_values = [v for v in sample_values if v is not None]
    if not non_null_values:
        return False

    numeric_count = sum(1 for v in non_null_values if _is_numeric_value(v))
    # If majority of non-null samples are numeric, treat as numeric
    return numeric_count > len(non_null_values) / 2


# ---------------------------------------------------------------------------
# Column analysis
# ---------------------------------------------------------------------------


def analyze_columns(
    columns: list[str],
    rows: list[list[Any]],
    column_types: list[str] | None = None,
) -> list[ColumnAnalysis]:
    """Analyze each column in the result set.

    Args:
        columns: Column names.
        rows: Row data (list of lists).
        column_types: Optional data type strings for each column.

    Returns:
        List of ColumnAnalysis objects, one per column.
    """
    if not columns:
        return []

    num_columns = len(columns)
    types = column_types or [None] * num_columns  # type: ignore[list-item]

    analyses: list[ColumnAnalysis] = []

    for idx in range(num_columns):
        name = columns[idx]
        data_type = types[idx] if idx < len(types) else None

        # Collect values for this column
        values = [row[idx] for row in rows if idx < len(row)]
        total_count = len(values)
        null_count = sum(1 for v in values if v is None)
        non_null = [v for v in values if v is not None]

        # Count distinct non-null values
        try:
            distinct_values = set()
            for v in non_null:
                try:
                    distinct_values.add(v)
                except TypeError:
                    # Unhashable types (lists, dicts) - treat as unique
                    distinct_values.add(id(v))
            distinct_count = len(distinct_values)
        except Exception:
            distinct_count = len(non_null)

        # Sample values (up to 10 non-null)
        sample_values = non_null[:10]

        # Classify column type
        is_dt = _is_datetime_column(name, data_type, sample_values)
        is_num = False if is_dt else _is_numeric_column(data_type, sample_values)

        # Categorical: not numeric, not datetime, and has limited distinct values
        is_cat = (
            not is_num
            and not is_dt
            and distinct_count < CATEGORICAL_DISTINCT_THRESHOLD
        )

        # Mixed types: if column has both numeric and non-numeric values,
        # treat as categorical
        if not is_dt and non_null:
            numeric_vals = [v for v in non_null if _is_numeric_value(v)]
            non_numeric_vals = [
                v for v in non_null
                if not _is_numeric_value(v) and not isinstance(v, bool)
            ]
            if numeric_vals and non_numeric_vals:
                is_num = False
                is_cat = True

        analyses.append(
            ColumnAnalysis(
                name=name,
                index=idx,
                is_numeric=is_num,
                is_datetime=is_dt,
                is_categorical=is_cat,
                distinct_count=distinct_count,
                null_count=null_count,
                total_count=total_count,
                sample_values=sample_values,
            )
        )

    return analyses


# ---------------------------------------------------------------------------
# Chart type recommendation
# ---------------------------------------------------------------------------


def recommend_chart_type(
    columns: list[str],
    rows: list[list[Any]],
    column_types: list[str] | None = None,
    ai_override: ChartType | str | None = None,
    user_requested: ChartType | str | None = None,
) -> ChartRecommendation:
    """Recommend the best chart type for the given query results.

    Args:
        columns: Column names from the query result.
        rows: Row data from the query result.
        column_types: Optional data type strings for each column.
        ai_override: Chart type specified by the AI agent (takes
            precedence over heuristics but not user request).
        user_requested: Chart type explicitly requested by the user
            (highest precedence).

    Returns:
        A ChartRecommendation with the chart type, reasoning, and
        axis column suggestions.
    """
    row_count = len(rows)

    # User request takes highest precedence
    if user_requested is not None:
        chart = _resolve_chart_type(user_requested)
        if chart is not None:
            return ChartRecommendation(
                chart_type=chart,
                reasoning=f"User requested {chart.value} chart.",
            )

    # AI override takes precedence over heuristics
    if ai_override is not None:
        chart = _resolve_chart_type(ai_override)
        if chart is not None:
            return ChartRecommendation(
                chart_type=chart,
                reasoning=f"AI agent specified {chart.value} chart.",
            )

    # No data -> table
    if not columns or not rows:
        return ChartRecommendation(
            chart_type=ChartType.TABLE,
            reasoning="No data available to visualize.",
        )

    # Analyze columns
    analyses = analyze_columns(columns, rows, column_types)

    # Check if all data is NULL
    if all(col.all_null for col in analyses):
        return ChartRecommendation(
            chart_type=ChartType.TABLE,
            reasoning="All values are NULL. No chart can be generated.",
        )

    # Classify columns
    numeric_cols = [a for a in analyses if a.is_numeric and not a.all_null]
    datetime_cols = [a for a in analyses if a.is_datetime and not a.all_null]
    categorical_cols = [a for a in analyses if a.is_categorical and not a.all_null]

    # Single row -> KPI
    if row_count == 1:
        if numeric_cols:
            return ChartRecommendation(
                chart_type=ChartType.KPI,
                reasoning=(
                    "Single row result with numeric data. "
                    "Best displayed as a KPI/stat card."
                ),
                y_column=numeric_cols[0].name,
            )
        return ChartRecommendation(
            chart_type=ChartType.KPI,
            reasoning="Single row result. Best displayed as a KPI/stat card.",
            y_column=columns[0],
        )

    # Single numeric column, single row equivalent (1 col, 1 row handled above)
    # Single value: only one column which is numeric and one row
    if len(columns) == 1 and numeric_cols and row_count == 1:
        return ChartRecommendation(
            chart_type=ChartType.KPI,
            reasoning="Single numeric value. Best displayed as a KPI card.",
            y_column=numeric_cols[0].name,
        )

    # No numeric columns -> table only
    if not numeric_cols:
        return ChartRecommendation(
            chart_type=ChartType.TABLE,
            reasoning=(
                "No numeric columns found. "
                "Data is best displayed as a table."
            ),
        )

    # Large result set -> suggest aggregation
    suggest_agg = row_count > LARGE_RESULT_THRESHOLD
    agg_message = None
    if suggest_agg:
        agg_message = (
            f"Result set has {row_count:,} rows. "
            f"Consider aggregating the data (GROUP BY) for better visualization. "
            f"The full data is available in the table view."
        )

    # Time series: datetime column + numeric column -> line chart
    if datetime_cols and numeric_cols:
        dt_col = datetime_cols[0]
        num_col = numeric_cols[0]
        return ChartRecommendation(
            chart_type=ChartType.LINE,
            reasoning=(
                f"Time series data detected: '{dt_col.name}' (date/time) "
                f"with '{num_col.name}' (numeric). Line chart shows trends over time."
            ),
            x_column=dt_col.name,
            y_column=num_col.name,
            suggest_aggregation=suggest_agg,
            aggregation_message=agg_message,
        )

    # Categorical + numeric -> bar or pie
    if categorical_cols and numeric_cols:
        cat_col = categorical_cols[0]
        num_col = numeric_cols[0]

        # Proportional data (pie): few categories, single numeric column,
        # and all values are positive
        if (
            cat_col.distinct_count <= PIE_MAX_CATEGORIES
            and len(numeric_cols) == 1
            and _all_positive(rows, num_col.index)
        ):
            return ChartRecommendation(
                chart_type=ChartType.PIE,
                reasoning=(
                    f"Proportional data: '{cat_col.name}' has "
                    f"{cat_col.distinct_count} categories with a single "
                    f"numeric column '{num_col.name}'. "
                    f"Pie chart shows relative proportions."
                ),
                x_column=cat_col.name,
                y_column=num_col.name,
                suggest_aggregation=suggest_agg,
                aggregation_message=agg_message,
            )

        # Bar chart for categorical + numeric
        return ChartRecommendation(
            chart_type=ChartType.BAR,
            reasoning=(
                f"Categorical data: '{cat_col.name}' "
                f"({cat_col.distinct_count} categories) with numeric "
                f"column '{num_col.name}'. Bar chart compares values "
                f"across categories."
            ),
            x_column=cat_col.name,
            y_column=num_col.name,
            suggest_aggregation=suggest_agg,
            aggregation_message=agg_message,
        )

    # Two or more numeric columns -> scatter plot
    if len(numeric_cols) >= 2:
        x_col = numeric_cols[0]
        y_col = numeric_cols[1]
        return ChartRecommendation(
            chart_type=ChartType.SCATTER,
            reasoning=(
                f"Two numeric columns: '{x_col.name}' and '{y_col.name}'. "
                f"Scatter plot shows the relationship between them."
            ),
            x_column=x_col.name,
            y_column=y_col.name,
            suggest_aggregation=suggest_agg,
            aggregation_message=agg_message,
        )

    # Single numeric column with many rows -> histogram
    if len(numeric_cols) == 1 and row_count > 1:
        num_col = numeric_cols[0]
        return ChartRecommendation(
            chart_type=ChartType.HISTOGRAM,
            reasoning=(
                f"Single numeric column '{num_col.name}' with "
                f"{row_count} values. Histogram shows the distribution."
            ),
            x_column=num_col.name,
            suggest_aggregation=suggest_agg,
            aggregation_message=agg_message,
        )

    # Fallback -> table
    return ChartRecommendation(
        chart_type=ChartType.TABLE,
        reasoning="Could not determine an appropriate chart type. Displaying as table.",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_chart_type(value: ChartType | str | None) -> ChartType | None:
    """Convert a string or ChartType to a ChartType enum, or None if invalid."""
    if value is None:
        return None
    if isinstance(value, ChartType):
        return value
    try:
        return ChartType(value.lower())
    except (ValueError, AttributeError):
        logger.warning("invalid_chart_type", requested=str(value))
        return None


def _all_positive(rows: list[list[Any]], col_index: int) -> bool:
    """Check if all non-null values in a column are positive numbers."""
    for row in rows:
        if col_index >= len(row):
            continue
        val = row[col_index]
        if val is None:
            continue
        if isinstance(val, bool):
            return False
        if isinstance(val, (int, float)):
            if val < 0:
                return False
        else:
            try:
                if float(val) < 0:
                    return False
            except (ValueError, TypeError):
                return False
    return True
