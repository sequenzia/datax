"""Tests for chart type selection heuristics.

Covers:
- Functional: Time series -> line, categorical+numeric -> bar, proportional -> pie,
  two numerics -> scatter, single value -> KPI, AI can specify type, user can request type
- Edge Cases: All NULL -> no chart, mixed types -> categorical, 100k+ rows -> suggest
  aggregation, single row -> KPI, no numerics -> table only
- Error Handling: Cannot determine -> default to table
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app.services.chart_heuristics import (
    LARGE_RESULT_THRESHOLD,
    PIE_MAX_CATEGORIES,
    ChartRecommendation,
    ChartType,
    ColumnAnalysis,
    _all_positive,
    _is_datetime_column,
    _is_numeric_column,
    _is_numeric_value,
    _resolve_chart_type,
    analyze_columns,
    recommend_chart_type,
)

# ---------------------------------------------------------------------------
# Unit: _is_numeric_value
# ---------------------------------------------------------------------------


class TestIsNumericValue:
    """Test numeric value detection."""

    def test_int_is_numeric(self) -> None:
        assert _is_numeric_value(42) is True

    def test_float_is_numeric(self) -> None:
        assert _is_numeric_value(3.14) is True

    def test_string_number_is_numeric(self) -> None:
        assert _is_numeric_value("123") is True

    def test_string_float_is_numeric(self) -> None:
        assert _is_numeric_value("3.14") is True

    def test_none_is_not_numeric(self) -> None:
        assert _is_numeric_value(None) is False

    def test_bool_is_not_numeric(self) -> None:
        assert _is_numeric_value(True) is False
        assert _is_numeric_value(False) is False

    def test_string_is_not_numeric(self) -> None:
        assert _is_numeric_value("hello") is False

    def test_empty_string_is_not_numeric(self) -> None:
        assert _is_numeric_value("") is False


# ---------------------------------------------------------------------------
# Unit: _is_datetime_column
# ---------------------------------------------------------------------------


class TestIsDatetimeColumn:
    """Test datetime column detection."""

    def test_date_type_string(self) -> None:
        assert _is_datetime_column("col", "DATE", []) is True

    def test_timestamp_type_string(self) -> None:
        assert _is_datetime_column("col", "TIMESTAMP", []) is True

    def test_datetime_type_string(self) -> None:
        assert _is_datetime_column("col", "DATETIME", []) is True

    def test_date_column_name(self) -> None:
        assert _is_datetime_column("created_date", None, []) is True

    def test_timestamp_column_name(self) -> None:
        assert _is_datetime_column("updated_at", None, []) is True

    def test_created_at_column_name(self) -> None:
        assert _is_datetime_column("created_at", None, []) is True

    def test_year_column_name(self) -> None:
        assert _is_datetime_column("year", None, []) is True

    def test_month_column_name(self) -> None:
        assert _is_datetime_column("month", None, []) is True

    def test_non_date_column(self) -> None:
        assert _is_datetime_column("revenue", None, []) is False

    def test_datetime_sample_value(self) -> None:
        assert _is_datetime_column("col", None, [datetime(2024, 1, 1)]) is True

    def test_date_sample_value(self) -> None:
        assert _is_datetime_column("col", None, [date(2024, 1, 1)]) is True

    def test_iso_string_sample_value(self) -> None:
        assert _is_datetime_column("col", None, ["2024-01-15"]) is True

    def test_non_date_string_sample_value(self) -> None:
        assert _is_datetime_column("col", None, ["hello"]) is False


# ---------------------------------------------------------------------------
# Unit: _is_numeric_column
# ---------------------------------------------------------------------------


class TestIsNumericColumn:
    """Test numeric column detection."""

    def test_integer_type(self) -> None:
        assert _is_numeric_column("INTEGER", []) is True

    def test_float_type(self) -> None:
        assert _is_numeric_column("FLOAT", []) is True

    def test_bigint_type(self) -> None:
        assert _is_numeric_column("BIGINT", []) is True

    def test_decimal_type(self) -> None:
        assert _is_numeric_column("DECIMAL(10,2)", []) is True

    def test_varchar_type_with_numeric_values(self) -> None:
        assert _is_numeric_column("VARCHAR", [1, 2, 3]) is True

    def test_varchar_type_with_string_values(self) -> None:
        assert _is_numeric_column("VARCHAR", ["a", "b", "c"]) is False

    def test_no_type_with_numeric_values(self) -> None:
        assert _is_numeric_column(None, [10, 20, 30]) is True

    def test_no_type_with_no_values(self) -> None:
        assert _is_numeric_column(None, []) is False

    def test_all_null_values(self) -> None:
        assert _is_numeric_column(None, [None, None]) is False


# ---------------------------------------------------------------------------
# Unit: _resolve_chart_type
# ---------------------------------------------------------------------------


class TestResolveChartType:
    """Test chart type string resolution."""

    def test_resolves_enum_value(self) -> None:
        assert _resolve_chart_type(ChartType.BAR) == ChartType.BAR

    def test_resolves_string(self) -> None:
        assert _resolve_chart_type("line") == ChartType.LINE

    def test_resolves_uppercase_string(self) -> None:
        assert _resolve_chart_type("BAR") == ChartType.BAR

    def test_resolves_mixed_case_string(self) -> None:
        assert _resolve_chart_type("Scatter") == ChartType.SCATTER

    def test_returns_none_for_invalid(self) -> None:
        assert _resolve_chart_type("invalid_type") is None

    def test_returns_none_for_none(self) -> None:
        assert _resolve_chart_type(None) is None


# ---------------------------------------------------------------------------
# Unit: _all_positive
# ---------------------------------------------------------------------------


class TestAllPositive:
    """Test positive value checking for pie charts."""

    def test_all_positive(self) -> None:
        rows = [[1, 10], [2, 20], [3, 30]]
        assert _all_positive(rows, 1) is True

    def test_contains_negative(self) -> None:
        rows = [[1, 10], [2, -5], [3, 30]]
        assert _all_positive(rows, 1) is False

    def test_contains_zero(self) -> None:
        rows = [[1, 0], [2, 10]]
        assert _all_positive(rows, 1) is True

    def test_with_nulls(self) -> None:
        rows = [[1, None], [2, 10], [3, 20]]
        assert _all_positive(rows, 1) is True

    def test_all_null(self) -> None:
        rows = [[1, None], [2, None]]
        assert _all_positive(rows, 1) is True

    def test_bool_values(self) -> None:
        rows = [[1, True], [2, False]]
        assert _all_positive(rows, 1) is False


# ---------------------------------------------------------------------------
# Unit: analyze_columns
# ---------------------------------------------------------------------------


class TestAnalyzeColumns:
    """Test column analysis."""

    def test_empty_columns(self) -> None:
        result = analyze_columns([], [])
        assert result == []

    def test_numeric_column_detection(self) -> None:
        columns = ["revenue"]
        rows = [[100], [200], [300]]
        result = analyze_columns(columns, rows, ["INTEGER"])
        assert len(result) == 1
        assert result[0].is_numeric is True
        assert result[0].is_datetime is False
        assert result[0].distinct_count == 3

    def test_datetime_column_detection(self) -> None:
        columns = ["created_at"]
        rows = [["2024-01-01"], ["2024-01-02"]]
        result = analyze_columns(columns, rows)
        assert result[0].is_datetime is True
        assert result[0].is_numeric is False

    def test_categorical_column_detection(self) -> None:
        columns = ["category"]
        rows = [["A"], ["B"], ["A"], ["C"]]
        result = analyze_columns(columns, rows)
        assert result[0].is_categorical is True
        assert result[0].distinct_count == 3

    def test_null_counting(self) -> None:
        columns = ["value"]
        rows = [[None], [1], [None], [2]]
        result = analyze_columns(columns, rows, ["INTEGER"])
        assert result[0].null_count == 2
        assert result[0].total_count == 4

    def test_all_null_column(self) -> None:
        columns = ["value"]
        rows = [[None], [None], [None]]
        result = analyze_columns(columns, rows)
        assert result[0].all_null is True

    def test_mixed_types_become_categorical(self) -> None:
        """Columns with mixed numeric and string values -> categorical."""
        columns = ["mixed"]
        rows = [[1], ["hello"], [3], ["world"]]
        result = analyze_columns(columns, rows)
        assert result[0].is_categorical is True
        assert result[0].is_numeric is False

    def test_multiple_columns(self) -> None:
        columns = ["name", "value", "date"]
        rows = [
            ["Alice", 100, "2024-01-01"],
            ["Bob", 200, "2024-01-02"],
        ]
        result = analyze_columns(columns, rows, ["VARCHAR", "INTEGER", "DATE"])
        assert result[0].is_categorical is True
        assert result[1].is_numeric is True
        assert result[2].is_datetime is True


# ---------------------------------------------------------------------------
# Functional: Time series -> line chart
# ---------------------------------------------------------------------------


class TestTimeSeriesLineChart:
    """Time series data should recommend a line chart."""

    def test_date_column_with_numeric(self) -> None:
        columns = ["date", "revenue"]
        rows = [
            ["2024-01-01", 100],
            ["2024-01-02", 200],
            ["2024-01-03", 300],
        ]
        result = recommend_chart_type(columns, rows, ["DATE", "FLOAT"])
        assert result.chart_type == ChartType.LINE
        assert result.x_column == "date"
        assert result.y_column == "revenue"

    def test_timestamp_column_with_numeric(self) -> None:
        columns = ["created_at", "count"]
        rows = [
            [datetime(2024, 1, 1), 10],
            [datetime(2024, 2, 1), 20],
        ]
        result = recommend_chart_type(columns, rows)
        assert result.chart_type == ChartType.LINE

    def test_year_column_with_numeric(self) -> None:
        columns = ["year", "total_sales"]
        rows = [
            ["2020", 1000],
            ["2021", 1500],
            ["2022", 2000],
        ]
        result = recommend_chart_type(columns, rows)
        assert result.chart_type == ChartType.LINE


# ---------------------------------------------------------------------------
# Functional: Categorical + numeric -> bar chart
# ---------------------------------------------------------------------------


class TestCategoricalBarChart:
    """Categorical + numeric data should recommend a bar chart."""

    def test_category_with_count(self) -> None:
        columns = ["department", "employee_count"]
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
        result = recommend_chart_type(columns, rows, ["VARCHAR", "INTEGER"])
        assert result.chart_type == ChartType.BAR
        assert result.x_column == "department"
        assert result.y_column == "employee_count"

    def test_category_with_negative_values(self) -> None:
        """Negative values should prevent pie and use bar instead."""
        columns = ["category", "profit"]
        rows = [
            ["A", 100],
            ["B", -50],
            ["C", 200],
        ]
        result = recommend_chart_type(columns, rows, ["VARCHAR", "FLOAT"])
        assert result.chart_type == ChartType.BAR


# ---------------------------------------------------------------------------
# Functional: Proportional -> pie chart
# ---------------------------------------------------------------------------


class TestProportionalPieChart:
    """Proportional data should recommend a pie chart."""

    def test_few_categories_single_numeric_all_positive(self) -> None:
        columns = ["region", "sales"]
        rows = [
            ["North", 400],
            ["South", 300],
            ["East", 200],
            ["West", 100],
        ]
        result = recommend_chart_type(columns, rows, ["VARCHAR", "INTEGER"])
        assert result.chart_type == ChartType.PIE
        assert result.x_column == "region"
        assert result.y_column == "sales"

    def test_too_many_categories_gets_bar(self) -> None:
        """More than PIE_MAX_CATEGORIES categories -> bar instead of pie."""
        columns = ["product", "sales"]
        rows = [[f"Product_{i}", i * 10] for i in range(PIE_MAX_CATEGORIES + 1)]
        result = recommend_chart_type(columns, rows, ["VARCHAR", "INTEGER"])
        assert result.chart_type == ChartType.BAR

    def test_multiple_numeric_columns_gets_bar(self) -> None:
        """Multiple numeric columns -> bar, not pie."""
        columns = ["category", "q1_sales", "q2_sales"]
        rows = [
            ["A", 100, 150],
            ["B", 200, 250],
        ]
        result = recommend_chart_type(columns, rows, ["VARCHAR", "INTEGER", "INTEGER"])
        assert result.chart_type == ChartType.BAR


# ---------------------------------------------------------------------------
# Functional: Two numerics -> scatter
# ---------------------------------------------------------------------------


class TestTwoNumericsScatter:
    """Two numeric columns should recommend a scatter plot."""

    def test_two_numerics_no_categorical(self) -> None:
        columns = ["height", "weight"]
        rows = [
            [170, 65],
            [180, 80],
            [160, 55],
            [175, 70],
        ]
        result = recommend_chart_type(columns, rows, ["FLOAT", "FLOAT"])
        assert result.chart_type == ChartType.SCATTER
        assert result.x_column == "height"
        assert result.y_column == "weight"

    def test_three_numerics_still_scatter(self) -> None:
        columns = ["x", "y", "z"]
        rows = [[1, 2, 3], [4, 5, 6]]
        result = recommend_chart_type(columns, rows, ["FLOAT", "FLOAT", "FLOAT"])
        assert result.chart_type == ChartType.SCATTER


# ---------------------------------------------------------------------------
# Functional: Single value -> KPI
# ---------------------------------------------------------------------------


class TestSingleValueKPI:
    """Single value/row results should recommend KPI."""

    def test_single_row_single_numeric(self) -> None:
        columns = ["total"]
        rows = [[42]]
        result = recommend_chart_type(columns, rows, ["INTEGER"])
        assert result.chart_type == ChartType.KPI
        assert result.y_column == "total"

    def test_single_row_multiple_columns(self) -> None:
        columns = ["count", "average", "max"]
        rows = [[100, 45.5, 99]]
        result = recommend_chart_type(columns, rows, ["INTEGER", "FLOAT", "INTEGER"])
        assert result.chart_type == ChartType.KPI

    def test_single_row_non_numeric(self) -> None:
        columns = ["status"]
        rows = [["active"]]
        result = recommend_chart_type(columns, rows, ["VARCHAR"])
        assert result.chart_type == ChartType.KPI


# ---------------------------------------------------------------------------
# Functional: AI can specify type
# ---------------------------------------------------------------------------


class TestAIOverride:
    """AI agent should be able to override heuristic chart type."""

    def test_ai_overrides_heuristic(self) -> None:
        """Even though data suggests bar, AI specifies scatter."""
        columns = ["category", "value"]
        rows = [["A", 10], ["B", 20], ["C", 30]]
        result = recommend_chart_type(
            columns, rows, ["VARCHAR", "INTEGER"],
            ai_override="scatter",
        )
        assert result.chart_type == ChartType.SCATTER
        assert "AI agent" in result.reasoning

    def test_ai_override_with_enum(self) -> None:
        columns = ["x", "y"]
        rows = [[1, 2], [3, 4]]
        result = recommend_chart_type(
            columns, rows,
            ai_override=ChartType.HISTOGRAM,
        )
        assert result.chart_type == ChartType.HISTOGRAM

    def test_invalid_ai_override_falls_through(self) -> None:
        """Invalid AI override falls through to heuristics."""
        columns = ["category", "value"]
        rows = [["A", 10], ["B", 20]]
        result = recommend_chart_type(
            columns, rows, ["VARCHAR", "INTEGER"],
            ai_override="invalid_chart",
        )
        # Falls through to heuristic (pie for few categories with positive values)
        assert result.chart_type in (ChartType.PIE, ChartType.BAR)


# ---------------------------------------------------------------------------
# Functional: User can request type
# ---------------------------------------------------------------------------


class TestUserRequest:
    """User should be able to request a specific chart type."""

    def test_user_request_overrides_everything(self) -> None:
        """User request overrides both AI override and heuristics."""
        columns = ["category", "value"]
        rows = [["A", 10], ["B", 20]]
        result = recommend_chart_type(
            columns, rows, ["VARCHAR", "INTEGER"],
            ai_override="bar",
            user_requested="line",
        )
        assert result.chart_type == ChartType.LINE
        assert "User requested" in result.reasoning

    def test_user_request_string(self) -> None:
        columns = ["x"]
        rows = [[1], [2], [3]]
        result = recommend_chart_type(
            columns, rows,
            user_requested="histogram",
        )
        assert result.chart_type == ChartType.HISTOGRAM

    def test_invalid_user_request_falls_through(self) -> None:
        """Invalid user request falls through to AI override or heuristics."""
        columns = ["x", "y"]
        rows = [[1, 2], [3, 4]]
        result = recommend_chart_type(
            columns, rows, ["FLOAT", "FLOAT"],
            user_requested="nonexistent",
        )
        # Falls through to heuristic
        assert result.chart_type == ChartType.SCATTER


# ---------------------------------------------------------------------------
# Edge Cases: All NULL -> no chart
# ---------------------------------------------------------------------------


class TestAllNullEdgeCase:
    """All NULL values should produce table-only recommendation."""

    def test_all_null_single_column(self) -> None:
        columns = ["value"]
        rows = [[None], [None], [None]]
        result = recommend_chart_type(columns, rows)
        assert result.chart_type == ChartType.TABLE
        assert "NULL" in result.reasoning

    def test_all_null_multiple_columns(self) -> None:
        columns = ["a", "b", "c"]
        rows = [[None, None, None], [None, None, None]]
        result = recommend_chart_type(columns, rows)
        assert result.chart_type == ChartType.TABLE


# ---------------------------------------------------------------------------
# Edge Cases: Mixed types -> categorical
# ---------------------------------------------------------------------------


class TestMixedTypesEdgeCase:
    """Mixed types should be treated as categorical."""

    def test_mixed_numeric_and_string_is_categorical(self) -> None:
        columns = ["mixed"]
        rows = [[1], ["hello"], [3], ["world"]]
        analyses = analyze_columns(columns, rows)
        assert analyses[0].is_categorical is True
        assert analyses[0].is_numeric is False

    def test_mixed_column_with_numeric_gives_table(self) -> None:
        """Mixed type column + numeric -> treated as categorical+numeric -> bar."""
        columns = ["label", "value"]
        rows = [[1, 10], ["hello", 20], [3, 30], ["world", 40]]
        result = recommend_chart_type(columns, rows, [None, "INTEGER"])
        # label is mixed -> categorical, value is numeric -> bar
        assert result.chart_type in (ChartType.BAR, ChartType.PIE)


# ---------------------------------------------------------------------------
# Edge Cases: 100k+ rows -> suggest aggregation
# ---------------------------------------------------------------------------


class TestLargeResultSetEdgeCase:
    """Large result sets should suggest aggregation."""

    def test_large_result_suggests_aggregation(self) -> None:
        columns = ["date", "value"]
        # Create minimal large dataset
        rows = [["2024-01-01", i] for i in range(LARGE_RESULT_THRESHOLD + 1)]
        result = recommend_chart_type(columns, rows, ["DATE", "FLOAT"])
        assert result.suggest_aggregation is True
        assert result.aggregation_message is not None
        msg = result.aggregation_message.lower()
        assert "aggregat" in msg

    def test_small_result_no_aggregation_suggestion(self) -> None:
        columns = ["date", "value"]
        rows = [["2024-01-01", 100], ["2024-01-02", 200]]
        result = recommend_chart_type(columns, rows, ["DATE", "FLOAT"])
        assert result.suggest_aggregation is False


# ---------------------------------------------------------------------------
# Edge Cases: Single row -> KPI
# ---------------------------------------------------------------------------


class TestSingleRowEdgeCase:
    """Single row results should always be KPI."""

    def test_single_row_with_numeric(self) -> None:
        columns = ["avg_salary"]
        rows = [[75000]]
        result = recommend_chart_type(columns, rows, ["FLOAT"])
        assert result.chart_type == ChartType.KPI

    def test_single_row_with_text(self) -> None:
        columns = ["name"]
        rows = [["Alice"]]
        result = recommend_chart_type(columns, rows, ["VARCHAR"])
        assert result.chart_type == ChartType.KPI

    def test_single_row_multiple_numeric(self) -> None:
        columns = ["min", "max", "avg"]
        rows = [[10, 100, 55]]
        result = recommend_chart_type(columns, rows, ["FLOAT", "FLOAT", "FLOAT"])
        assert result.chart_type == ChartType.KPI


# ---------------------------------------------------------------------------
# Edge Cases: No numerics -> table only
# ---------------------------------------------------------------------------


class TestNoNumericsEdgeCase:
    """No numeric columns should produce table-only recommendation."""

    def test_all_text_columns(self) -> None:
        columns = ["name", "city", "status"]
        rows = [
            ["Alice", "NYC", "active"],
            ["Bob", "LA", "inactive"],
        ]
        result = recommend_chart_type(columns, rows, ["VARCHAR", "VARCHAR", "VARCHAR"])
        assert result.chart_type == ChartType.TABLE
        assert "numeric" in result.reasoning.lower()


# ---------------------------------------------------------------------------
# Error Handling: Cannot determine -> default to table
# ---------------------------------------------------------------------------


class TestCannotDetermineDefault:
    """When chart type cannot be determined, default to table."""

    def test_empty_result_set(self) -> None:
        columns = ["a", "b"]
        rows: list[list] = []
        result = recommend_chart_type(columns, rows)
        assert result.chart_type == ChartType.TABLE

    def test_empty_columns(self) -> None:
        result = recommend_chart_type([], [])
        assert result.chart_type == ChartType.TABLE

    def test_no_columns_with_rows(self) -> None:
        result = recommend_chart_type([], [[1, 2]])
        assert result.chart_type == ChartType.TABLE


# ---------------------------------------------------------------------------
# ChartRecommendation
# ---------------------------------------------------------------------------


class TestChartRecommendation:
    """Test ChartRecommendation dataclass and serialization."""

    def test_to_dict_basic(self) -> None:
        rec = ChartRecommendation(
            chart_type=ChartType.BAR,
            reasoning="Test reasoning",
            x_column="category",
            y_column="value",
        )
        d = rec.to_dict()
        assert d["chart_type"] == "bar"
        assert d["reasoning"] == "Test reasoning"
        assert d["x_column"] == "category"
        assert d["y_column"] == "value"
        assert "group_column" not in d
        assert "suggest_aggregation" not in d

    def test_to_dict_with_aggregation(self) -> None:
        rec = ChartRecommendation(
            chart_type=ChartType.LINE,
            reasoning="Time series",
            suggest_aggregation=True,
            aggregation_message="Too many rows",
        )
        d = rec.to_dict()
        assert d["suggest_aggregation"] is True
        assert d["aggregation_message"] == "Too many rows"

    def test_to_dict_minimal(self) -> None:
        rec = ChartRecommendation(
            chart_type=ChartType.TABLE,
            reasoning="No data",
        )
        d = rec.to_dict()
        assert d == {"chart_type": "table", "reasoning": "No data"}


# ---------------------------------------------------------------------------
# ColumnAnalysis
# ---------------------------------------------------------------------------


class TestColumnAnalysis:
    """Test ColumnAnalysis properties."""

    def test_all_null_property(self) -> None:
        ca = ColumnAnalysis(name="x", index=0, null_count=5, total_count=5)
        assert ca.all_null is True

    def test_not_all_null(self) -> None:
        ca = ColumnAnalysis(name="x", index=0, null_count=2, total_count=5)
        assert ca.all_null is False

    def test_null_ratio(self) -> None:
        ca = ColumnAnalysis(name="x", index=0, null_count=3, total_count=10)
        assert ca.null_ratio == pytest.approx(0.3)

    def test_null_ratio_zero_total(self) -> None:
        ca = ColumnAnalysis(name="x", index=0, null_count=0, total_count=0)
        assert ca.null_ratio == 0.0


# ---------------------------------------------------------------------------
# Integration: Histogram detection
# ---------------------------------------------------------------------------


class TestHistogramDetection:
    """Single numeric column with multiple rows -> histogram."""

    def test_single_numeric_many_rows(self) -> None:
        columns = ["score"]
        rows = [[i] for i in range(50)]
        result = recommend_chart_type(columns, rows, ["FLOAT"])
        assert result.chart_type == ChartType.HISTOGRAM
        assert result.x_column == "score"

    def test_single_numeric_two_rows(self) -> None:
        columns = ["value"]
        rows = [[10], [20]]
        result = recommend_chart_type(columns, rows, ["INTEGER"])
        assert result.chart_type == ChartType.HISTOGRAM


# ---------------------------------------------------------------------------
# ChartType enum
# ---------------------------------------------------------------------------


class TestChartTypeEnum:
    """Test ChartType enum values."""

    def test_all_values(self) -> None:
        assert ChartType.LINE.value == "line"
        assert ChartType.BAR.value == "bar"
        assert ChartType.PIE.value == "pie"
        assert ChartType.SCATTER.value == "scatter"
        assert ChartType.HISTOGRAM.value == "histogram"
        assert ChartType.KPI.value == "kpi"
        assert ChartType.TABLE.value == "table"

    def test_string_enum(self) -> None:
        """ChartType inherits from str for JSON serialization."""
        assert isinstance(ChartType.BAR, str)
        assert ChartType.BAR.value == "bar"
        assert str(ChartType.BAR) == "ChartType.BAR" or ChartType.BAR == "bar"
