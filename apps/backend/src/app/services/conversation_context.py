"""Conversational context management with graduated summarization.

Implements session memory for context-aware follow-ups using the
AnalysisState dataclass. The AI maintains conversation history with
graduated compression to manage token budgets.

Graduated compression levels:
    Level 0 (recent): Full SQL + full result summary
    Level 1 (mid):    SQL signature + result summary
    Level 2 (old):    Result summary only

Token counting:
    Uses character-based approximation (chars / 4) for all providers.
    This avoids a dependency on tiktoken while remaining accurate enough
    for budget management purposes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Token budget constants
# ---------------------------------------------------------------------------

# Default context window sizes by provider (in tokens)
CONTEXT_WINDOW_SIZES: dict[str, int] = {
    "openai": 128_000,       # GPT-4o
    "anthropic": 200_000,    # Claude
    "gemini": 1_000_000,     # Gemini 2.0 Flash
    "openai_compatible": 32_000,  # Conservative default
}

# Trigger compression when context exceeds this fraction of the window
COMPRESSION_THRESHOLD = 0.60

# Number of recent queries to keep in full detail
RECENT_QUERY_LIMIT = 3


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class QueryRecord:
    """A single query turn in the conversation history.

    Attributes:
        user_message: The original user question.
        sql: The generated SQL query.
        sql_signature: Abbreviated SQL (table + aggregation summary).
        result_summary: Summary of query results (columns, row count, stats).
        source_id: UUID of the data source queried.
        source_type: 'dataset' or 'connection'.
        turn_index: Position in the conversation (0-based).
    """

    user_message: str = ""
    sql: str = ""
    sql_signature: str = ""
    result_summary: dict[str, Any] = field(default_factory=dict)
    source_id: str = ""
    source_type: str = ""
    turn_index: int = 0


@dataclass
class AnalysisState:
    """Session memory state for context-aware conversation follow-ups.

    Tracks recent queries, result summaries, and session-level insights
    to enable the AI to reference prior context in follow-up responses.

    Stored in the Conversation.analysis_context JSONB column.
    """

    recent_queries: list[QueryRecord] = field(default_factory=list)
    result_summaries: list[dict[str, Any]] = field(default_factory=list)
    session_insights: list[str] = field(default_factory=list)
    total_turns: int = 0
    provider_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary for JSONB storage."""
        return {
            "recent_queries": [
                {
                    "user_message": q.user_message,
                    "sql": q.sql,
                    "sql_signature": q.sql_signature,
                    "result_summary": q.result_summary,
                    "source_id": q.source_id,
                    "source_type": q.source_type,
                    "turn_index": q.turn_index,
                }
                for q in self.recent_queries
            ],
            "result_summaries": self.result_summaries,
            "session_insights": self.session_insights,
            "total_turns": self.total_turns,
            "provider_name": self.provider_name,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> AnalysisState:
        """Deserialize from a JSON dictionary (e.g., from JSONB column)."""
        if not data:
            return cls()

        queries = []
        for q in data.get("recent_queries", []):
            queries.append(
                QueryRecord(
                    user_message=q.get("user_message", ""),
                    sql=q.get("sql", ""),
                    sql_signature=q.get("sql_signature", ""),
                    result_summary=q.get("result_summary", {}),
                    source_id=q.get("source_id", ""),
                    source_type=q.get("source_type", ""),
                    turn_index=q.get("turn_index", 0),
                )
            )

        return cls(
            recent_queries=queries,
            result_summaries=data.get("result_summaries", []),
            session_insights=data.get("session_insights", []),
            total_turns=data.get("total_turns", 0),
            provider_name=data.get("provider_name", ""),
        )


# ---------------------------------------------------------------------------
# Token counting
# ---------------------------------------------------------------------------


def estimate_tokens(text: str) -> int:
    """Estimate token count using character-based approximation.

    Uses chars / 4 as a rough but fast approximation. This avoids
    requiring tiktoken as a dependency while being accurate enough
    for budget management (typically within 10-20% of actual count).

    Args:
        text: The text to estimate tokens for.

    Returns:
        Estimated token count.
    """
    return max(1, len(text) // 4)


def get_context_window(provider_name: str) -> int:
    """Get the context window size for a provider.

    Args:
        provider_name: Provider identifier (openai, anthropic, gemini, etc.).

    Returns:
        Context window size in tokens.
    """
    return CONTEXT_WINDOW_SIZES.get(provider_name, 32_000)


def get_token_budget(provider_name: str) -> int:
    """Get the token budget for conversation context (60% of context window).

    Args:
        provider_name: Provider identifier.

    Returns:
        Maximum token count for conversation context.
    """
    window = get_context_window(provider_name)
    return int(window * COMPRESSION_THRESHOLD)


# ---------------------------------------------------------------------------
# SQL signature extraction
# ---------------------------------------------------------------------------


def extract_sql_signature(sql: str) -> str:
    """Extract a compact SQL signature from a full SQL query.

    Captures the key structural elements: tables, aggregations, filters.
    Used as a compressed representation during graduated summarization.

    Args:
        sql: The full SQL query text.

    Returns:
        A compact signature string like "SELECT agg(col) FROM table WHERE cond".
    """
    if not sql or not sql.strip():
        return ""

    sql_upper = sql.upper().strip()
    parts: list[str] = []

    # Extract SELECT clause (simplified)
    if "SELECT" in sql_upper:
        # Get the SELECT ... FROM portion
        select_idx = sql_upper.index("SELECT")
        from_idx = sql_upper.find("FROM", select_idx)
        if from_idx > 0:
            select_part = sql[select_idx:from_idx].strip()
            # Truncate long select lists
            if len(select_part) > 80:
                select_part = select_part[:77] + "..."
            parts.append(select_part)

    # Extract FROM clause (just table names)
    if "FROM" in sql_upper:
        from_idx = sql_upper.index("FROM")
        # Find next keyword after FROM
        next_kw_idx = len(sql)
        for kw in ("WHERE", "GROUP BY", "ORDER BY", "LIMIT", "HAVING", "JOIN"):
            kw_idx = sql_upper.find(kw, from_idx + 4)
            if kw_idx > 0:
                next_kw_idx = min(next_kw_idx, kw_idx)
        from_part = sql[from_idx:next_kw_idx].strip()
        parts.append(from_part)

    # Note key clauses present
    clauses = []
    if "WHERE" in sql_upper:
        clauses.append("WHERE ...")
    if "GROUP BY" in sql_upper:
        clauses.append("GROUP BY ...")
    if "ORDER BY" in sql_upper:
        clauses.append("ORDER BY ...")
    if "LIMIT" in sql_upper:
        # Extract the LIMIT value
        limit_idx = sql_upper.index("LIMIT")
        limit_val = sql[limit_idx:].strip()
        if len(limit_val) > 20:
            limit_val = limit_val[:20]
        clauses.append(limit_val)
    if clauses:
        parts.append(" ".join(clauses))

    return " | ".join(parts) if parts else sql[:100]


# ---------------------------------------------------------------------------
# Result summary construction
# ---------------------------------------------------------------------------


def build_result_summary(
    columns: list[str],
    rows: list[list[Any]],
    sql: str = "",
) -> dict[str, Any]:
    """Build a compact result summary from query results.

    Includes column names, row count, and basic column statistics
    (min, max, avg for numeric columns; distinct count for strings).

    Args:
        columns: Column names from the query result.
        rows: Row data from the query result.
        sql: The SQL query that produced the results.

    Returns:
        A dictionary with columns, row_count, and column_stats.
    """
    summary: dict[str, Any] = {
        "columns": columns,
        "row_count": len(rows),
    }

    if not rows or not columns:
        return summary

    # Compute per-column statistics
    col_stats: dict[str, dict[str, Any]] = {}
    for col_idx, col_name in enumerate(columns):
        values = [row[col_idx] for row in rows if col_idx < len(row) and row[col_idx] is not None]
        if not values:
            col_stats[col_name] = {"non_null_count": 0}
            continue

        stats: dict[str, Any] = {"non_null_count": len(values)}

        # Check if numeric
        numeric_values: list[float] = []
        for v in values:
            if isinstance(v, (int, float)):
                numeric_values.append(float(v))

        if numeric_values and len(numeric_values) == len(values):
            stats["min"] = min(numeric_values)
            stats["max"] = max(numeric_values)
            stats["avg"] = round(sum(numeric_values) / len(numeric_values), 2)
        else:
            # String-like: count distinct values
            str_values = [str(v) for v in values]
            stats["distinct_count"] = len(set(str_values))
            # Include sample values (up to 5)
            samples = list(set(str_values))[:5]
            stats["sample_values"] = samples

        col_stats[col_name] = stats

    summary["column_stats"] = col_stats
    return summary


# ---------------------------------------------------------------------------
# Context update
# ---------------------------------------------------------------------------


def add_turn_to_state(
    state: AnalysisState,
    user_message: str,
    sql: str,
    columns: list[str],
    rows: list[list[Any]],
    source_id: str = "",
    source_type: str = "",
) -> AnalysisState:
    """Add a new conversation turn to the analysis state.

    Appends the query record to recent_queries, builds a result summary,
    and increments the turn counter. If the state exceeds the token
    budget, triggers graduated compression.

    Args:
        state: Current analysis state.
        user_message: The user's question.
        sql: The generated SQL query.
        columns: Result column names.
        rows: Result row data.
        source_id: UUID of the data source.
        source_type: 'dataset' or 'connection'.

    Returns:
        Updated AnalysisState (same object, mutated in place).
    """
    result_summary = build_result_summary(columns, rows, sql)
    sql_sig = extract_sql_signature(sql)

    record = QueryRecord(
        user_message=user_message,
        sql=sql,
        sql_signature=sql_sig,
        result_summary=result_summary,
        source_id=source_id,
        source_type=source_type,
        turn_index=state.total_turns,
    )

    state.recent_queries.append(record)
    state.result_summaries.append(result_summary)
    state.total_turns += 1

    # Check token budget and compress if needed
    state = compress_context(state)

    return state


# ---------------------------------------------------------------------------
# Graduated compression
# ---------------------------------------------------------------------------


def compress_context(state: AnalysisState) -> AnalysisState:
    """Apply graduated compression to keep context within token budget.

    Compression levels (applied from oldest to newest):
        Level 2 (oldest): Remove SQL entirely, keep only result summary
        Level 1 (middle): Replace full SQL with SQL signature
        Level 0 (recent): Keep everything in full detail

    The most recent RECENT_QUERY_LIMIT queries are always kept at Level 0.
    Older queries are progressively compressed until the token budget is met.

    Args:
        state: The analysis state to compress.

    Returns:
        The compressed state (same object, mutated).
    """
    budget = get_token_budget(state.provider_name)
    current_tokens = _estimate_state_tokens(state)

    if current_tokens <= budget:
        return state

    queries = state.recent_queries
    n = len(queries)

    if n <= RECENT_QUERY_LIMIT:
        # Not enough queries to compress; trim result_summaries if needed
        while len(state.result_summaries) > n:
            state.result_summaries.pop(0)
        return state

    # Phase 1: Compress oldest queries (beyond last 6) to Level 2 (summary only)
    mid_boundary = max(0, n - RECENT_QUERY_LIMIT * 2)
    for i in range(mid_boundary):
        queries[i].sql = ""
        queries[i].sql_signature = ""
        queries[i].user_message = _truncate(queries[i].user_message, 50)

    # Re-check budget
    current_tokens = _estimate_state_tokens(state)
    if current_tokens <= budget:
        return state

    # Phase 2: Compress mid-range queries to Level 1 (signature + summary)
    for i in range(mid_boundary, max(0, n - RECENT_QUERY_LIMIT)):
        queries[i].sql = ""  # Remove full SQL, keep signature
        queries[i].user_message = _truncate(queries[i].user_message, 80)

    # Re-check budget
    current_tokens = _estimate_state_tokens(state)
    if current_tokens <= budget:
        return state

    # Phase 3: If still over budget, drop oldest queries entirely
    while len(state.recent_queries) > RECENT_QUERY_LIMIT:
        state.recent_queries.pop(0)

    # Trim result summaries to match
    while len(state.result_summaries) > len(state.recent_queries):
        state.result_summaries.pop(0)

    # Phase 4: Trim session insights if still over
    current_tokens = _estimate_state_tokens(state)
    while current_tokens > budget and state.session_insights:
        state.session_insights.pop(0)
        current_tokens = _estimate_state_tokens(state)

    return state


def _truncate(text: str, max_len: int) -> str:
    """Truncate text to max_len, adding '...' if truncated."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _estimate_state_tokens(state: AnalysisState) -> int:
    """Estimate the total token count for the serialized state."""
    serialized = json.dumps(state.to_dict())
    return estimate_tokens(serialized)


# ---------------------------------------------------------------------------
# Context formatting for system prompt
# ---------------------------------------------------------------------------


def format_context_for_prompt(state: AnalysisState) -> str:
    """Format the analysis state into a text block for the AI system prompt.

    Includes the last N queries with SQL, the most recent result summary,
    and session insights. The format is designed to enable context-aware
    follow-ups like "show me just the top 5" or "break that down by region".

    Args:
        state: The current analysis state.

    Returns:
        Formatted context string to inject into the system prompt.
    """
    if not state.recent_queries and not state.session_insights:
        return ""

    sections: list[str] = []

    # Section 1: Recent queries with SQL
    if state.recent_queries:
        recent = state.recent_queries[-RECENT_QUERY_LIMIT:]
        query_lines: list[str] = []
        for q in recent:
            line = f"Turn {q.turn_index}: \"{q.user_message}\""
            if q.sql:
                line += f"\n  SQL: {q.sql}"
            elif q.sql_signature:
                line += f"\n  SQL (summary): {q.sql_signature}"
            if q.source_type:
                line += f"\n  Source: {q.source_type} ({q.source_id})"
            query_lines.append(line)

        sections.append(
            "Recent queries:\n" + "\n\n".join(query_lines)
        )

    # Section 2: Most recent result summary
    if state.result_summaries:
        latest = state.result_summaries[-1]
        summary_lines: list[str] = [
            f"Columns: {', '.join(latest.get('columns', []))}",
            f"Row count: {latest.get('row_count', 0)}",
        ]
        col_stats = latest.get("column_stats", {})
        if col_stats:
            for col_name, stats in col_stats.items():
                stat_parts = []
                if "min" in stats:
                    stat_parts.append(f"min={stats['min']}")
                if "max" in stats:
                    stat_parts.append(f"max={stats['max']}")
                if "avg" in stats:
                    stat_parts.append(f"avg={stats['avg']}")
                if "distinct_count" in stats:
                    stat_parts.append(f"distinct={stats['distinct_count']}")
                if stat_parts:
                    summary_lines.append(f"  {col_name}: {', '.join(stat_parts)}")
        sections.append(
            "Most recent result:\n" + "\n".join(summary_lines)
        )

    # Section 3: Session insights
    if state.session_insights:
        sections.append(
            "Session insights:\n" + "\n".join(f"- {i}" for i in state.session_insights[-5:])
        )

    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Context-aware system prompt injection
# ---------------------------------------------------------------------------

CONTEXT_AWARE_INSTRUCTIONS = """\

When the user references previous results or asks to modify a prior query:
- "Show me just the top 5" → Modify the previous SQL by adding/changing LIMIT 5, \
do not generate a completely new query from scratch.
- "Break that down by region" → Reference the prior query and add a GROUP BY \
or additional dimension.
- Reference earlier findings in your responses when relevant \
(e.g., "Earlier you found that Q4 revenue was $2.3M").
- If the user asks about something discussed earlier, use the conversation \
context below to provide accurate references.
"""


def inject_conversation_context(
    system_prompt: str,
    state: AnalysisState,
) -> str:
    """Inject conversation context and context-aware instructions into the system prompt.

    Args:
        system_prompt: The base system prompt.
        state: The current analysis state.

    Returns:
        System prompt with conversation context appended.
    """
    context_text = format_context_for_prompt(state)

    if not context_text:
        # First turn: just add the instructions for future reference
        return system_prompt + CONTEXT_AWARE_INSTRUCTIONS

    return (
        system_prompt
        + CONTEXT_AWARE_INSTRUCTIONS
        + "\n--- Conversation Context ---\n"
        + context_text
        + "\n--- End Conversation Context ---"
    )
