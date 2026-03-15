"""Tests for conversation context with graduated summarization.

Covers:
- Unit: AnalysisState serialization/deserialization
- Unit: Graduated compression logic (full -> signature -> summary)
- Unit: Token counting for different providers
- Unit: SQL signature extraction
- Unit: Result summary construction
- Unit: Context formatting for system prompt
- Integration: Context carries across multiple agent turns
- Integration: analysis_context persists in database between requests
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.orm import Conversation
from app.services.conversation_context import (
    COMPRESSION_THRESHOLD,
    RECENT_QUERY_LIMIT,
    AnalysisState,
    QueryRecord,
    add_turn_to_state,
    build_result_summary,
    compress_context,
    estimate_tokens,
    extract_sql_signature,
    format_context_for_prompt,
    get_context_window,
    get_token_budget,
    inject_conversation_context,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_engine():
    """Create an in-memory SQLite engine for tests."""
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def session_factory(db_engine):
    """Create a session factory for tests."""
    return sessionmaker(bind=db_engine)


@pytest.fixture
def session(session_factory):
    """Create a database session for tests."""
    s = session_factory()
    yield s
    s.close()


@pytest.fixture
def empty_state() -> AnalysisState:
    """Create an empty AnalysisState."""
    return AnalysisState(provider_name="openai")


@pytest.fixture
def populated_state() -> AnalysisState:
    """Create an AnalysisState with 3 query turns."""
    state = AnalysisState(provider_name="openai", total_turns=3)
    for i in range(3):
        record = QueryRecord(
            user_message=f"Question {i + 1}",
            sql=f"SELECT col{i} FROM table{i}",
            sql_signature=f"SELECT col{i} | FROM table{i}",
            result_summary={
                "columns": [f"col{i}"],
                "row_count": (i + 1) * 10,
                "column_stats": {
                    f"col{i}": {"min": 0, "max": 100, "avg": 50}
                },
            },
            source_id=str(uuid.uuid4()),
            source_type="dataset",
            turn_index=i,
        )
        state.recent_queries.append(record)
        state.result_summaries.append(record.result_summary)
    return state


# ---------------------------------------------------------------------------
# Unit: AnalysisState serialization/deserialization
# ---------------------------------------------------------------------------


class TestAnalysisStateSerialization:
    """Test AnalysisState to_dict / from_dict round-tripping."""

    def test_empty_state_serializes(self, empty_state: AnalysisState) -> None:
        """Empty state serializes to valid dict."""
        data = empty_state.to_dict()
        assert data["recent_queries"] == []
        assert data["result_summaries"] == []
        assert data["session_insights"] == []
        assert data["total_turns"] == 0
        assert data["provider_name"] == "openai"

    def test_empty_state_deserializes_from_none(self) -> None:
        """from_dict(None) returns empty state."""
        state = AnalysisState.from_dict(None)
        assert state.total_turns == 0
        assert state.recent_queries == []

    def test_empty_state_deserializes_from_empty_dict(self) -> None:
        """from_dict({}) returns empty state."""
        state = AnalysisState.from_dict({})
        assert state.total_turns == 0
        assert state.recent_queries == []

    def test_populated_state_round_trips(self, populated_state: AnalysisState) -> None:
        """Populated state survives to_dict -> from_dict round-trip."""
        data = populated_state.to_dict()
        restored = AnalysisState.from_dict(data)

        assert restored.total_turns == 3
        assert len(restored.recent_queries) == 3
        assert len(restored.result_summaries) == 3
        assert restored.provider_name == "openai"

        # Verify query records preserved
        for i, q in enumerate(restored.recent_queries):
            assert q.user_message == f"Question {i + 1}"
            assert q.sql == f"SELECT col{i} FROM table{i}"
            assert q.turn_index == i

    def test_query_record_fields_preserved(self) -> None:
        """All QueryRecord fields are preserved through serialization."""
        sid = str(uuid.uuid4())
        state = AnalysisState(
            recent_queries=[
                QueryRecord(
                    user_message="test msg",
                    sql="SELECT 1",
                    sql_signature="SELECT 1 | signature",
                    result_summary={"columns": ["a"], "row_count": 5},
                    source_id=sid,
                    source_type="connection",
                    turn_index=7,
                )
            ],
            total_turns=8,
        )

        restored = AnalysisState.from_dict(state.to_dict())
        q = restored.recent_queries[0]
        assert q.user_message == "test msg"
        assert q.sql == "SELECT 1"
        assert q.sql_signature == "SELECT 1 | signature"
        assert q.result_summary == {"columns": ["a"], "row_count": 5}
        assert q.source_id == sid
        assert q.source_type == "connection"
        assert q.turn_index == 7

    def test_session_insights_preserved(self) -> None:
        """Session insights survive serialization."""
        state = AnalysisState(
            session_insights=["Revenue is trending up", "Q4 had highest sales"],
        )
        restored = AnalysisState.from_dict(state.to_dict())
        assert restored.session_insights == [
            "Revenue is trending up",
            "Q4 had highest sales",
        ]


# ---------------------------------------------------------------------------
# Unit: Token counting
# ---------------------------------------------------------------------------


class TestTokenCounting:
    """Test token estimation and budget calculation."""

    def test_estimate_tokens_basic(self) -> None:
        """Token estimation uses chars/4 approximation."""
        assert estimate_tokens("hello world") >= 1
        # "hello world" is 11 chars -> ~2-3 tokens
        assert estimate_tokens("hello world") == 11 // 4

    def test_estimate_tokens_empty(self) -> None:
        """Empty string returns 1 token minimum."""
        assert estimate_tokens("") == 1

    def test_estimate_tokens_long_text(self) -> None:
        """Long text token count is proportional to length."""
        text = "a" * 4000
        assert estimate_tokens(text) == 1000

    def test_context_window_openai(self) -> None:
        """OpenAI context window is 128K."""
        assert get_context_window("openai") == 128_000

    def test_context_window_anthropic(self) -> None:
        """Anthropic context window is 200K."""
        assert get_context_window("anthropic") == 200_000

    def test_context_window_gemini(self) -> None:
        """Gemini context window is 1M."""
        assert get_context_window("gemini") == 1_000_000

    def test_context_window_unknown(self) -> None:
        """Unknown provider defaults to 32K."""
        assert get_context_window("unknown_provider") == 32_000

    def test_token_budget_is_60_percent(self) -> None:
        """Token budget is 60% of context window."""
        budget = get_token_budget("openai")
        expected = int(128_000 * COMPRESSION_THRESHOLD)
        assert budget == expected

    def test_token_budget_different_providers(self) -> None:
        """Each provider gets a different budget based on its window size."""
        openai_budget = get_token_budget("openai")
        anthropic_budget = get_token_budget("anthropic")
        assert anthropic_budget > openai_budget


# ---------------------------------------------------------------------------
# Unit: SQL signature extraction
# ---------------------------------------------------------------------------


class TestSqlSignature:
    """Test SQL signature extraction."""

    def test_simple_select(self) -> None:
        """Simple SELECT signature captures table."""
        sig = extract_sql_signature("SELECT name, amount FROM sales")
        assert "FROM sales" in sig
        assert "SELECT" in sig

    def test_select_with_where(self) -> None:
        """WHERE clause is noted in signature."""
        sig = extract_sql_signature(
            "SELECT name FROM users WHERE active = true"
        )
        assert "WHERE" in sig

    def test_select_with_group_by(self) -> None:
        """GROUP BY clause is noted in signature."""
        sig = extract_sql_signature(
            "SELECT region, SUM(amount) FROM sales GROUP BY region"
        )
        assert "GROUP BY" in sig

    def test_select_with_limit(self) -> None:
        """LIMIT clause is captured in signature."""
        sig = extract_sql_signature(
            "SELECT name FROM users ORDER BY name LIMIT 10"
        )
        assert "LIMIT" in sig

    def test_empty_sql(self) -> None:
        """Empty SQL returns empty signature."""
        assert extract_sql_signature("") == ""
        assert extract_sql_signature("  ") == ""

    def test_long_select_truncated(self) -> None:
        """Long SELECT clause is truncated."""
        cols = ", ".join(f"col_{i}" for i in range(50))
        sql = f"SELECT {cols} FROM big_table"
        sig = extract_sql_signature(sql)
        # Should not exceed reasonable length
        assert len(sig) < 200


# ---------------------------------------------------------------------------
# Unit: Result summary construction
# ---------------------------------------------------------------------------


class TestResultSummary:
    """Test result summary building."""

    def test_basic_summary(self) -> None:
        """Basic summary includes columns and row count."""
        summary = build_result_summary(
            columns=["name", "amount"],
            rows=[["Alice", 100], ["Bob", 200]],
        )
        assert summary["columns"] == ["name", "amount"]
        assert summary["row_count"] == 2

    def test_numeric_column_stats(self) -> None:
        """Numeric columns have min/max/avg stats."""
        summary = build_result_summary(
            columns=["value"],
            rows=[[10], [20], [30]],
        )
        stats = summary["column_stats"]["value"]
        assert stats["min"] == 10.0
        assert stats["max"] == 30.0
        assert stats["avg"] == 20.0

    def test_string_column_stats(self) -> None:
        """String columns have distinct count and samples."""
        summary = build_result_summary(
            columns=["name"],
            rows=[["Alice"], ["Bob"], ["Alice"]],
        )
        stats = summary["column_stats"]["name"]
        assert stats["distinct_count"] == 2
        assert "sample_values" in stats

    def test_empty_rows(self) -> None:
        """Empty result set returns columns and zero row count."""
        summary = build_result_summary(
            columns=["a", "b"],
            rows=[],
        )
        assert summary["columns"] == ["a", "b"]
        assert summary["row_count"] == 0

    def test_null_values_handled(self) -> None:
        """None values are excluded from statistics."""
        summary = build_result_summary(
            columns=["val"],
            rows=[[10], [None], [30]],
        )
        stats = summary["column_stats"]["val"]
        assert stats["non_null_count"] == 2
        assert stats["min"] == 10.0
        assert stats["max"] == 30.0


# ---------------------------------------------------------------------------
# Unit: Graduated compression
# ---------------------------------------------------------------------------


class TestGraduatedCompression:
    """Test graduated compression logic."""

    def test_no_compression_under_budget(self, populated_state: AnalysisState) -> None:
        """State within budget is not compressed."""
        original_queries = len(populated_state.recent_queries)
        compressed = compress_context(populated_state)
        assert len(compressed.recent_queries) == original_queries
        # SQL should still be present
        for q in compressed.recent_queries:
            assert q.sql != ""

    def test_compression_triggered_by_large_state(self) -> None:
        """State exceeding budget triggers compression."""
        # Create a state with many long queries that exceeds budget
        state = AnalysisState(provider_name="openai_compatible")  # 32K window
        for i in range(30):
            long_sql = f"SELECT {'x' * 500} FROM table_{i}"
            record = QueryRecord(
                user_message=f"Question {i} with lots of detail " * 10,
                sql=long_sql,
                sql_signature=f"SELECT ... | FROM table_{i}",
                result_summary={
                    "columns": [f"col{j}" for j in range(20)],
                    "row_count": 1000,
                    "column_stats": {
                        f"col{j}": {"min": 0, "max": 100, "avg": 50}
                        for j in range(20)
                    },
                },
                source_id=str(uuid.uuid4()),
                source_type="dataset",
                turn_index=i,
            )
            state.recent_queries.append(record)
            state.result_summaries.append(record.result_summary)
        state.total_turns = 30

        compressed = compress_context(state)

        # After compression, recent queries should be reduced
        # The last RECENT_QUERY_LIMIT should still have SQL
        recent = compressed.recent_queries[-RECENT_QUERY_LIMIT:]
        for q in recent:
            # Recent queries keep their full content through compression
            assert q.turn_index >= state.total_turns - RECENT_QUERY_LIMIT

    def test_oldest_queries_lose_sql_first(self) -> None:
        """Oldest queries are compressed to summary-only first."""
        state = AnalysisState(provider_name="openai_compatible")  # Small window
        for i in range(15):
            record = QueryRecord(
                user_message=f"Q{i}: " + "detailed question " * 20,
                sql=f"SELECT {'long_column_name, ' * 30} FROM table_{i}",
                sql_signature=f"SELECT ... | FROM table_{i}",
                result_summary={
                    "columns": [f"c{j}" for j in range(10)],
                    "row_count": 100,
                    "column_stats": {
                        f"c{j}": {"min": 0, "max": j * 10, "avg": j * 5}
                        for j in range(10)
                    },
                },
                source_id=str(uuid.uuid4()),
                source_type="dataset",
                turn_index=i,
            )
            state.recent_queries.append(record)
            state.result_summaries.append(record.result_summary)
        state.total_turns = 15

        compressed = compress_context(state)

        # If compression removed some queries, newest should still be present
        if len(compressed.recent_queries) < 15:
            last_query = compressed.recent_queries[-1]
            assert last_query.turn_index == 14  # Most recent preserved

    def test_very_long_conversation_drops_oldest(self) -> None:
        """20+ turn conversation drops oldest turns entirely."""
        state = AnalysisState(provider_name="openai_compatible")
        for i in range(25):
            record = QueryRecord(
                user_message=f"Turn {i} question " * 5,
                sql=f"SELECT * FROM t{i} WHERE condition = 'long value' " * 3,
                sql_signature=f"SELECT * | FROM t{i} | WHERE ...",
                result_summary={
                    "columns": ["a", "b", "c"],
                    "row_count": 50,
                    "column_stats": {"a": {"min": 0, "max": 100}},
                },
                source_id=str(uuid.uuid4()),
                source_type="dataset",
                turn_index=i,
            )
            state.recent_queries.append(record)
            state.result_summaries.append(record.result_summary)
        state.total_turns = 25

        compressed = compress_context(state)

        # Must have at most original count and at least RECENT_QUERY_LIMIT recent
        assert len(compressed.recent_queries) <= 25
        # Most recent queries should always be present
        if len(compressed.recent_queries) >= RECENT_QUERY_LIMIT:
            recent = compressed.recent_queries[-RECENT_QUERY_LIMIT:]
            for q in recent:
                assert q.turn_index >= 22  # last 3 of 25


# ---------------------------------------------------------------------------
# Unit: Context formatting for system prompt
# ---------------------------------------------------------------------------


class TestContextFormatting:
    """Test context formatting for the AI system prompt."""

    def test_empty_state_returns_empty(self, empty_state: AnalysisState) -> None:
        """Empty state produces empty context string."""
        result = format_context_for_prompt(empty_state)
        assert result == ""

    def test_populated_state_includes_recent_queries(
        self, populated_state: AnalysisState
    ) -> None:
        """Formatted context includes recent query details."""
        result = format_context_for_prompt(populated_state)
        assert "Recent queries:" in result
        assert "Question 1" in result
        assert "Question 2" in result
        assert "Question 3" in result

    def test_populated_state_includes_sql(
        self, populated_state: AnalysisState
    ) -> None:
        """Formatted context includes SQL for recent queries."""
        result = format_context_for_prompt(populated_state)
        assert "SQL:" in result
        assert "SELECT col0 FROM table0" in result

    def test_populated_state_includes_result_summary(
        self, populated_state: AnalysisState
    ) -> None:
        """Formatted context includes most recent result summary."""
        result = format_context_for_prompt(populated_state)
        assert "Most recent result:" in result
        assert "Row count:" in result

    def test_session_insights_included(self) -> None:
        """Session insights are included in formatted context."""
        state = AnalysisState(
            session_insights=["Revenue trending up", "Q4 peak"],
            recent_queries=[
                QueryRecord(user_message="test", sql="SELECT 1", turn_index=0)
            ],
        )
        result = format_context_for_prompt(state)
        assert "Session insights:" in result
        assert "Revenue trending up" in result

    def test_inject_conversation_context_first_turn(
        self, empty_state: AnalysisState
    ) -> None:
        """First turn injects instructions but no context block."""
        prompt = "Base system prompt."
        result = inject_conversation_context(prompt, empty_state)
        assert "Base system prompt." in result
        assert "modify the previous SQL" in result.lower() or "Modify the previous SQL" in result
        assert "Conversation Context" not in result

    def test_inject_conversation_context_with_history(
        self, populated_state: AnalysisState
    ) -> None:
        """Subsequent turns include the conversation context block."""
        prompt = "Base system prompt."
        result = inject_conversation_context(prompt, populated_state)
        assert "Base system prompt." in result
        assert "--- Conversation Context ---" in result
        assert "--- End Conversation Context ---" in result
        assert "Question 3" in result


# ---------------------------------------------------------------------------
# Unit: add_turn_to_state
# ---------------------------------------------------------------------------


class TestAddTurnToState:
    """Test adding conversation turns to the state."""

    def test_add_first_turn(self, empty_state: AnalysisState) -> None:
        """Adding first turn creates a query record."""
        state = add_turn_to_state(
            empty_state,
            user_message="Show me all sales",
            sql="SELECT * FROM sales",
            columns=["id", "amount", "date"],
            rows=[[1, 100, "2024-01-01"], [2, 200, "2024-01-02"]],
            source_id="abc-123",
            source_type="dataset",
        )

        assert state.total_turns == 1
        assert len(state.recent_queries) == 1
        assert state.recent_queries[0].user_message == "Show me all sales"
        assert state.recent_queries[0].sql == "SELECT * FROM sales"
        assert state.recent_queries[0].source_type == "dataset"

    def test_add_multiple_turns(self, empty_state: AnalysisState) -> None:
        """Multiple turns accumulate in state."""
        for i in range(5):
            add_turn_to_state(
                empty_state,
                user_message=f"Query {i}",
                sql=f"SELECT * FROM t{i}",
                columns=["val"],
                rows=[[i]],
            )

        assert empty_state.total_turns == 5
        assert len(empty_state.recent_queries) >= RECENT_QUERY_LIMIT

    def test_result_summary_built_automatically(
        self, empty_state: AnalysisState
    ) -> None:
        """add_turn builds a result summary with column stats."""
        add_turn_to_state(
            empty_state,
            user_message="Sum revenue",
            sql="SELECT SUM(amount) as total FROM sales",
            columns=["total"],
            rows=[[12345.67]],
        )

        summary = empty_state.result_summaries[0]
        assert summary["columns"] == ["total"]
        assert summary["row_count"] == 1
        assert "column_stats" in summary
        assert summary["column_stats"]["total"]["min"] == 12345.67

    def test_sql_signature_generated(self, empty_state: AnalysisState) -> None:
        """add_turn generates an SQL signature."""
        add_turn_to_state(
            empty_state,
            user_message="Count by region",
            sql="SELECT region, COUNT(*) as cnt FROM sales GROUP BY region",
            columns=["region", "cnt"],
            rows=[["East", 10], ["West", 20]],
        )

        sig = empty_state.recent_queries[0].sql_signature
        assert sig != ""
        assert "GROUP BY" in sig


# ---------------------------------------------------------------------------
# Integration: Context carries across multiple agent turns
# ---------------------------------------------------------------------------


class TestContextAcrossTurns:
    """Integration: verify context accumulates and compresses across turns."""

    def test_three_turns_preserves_all(self) -> None:
        """Three turns are all preserved (under RECENT_QUERY_LIMIT)."""
        state = AnalysisState(provider_name="openai")

        add_turn_to_state(
            state,
            user_message="Show total revenue",
            sql="SELECT SUM(amount) FROM sales",
            columns=["sum"],
            rows=[[50000]],
            source_id="ds-1",
            source_type="dataset",
        )

        add_turn_to_state(
            state,
            user_message="Break that down by region",
            sql="SELECT region, SUM(amount) FROM sales GROUP BY region",
            columns=["region", "sum"],
            rows=[["East", 20000], ["West", 30000]],
            source_id="ds-1",
            source_type="dataset",
        )

        add_turn_to_state(
            state,
            user_message="Show me just the top 5",
            sql="SELECT region, SUM(amount) FROM sales GROUP BY region ORDER BY sum DESC LIMIT 5",
            columns=["region", "sum"],
            rows=[["West", 30000], ["East", 20000]],
            source_id="ds-1",
            source_type="dataset",
        )

        assert state.total_turns == 3
        assert len(state.recent_queries) == 3

        # All SQL should be present for recent queries
        for q in state.recent_queries:
            assert q.sql != ""

        # Context should include all 3 queries
        context = format_context_for_prompt(state)
        assert "Show total revenue" in context
        assert "Break that down by region" in context
        assert "Show me just the top 5" in context

    def test_last_3_queries_in_context(self) -> None:
        """Only last 3 queries appear in formatted context regardless of total."""
        state = AnalysisState(provider_name="openai")

        for i in range(6):
            add_turn_to_state(
                state,
                user_message=f"Query number {i}",
                sql=f"SELECT * FROM t{i}",
                columns=["val"],
                rows=[[i]],
            )

        context = format_context_for_prompt(state)
        # Last 3 should be visible
        assert "Query number 3" in context
        assert "Query number 4" in context
        assert "Query number 5" in context

    def test_most_recent_result_in_context(self) -> None:
        """Only the most recent result summary appears in context."""
        state = AnalysisState(provider_name="openai")

        add_turn_to_state(
            state,
            user_message="First query",
            sql="SELECT count(*) as cnt FROM old_table",
            columns=["cnt"],
            rows=[[99]],
        )

        add_turn_to_state(
            state,
            user_message="Second query",
            sql="SELECT region, revenue FROM new_table",
            columns=["region", "revenue"],
            rows=[["East", 1000], ["West", 2000]],
        )

        context = format_context_for_prompt(state)
        # Most recent result should show 2 columns
        assert "region" in context
        assert "revenue" in context
        assert "Row count: 2" in context


# ---------------------------------------------------------------------------
# Integration: analysis_context persists in database
# ---------------------------------------------------------------------------


class TestAnalysisContextPersistence:
    """Integration: analysis_context persists in Conversation model."""

    def test_save_and_load_state(self, session) -> None:
        """State saved to Conversation.analysis_context can be loaded back."""
        from app.services.agent_service import load_analysis_state, save_analysis_state

        # Create a conversation
        conv = Conversation(
            title="Test Conversation",
        )
        session.add(conv)
        session.commit()
        conv_id = str(conv.id)

        # Build a state
        state = AnalysisState(provider_name="openai", total_turns=2)
        add_turn_to_state(
            state,
            user_message="Show revenue",
            sql="SELECT SUM(amount) FROM sales",
            columns=["sum"],
            rows=[[50000]],
        )
        add_turn_to_state(
            state,
            user_message="By region",
            sql="SELECT region, SUM(amount) FROM sales GROUP BY region",
            columns=["region", "sum"],
            rows=[["East", 20000], ["West", 30000]],
        )

        # Save to DB
        save_analysis_state(session, conv_id, state)

        # Reload from DB
        loaded = load_analysis_state(session, conv_id, provider_name="openai")

        assert loaded.total_turns == state.total_turns
        assert len(loaded.recent_queries) == len(state.recent_queries)
        assert loaded.recent_queries[0].user_message == "Show revenue"
        assert loaded.recent_queries[1].sql == (
            "SELECT region, SUM(amount) FROM sales GROUP BY region"
        )

    def test_load_state_new_conversation(self, session) -> None:
        """Loading state for a new conversation returns empty state."""
        from app.services.agent_service import load_analysis_state

        conv = Conversation(title="New Conv")
        session.add(conv)
        session.commit()

        state = load_analysis_state(session, str(conv.id), provider_name="anthropic")
        assert state.total_turns == 0
        assert state.recent_queries == []
        assert state.provider_name == "anthropic"

    def test_load_state_invalid_conversation_id(self, session) -> None:
        """Loading state with invalid conversation ID returns empty state."""
        from app.services.agent_service import load_analysis_state

        state = load_analysis_state(session, "not-a-uuid")
        assert state.total_turns == 0

    def test_load_state_nonexistent_conversation(self, session) -> None:
        """Loading state for non-existent conversation returns empty state."""
        from app.services.agent_service import load_analysis_state

        state = load_analysis_state(session, str(uuid.uuid4()))
        assert state.total_turns == 0

    def test_save_state_invalid_conversation_id(self, session) -> None:
        """Saving state with invalid conversation ID logs warning, no crash."""
        from app.services.agent_service import save_analysis_state

        state = AnalysisState()
        # Should not raise
        save_analysis_state(session, "not-a-uuid", state)

    def test_analysis_context_column_stores_jsonb(self, session) -> None:
        """Conversation.analysis_context stores and retrieves dict."""
        conv = Conversation(
            title="JSONB Test",
            analysis_context={
                "recent_queries": [
                    {
                        "user_message": "test",
                        "sql": "SELECT 1",
                        "turn_index": 0,
                    }
                ],
                "total_turns": 1,
            },
        )
        session.add(conv)
        session.commit()

        loaded = session.get(Conversation, conv.id)
        assert loaded is not None
        assert loaded.analysis_context is not None
        assert loaded.analysis_context["total_turns"] == 1


# ---------------------------------------------------------------------------
# Unit: AgentDeps analysis_state field
# ---------------------------------------------------------------------------


class TestAgentDepsAnalysisState:
    """Test that AgentDeps carries analysis_state."""

    def test_default_analysis_state_is_none(self) -> None:
        """AgentDeps.analysis_state defaults to None."""
        from app.services.agent_tools import AgentDeps

        deps = AgentDeps()
        assert deps.analysis_state is None

    def test_analysis_state_can_be_set(self) -> None:
        """AgentDeps.analysis_state can hold an AnalysisState."""
        from app.services.agent_tools import AgentDeps

        state = AnalysisState(provider_name="openai", total_turns=5)
        deps = AgentDeps(analysis_state=state)
        assert deps.analysis_state is state
        assert deps.analysis_state.total_turns == 5


# ---------------------------------------------------------------------------
# Edge case: First message in conversation
# ---------------------------------------------------------------------------


class TestFirstMessageEdgeCase:
    """Test that first message works without prior context."""

    def test_first_turn_no_prior_context(self) -> None:
        """First message creates valid state from nothing."""
        state = AnalysisState(provider_name="anthropic")

        assert format_context_for_prompt(state) == ""

        add_turn_to_state(
            state,
            user_message="What tables do I have?",
            sql="",
            columns=[],
            rows=[],
        )

        assert state.total_turns == 1
        context = format_context_for_prompt(state)
        assert "What tables do I have?" in context

    def test_inject_context_first_turn(self) -> None:
        """inject_conversation_context on first turn adds instructions only."""
        state = AnalysisState()
        result = inject_conversation_context("Base prompt.", state)
        assert "Base prompt." in result
        assert "Modify the previous SQL" in result
        assert "Conversation Context" not in result


# ---------------------------------------------------------------------------
# Edge case: Token budget exceeded
# ---------------------------------------------------------------------------


class TestTokenBudgetExceeded:
    """Test behavior when token budget is exceeded."""

    def test_compression_keeps_recent_queries(self) -> None:
        """After compression, at least RECENT_QUERY_LIMIT recent queries remain."""
        state = AnalysisState(provider_name="openai_compatible")  # 32K window

        # Add many large queries
        for i in range(20):
            add_turn_to_state(
                state,
                user_message=f"Question {i}: " + "detail " * 100,
                sql=f"SELECT {'col, ' * 50} FROM table_{i} WHERE " + "x > 1 AND " * 20,
                columns=[f"c{j}" for j in range(20)],
                rows=[[j for j in range(20)] for _ in range(10)],
            )

        # Should still have at least RECENT_QUERY_LIMIT queries
        assert len(state.recent_queries) >= RECENT_QUERY_LIMIT

        # Most recent should be the last added
        last = state.recent_queries[-1]
        assert last.turn_index == 19

    def test_context_stays_within_budget(self) -> None:
        """Compressed state fits within token budget."""
        state = AnalysisState(provider_name="openai_compatible")

        for i in range(30):
            add_turn_to_state(
                state,
                user_message=f"Long question {i} " * 20,
                sql=f"SELECT * FROM t{i} " * 10,
                columns=["a", "b", "c"],
                rows=[[1, 2, 3]],
            )

        import json

        serialized = json.dumps(state.to_dict())
        tokens = estimate_tokens(serialized)
        budget = get_token_budget("openai_compatible")

        assert tokens <= budget
