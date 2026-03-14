"""Natural language to SQL query generation pipeline.

Translates user questions in natural language into executable SQL queries
using the Pydantic AI agent. The pipeline:

1. Receives a natural language question
2. Uses schema context to determine the relevant data source
3. Generates SQL via the AI agent (DuckDB dialect for datasets,
   PostgreSQL/MySQL for connections)
4. Executes the query with read-only enforcement and timeout
5. Self-corrects on SQL errors (up to max_retries attempts)
6. Returns structured results with a natural language explanation

Self-correction loop:
- On query failure, captures the error + failed SQL and sends them
  back to the AI agent for correction
- Handles: syntax errors, column/table not found, type mismatches,
  ambiguous references
- Tracks all attempts and surfaces progress via an optional SSE callback
- Non-retryable errors (timeout, read-only violations, auth failures,
  connection lost) skip the retry loop immediately

Edge case handling:
- Ambiguous questions -> agent asks a clarifying question
- No relevant data source -> agent reports no matching data
- Non-existent columns -> caught by self-correction loop
- Broad queries without LIMIT -> agent adds LIMIT by default
- Same error repeated -> AI receives full history to try different approach
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import distinct, select
from sqlalchemy.orm import Session

from app.logging import get_logger
from app.models.orm import Dataset, SchemaMetadata
from app.services.agent_service import (
    AgentDeps,
    NoProviderConfiguredError,
    create_agent,
)
from app.services.query_service import QueryService, is_read_only_sql
from app.services.schema_context import build_schema_context

logger = get_logger(__name__)

# Maximum rows to return when the AI doesn't specify a LIMIT
DEFAULT_RESULT_LIMIT = 1000

# Type alias for the optional SSE progress callback.
# Called with (attempt_number, max_retries, error_message, error_category).
RetryProgressCallback = Callable[[int, int, str, str], Awaitable[None]]


# ---------------------------------------------------------------------------
# Error classification for retry decisions
# ---------------------------------------------------------------------------

# Error categories used for classifying SQL execution errors.
class ErrorCategory:
    """Constants for SQL error categories."""

    SYNTAX = "syntax_error"
    COLUMN_NOT_FOUND = "column_not_found"
    TABLE_NOT_FOUND = "table_not_found"
    TYPE_MISMATCH = "type_mismatch"
    AMBIGUOUS_REFERENCE = "ambiguous_reference"
    TIMEOUT = "timeout"
    READ_ONLY_VIOLATION = "read_only_violation"
    CONNECTION_LOST = "connection_lost"
    PERMISSION_DENIED = "permission_denied"
    UNKNOWN = "unknown"


# Errors that should NOT be retried because re-generating SQL won't help.
_NON_RETRYABLE_CATEGORIES = frozenset({
    ErrorCategory.TIMEOUT,
    ErrorCategory.READ_ONLY_VIOLATION,
    ErrorCategory.CONNECTION_LOST,
    ErrorCategory.PERMISSION_DENIED,
})

# Compiled patterns for classifying error messages.
_ERROR_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Column / table not found
    (re.compile(r"column\b.*\bnot found\b", re.I), ErrorCategory.COLUMN_NOT_FOUND),
    (re.compile(r"no such column", re.I), ErrorCategory.COLUMN_NOT_FOUND),
    (re.compile(r"unknown column", re.I), ErrorCategory.COLUMN_NOT_FOUND),
    (re.compile(r"column\b.*\bdoes not exist\b", re.I), ErrorCategory.COLUMN_NOT_FOUND),
    (re.compile(r"table\b.*\bnot found\b", re.I), ErrorCategory.TABLE_NOT_FOUND),
    (re.compile(r"no such table", re.I), ErrorCategory.TABLE_NOT_FOUND),
    (re.compile(r"relation\b.*\bdoes not exist\b", re.I), ErrorCategory.TABLE_NOT_FOUND),
    (re.compile(r"table\b.*\bdoes not exist\b", re.I), ErrorCategory.TABLE_NOT_FOUND),
    # Type mismatches
    (re.compile(r"type mismatch", re.I), ErrorCategory.TYPE_MISMATCH),
    (re.compile(r"cannot (cast|convert)", re.I), ErrorCategory.TYPE_MISMATCH),
    (re.compile(r"invalid input syntax for type", re.I), ErrorCategory.TYPE_MISMATCH),
    (re.compile(r"conversion failed", re.I), ErrorCategory.TYPE_MISMATCH),
    # Ambiguous references
    (re.compile(r"ambiguous", re.I), ErrorCategory.AMBIGUOUS_REFERENCE),
    # Syntax errors
    (re.compile(r"syntax error", re.I), ErrorCategory.SYNTAX),
    (re.compile(r"parse error", re.I), ErrorCategory.SYNTAX),
    (re.compile(r"unexpected token", re.I), ErrorCategory.SYNTAX),
    (re.compile(r"near\s+\"", re.I), ErrorCategory.SYNTAX),
    # Non-retryable: connection
    (re.compile(r"connection (lost|refused|reset|closed)", re.I), ErrorCategory.CONNECTION_LOST),
    (re.compile(r"could not connect", re.I), ErrorCategory.CONNECTION_LOST),
    # Non-retryable: permission
    (re.compile(r"permission denied", re.I), ErrorCategory.PERMISSION_DENIED),
    (re.compile(r"access denied", re.I), ErrorCategory.PERMISSION_DENIED),
    (re.compile(r"insufficient privileges", re.I), ErrorCategory.PERMISSION_DENIED),
    # Non-retryable: timeout (handled by status check too, but belt-and-suspenders)
    (re.compile(r"timeout|timed out|statement_timeout", re.I), ErrorCategory.TIMEOUT),
]


def classify_error(error_message: str) -> str:
    """Classify a SQL error message into an ErrorCategory.

    Returns one of the ErrorCategory constants. Checks patterns in order,
    returning the first match. Falls back to ErrorCategory.UNKNOWN.
    """
    for pattern, category in _ERROR_PATTERNS:
        if pattern.search(error_message):
            return category
    return ErrorCategory.UNKNOWN


def is_retryable_error(error_message: str, status: str = "error") -> bool:
    """Determine whether an error should trigger the self-correction loop.

    Non-retryable errors (timeout, read-only violations, connection lost,
    permission denied) return False. Everything else returns True because
    the AI agent may be able to fix it by generating different SQL.
    """
    if status == "timeout":
        return False
    if "READ_ONLY" in error_message.upper():
        return False
    category = classify_error(error_message)
    return category not in _NON_RETRYABLE_CATEGORIES


# ---------------------------------------------------------------------------
# Structured output models for the AI agent
# ---------------------------------------------------------------------------


class SQLGenerationResult(BaseModel):
    """Structured output from the AI agent for SQL generation.

    The agent populates either (sql + source_id + source_type) for a
    query, or sets needs_clarification=True with a clarifying_question.
    """

    sql: str | None = Field(
        default=None,
        description="The generated SQL query. None if clarification is needed.",
    )
    source_id: str | None = Field(
        default=None,
        description="UUID of the dataset or connection to query.",
    )
    source_type: str | None = Field(
        default=None,
        description="Type of source: 'dataset' or 'connection'.",
    )
    explanation: str = Field(
        default="",
        description="Natural language explanation of the query and approach.",
    )
    needs_clarification: bool = Field(
        default=False,
        description="True if the question is ambiguous and needs refinement.",
    )
    clarifying_question: str | None = Field(
        default=None,
        description="Question to ask the user for clarification.",
    )
    no_relevant_source: bool = Field(
        default=False,
        description="True if no data source matches the question.",
    )
    no_source_message: str | None = Field(
        default=None,
        description="Message explaining why no source was found.",
    )


# ---------------------------------------------------------------------------
# Pipeline result
# ---------------------------------------------------------------------------


@dataclass
class NLQueryResult:
    """Result of the NL-to-SQL pipeline."""

    # Query execution results (populated when SQL was generated and executed)
    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    row_count: int = 0
    execution_time_ms: int = 0

    # SQL and source info
    sql: str | None = None
    source_id: str | None = None
    source_type: str | None = None

    # AI explanation
    explanation: str = ""

    # Clarification flow
    needs_clarification: bool = False
    clarifying_question: str | None = None

    # No source found
    no_relevant_source: bool = False
    no_source_message: str | None = None

    # Error info
    error: str | None = None

    # Self-correction tracking
    attempts: int = 0
    correction_history: list[dict[str, str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Source resolution helpers
# ---------------------------------------------------------------------------


def _resolve_source_mapping(session: Session) -> dict[str, dict[str, str]]:
    """Build a mapping of table_name -> {source_id, source_type} from SchemaMetadata.

    Also includes dataset names as keys mapping to their DuckDB table names,
    so the AI can refer to sources by human-readable names.
    """
    stmt = (
        select(
            distinct(SchemaMetadata.table_name),
            SchemaMetadata.source_id,
            SchemaMetadata.source_type,
        )
        .order_by(SchemaMetadata.table_name)
    )
    rows = session.execute(stmt).all()

    mapping: dict[str, dict[str, str]] = {}
    for table_name, source_id, source_type in rows:
        mapping[table_name] = {
            "source_id": str(source_id),
            "source_type": source_type,
        }

    # Also add dataset name -> table_name mapping for friendly lookups
    dataset_ids = {
        info["source_id"]
        for info in mapping.values()
        if info["source_type"] == "dataset"
    }
    if dataset_ids:
        ds_stmt = select(Dataset.id, Dataset.name, Dataset.duckdb_table_name).where(
            Dataset.id.in_([uuid.UUID(sid) for sid in dataset_ids])
        )
        for ds_id, ds_name, duckdb_name in session.execute(ds_stmt).all():
            if duckdb_name in mapping:
                mapping[ds_name.lower()] = mapping[duckdb_name]

    return mapping


def _find_source_for_table(
    table_name: str,
    source_mapping: dict[str, dict[str, str]],
) -> dict[str, str] | None:
    """Look up the source info for a table name (case-insensitive)."""
    # Exact match
    if table_name in source_mapping:
        return source_mapping[table_name]

    # Case-insensitive match
    lower = table_name.lower()
    for key, value in source_mapping.items():
        if key.lower() == lower:
            return value

    return None


# ---------------------------------------------------------------------------
# SQL validation and safety
# ---------------------------------------------------------------------------


def _ensure_limit(sql: str, limit: int = DEFAULT_RESULT_LIMIT) -> str:
    """Add a LIMIT clause if the SQL doesn't already have one.

    Only applies to top-level SELECT statements (not subqueries).
    """
    stripped = sql.strip().rstrip(";")

    # Check if there's already a LIMIT clause at the top level
    # Simple heuristic: check if LIMIT appears after the last FROM/WHERE/GROUP/ORDER
    if re.search(r"\bLIMIT\b", stripped, re.IGNORECASE):
        return sql

    return f"{stripped}\nLIMIT {limit}"


# ---------------------------------------------------------------------------
# Core NL-to-SQL pipeline
# ---------------------------------------------------------------------------


class NLQueryService:
    """Orchestrates natural language to SQL query generation and execution.

    Uses the Pydantic AI agent to translate questions into SQL, executes
    them against the appropriate data source, and handles self-correction
    on errors.
    """

    def __init__(
        self,
        query_service: QueryService,
        max_retries: int = 3,
    ) -> None:
        self._query_service = query_service
        self._max_retries = max_retries

    async def process_question(
        self,
        question: str,
        session: Session,
        conversation_id: str | None = None,
        provider_id: str | None = None,
        on_retry_progress: RetryProgressCallback | None = None,
    ) -> NLQueryResult:
        """Process a natural language question through the NL-to-SQL pipeline.

        Args:
            question: The user's natural language question.
            session: Active SQLAlchemy session for schema queries.
            conversation_id: Optional conversation context.
            provider_id: Optional AI provider ID to use.
            on_retry_progress: Optional async callback invoked before each
                self-correction retry attempt, for surfacing progress via SSE.
                Called with ``(attempt, max_retries, error_msg, error_category)``.

        Returns:
            NLQueryResult with query results, explanation, or clarification request.
        """
        # 1. Build schema context and source mapping
        schema_result = build_schema_context(session)
        source_mapping = _resolve_source_mapping(session)

        if not source_mapping:
            return NLQueryResult(
                no_relevant_source=True,
                no_source_message=(
                    "No data sources are available. "
                    "Please upload a file (CSV, Excel, Parquet, JSON) "
                    "or connect an external database to get started."
                ),
                explanation="No data sources found to query.",
            )

        # 2. Build source context for the AI
        source_list = _build_source_list(source_mapping)

        # 3. Generate SQL via AI
        generation = await self._generate_sql(
            question=question,
            schema_context=schema_result.context_text,
            source_list=source_list,
            source_mapping=source_mapping,
            provider_id=provider_id,
            conversation_id=conversation_id,
        )

        # 4. Handle clarification requests
        if generation.needs_clarification:
            return NLQueryResult(
                needs_clarification=True,
                clarifying_question=generation.clarifying_question,
                explanation=generation.explanation,
            )

        # 5. Handle no relevant source
        if generation.no_relevant_source:
            return NLQueryResult(
                no_relevant_source=True,
                no_source_message=generation.no_source_message,
                explanation=generation.explanation,
            )

        # 6. Validate generated SQL
        if not generation.sql:
            return NLQueryResult(
                error="AI did not generate a SQL query.",
                explanation=generation.explanation,
            )

        if not is_read_only_sql(generation.sql):
            return NLQueryResult(
                error=(
                    "The generated query would modify data. "
                    "Only read-only queries are allowed."
                ),
                explanation="Write operations (INSERT, UPDATE, DELETE, etc.) are not permitted.",
            )

        # 7. Resolve source
        source_id_str = generation.source_id
        source_type = generation.source_type

        if not source_id_str or not source_type:
            return NLQueryResult(
                error="Could not determine which data source to query.",
                explanation=generation.explanation,
            )

        # 8. Execute with self-correction loop
        return await self._execute_with_retries(
            sql=generation.sql,
            source_id_str=source_id_str,
            source_type=source_type,
            question=question,
            schema_context=schema_result.context_text,
            source_list=source_list,
            source_mapping=source_mapping,
            explanation=generation.explanation,
            provider_id=provider_id,
            conversation_id=conversation_id,
            on_retry_progress=on_retry_progress,
        )

    async def _generate_sql(
        self,
        question: str,
        schema_context: str,
        source_list: str,
        source_mapping: dict[str, dict[str, str]],
        provider_id: str | None = None,
        conversation_id: str | None = None,
    ) -> SQLGenerationResult:
        """Generate SQL from a natural language question using the AI agent.

        Returns a structured result with the generated SQL, source info,
        and explanation, or a clarification request.
        """
        try:
            agent = create_agent(provider_id=provider_id)
        except NoProviderConfiguredError:
            return SQLGenerationResult(
                no_relevant_source=True,
                no_source_message=(
                    "No AI provider is configured. "
                    "Please configure an AI provider in Settings."
                ),
            )

        prompt = _build_generation_prompt(question, schema_context, source_list)

        deps = AgentDeps(
            schema_context=schema_context,
            conversation_id=conversation_id,
            available_tables=list(source_mapping.keys()),
        )

        try:
            result = await agent.run(prompt, deps=deps)
            output = result.output
        except Exception as exc:
            logger.error("ai_generation_failed", error=str(exc))
            return SQLGenerationResult(
                explanation=f"AI generation failed: {exc}",
            )

        return _parse_ai_output(output, source_mapping)

    async def _generate_correction(
        self,
        original_sql: str,
        error_message: str,
        question: str,
        schema_context: str,
        source_list: str,
        source_mapping: dict[str, dict[str, str]],
        correction_history: list[dict[str, str]] | None = None,
        provider_id: str | None = None,
        conversation_id: str | None = None,
    ) -> SQLGenerationResult:
        """Ask the AI to correct a failed SQL query based on the error.

        The AI receives the original question, the failed SQL, the error
        message, and the full history of previous correction attempts so
        that it avoids repeating the same failing approaches.
        """
        try:
            agent = create_agent(provider_id=provider_id)
        except NoProviderConfiguredError:
            return SQLGenerationResult(
                explanation="No AI provider configured for self-correction.",
            )

        error_category = classify_error(error_message)

        prompt = _build_correction_prompt(
            question=question,
            failed_sql=original_sql,
            error_message=error_message,
            error_category=error_category,
            schema_context=schema_context,
            source_list=source_list,
            correction_history=correction_history,
        )

        deps = AgentDeps(
            schema_context=schema_context,
            conversation_id=conversation_id,
            available_tables=list(source_mapping.keys()),
        )

        try:
            result = await agent.run(prompt, deps=deps)
            output = result.output
        except Exception as exc:
            logger.error("ai_correction_failed", error=str(exc))
            return SQLGenerationResult(
                explanation=f"AI correction failed: {exc}",
            )

        return _parse_ai_output(output, source_mapping)

    async def _execute_with_retries(
        self,
        sql: str,
        source_id_str: str,
        source_type: str,
        question: str,
        schema_context: str,
        source_list: str,
        source_mapping: dict[str, dict[str, str]],
        explanation: str,
        provider_id: str | None = None,
        conversation_id: str | None = None,
        on_retry_progress: RetryProgressCallback | None = None,
    ) -> NLQueryResult:
        """Execute SQL with agentic self-correction loop on errors.

        On SQL errors the AI agent receives the error context (including
        full correction history so it avoids repeating the same failing
        approaches) and generates corrected SQL. The loop runs up to
        ``max_retries`` correction attempts after the initial execution.

        Non-retryable errors (timeout, read-only violations, connection
        lost, permission denied) skip the retry loop immediately.

        Args:
            sql: Initial SQL generated by the agent.
            source_id_str: UUID string of the target data source.
            source_type: ``"dataset"`` or ``"connection"``.
            question: Original natural language question.
            schema_context: Schema metadata text for the AI prompt.
            source_list: Formatted list of available sources.
            source_mapping: Table-to-source mapping dict.
            explanation: Initial AI explanation for the query.
            provider_id: Optional AI provider ID.
            conversation_id: Optional conversation context ID.
            on_retry_progress: Optional async callback invoked before each
                retry attempt. Receives ``(attempt, max_retries, error_msg,
                error_category)`` — useful for streaming SSE progress events.

        Returns:
            NLQueryResult with query results or structured error details.
        """
        current_sql = _ensure_limit(sql)
        correction_history: list[dict[str, str]] = []
        attempts = 0

        for attempt in range(self._max_retries + 1):
            attempts = attempt + 1

            try:
                source_uuid = uuid.UUID(source_id_str)
            except ValueError:
                return NLQueryResult(
                    error=f"Invalid source ID: {source_id_str}",
                    sql=current_sql,
                    source_id=source_id_str,
                    source_type=source_type,
                    explanation=explanation,
                    attempts=attempts,
                    correction_history=correction_history,
                )

            query_result = self._query_service.execute(
                sql=current_sql,
                source_id=source_uuid,
                source_type=source_type,
            )

            # Success
            if query_result.status == "success":
                if attempts > 1:
                    logger.info(
                        "nl_query_self_corrected",
                        attempts=attempts,
                        row_count=query_result.row_count,
                        execution_time_ms=query_result.execution_time_ms,
                    )
                else:
                    logger.info(
                        "nl_query_success",
                        attempts=attempts,
                        row_count=query_result.row_count,
                        execution_time_ms=query_result.execution_time_ms,
                    )
                return NLQueryResult(
                    columns=query_result.columns,
                    rows=query_result.rows,
                    row_count=query_result.row_count,
                    execution_time_ms=query_result.execution_time_ms,
                    sql=current_sql,
                    source_id=source_id_str,
                    source_type=source_type,
                    explanation=explanation,
                    attempts=attempts,
                    correction_history=correction_history,
                )

            # Classify the error
            error_msg = query_result.error_message or "Unknown error"
            error_category = classify_error(error_msg)

            # Non-retryable errors — return immediately
            if not is_retryable_error(error_msg, query_result.status):
                # Add to history for visibility even though we won't retry
                correction_history.append({
                    "sql": current_sql,
                    "error": error_msg,
                    "category": error_category,
                })

                if query_result.status == "timeout":
                    user_error = (
                        "The query exceeded the time limit and was cancelled. "
                        "Try narrowing your question or adding filters."
                    )
                elif error_category == ErrorCategory.CONNECTION_LOST:
                    user_error = (
                        "Connection to the data source was lost. "
                        "Please check the connection and try again."
                    )
                elif error_category == ErrorCategory.PERMISSION_DENIED:
                    user_error = (
                        "Permission denied when executing the query. "
                        "Check that the database user has read access."
                    )
                elif "READ_ONLY" in error_msg.upper():
                    user_error = "Write operations are not allowed."
                else:
                    user_error = error_msg

                logger.warning(
                    "nl_query_non_retryable",
                    sql=current_sql,
                    error_category=error_category,
                    error=error_msg,
                    attempts=attempts,
                )
                return NLQueryResult(
                    error=user_error,
                    sql=current_sql,
                    source_id=source_id_str,
                    source_type=source_type,
                    explanation=explanation,
                    attempts=attempts,
                    correction_history=correction_history,
                )

            # Retryable SQL error — record and attempt self-correction
            correction_history.append({
                "sql": current_sql,
                "error": error_msg,
                "category": error_category,
            })

            if attempt < self._max_retries:
                logger.info(
                    "nl_query_retry",
                    attempt=attempt + 1,
                    max_retries=self._max_retries,
                    error=error_msg,
                    error_category=error_category,
                )

                # Notify caller of retry progress (for SSE streaming)
                if on_retry_progress is not None:
                    await on_retry_progress(
                        attempt + 1,
                        self._max_retries,
                        error_msg,
                        error_category,
                    )

                correction = await self._generate_correction(
                    original_sql=current_sql,
                    error_message=error_msg,
                    question=question,
                    schema_context=schema_context,
                    source_list=source_list,
                    source_mapping=source_mapping,
                    correction_history=correction_history,
                    provider_id=provider_id,
                    conversation_id=conversation_id,
                )

                if correction.sql and is_read_only_sql(correction.sql):
                    current_sql = _ensure_limit(correction.sql)
                    if correction.explanation:
                        explanation = correction.explanation
                    # Update source if the AI changed it
                    if correction.source_id:
                        source_id_str = correction.source_id
                    if correction.source_type:
                        source_type = correction.source_type
                else:
                    # AI couldn't produce a valid correction
                    logger.warning(
                        "nl_query_correction_invalid",
                        attempt=attempt + 1,
                    )

        # All retries exhausted — build structured error with all attempts
        logger.warning(
            "nl_query_max_retries",
            attempts=attempts,
            last_error=correction_history[-1]["error"] if correction_history else None,
        )

        attempts_summary = _format_attempts_summary(correction_history)
        return NLQueryResult(
            error=(
                f"Unable to generate a working query after {attempts} attempts. "
                f"Here's what was tried:\n{attempts_summary}"
            ),
            sql=current_sql,
            source_id=source_id_str,
            source_type=source_type,
            explanation=explanation,
            attempts=attempts,
            correction_history=correction_history,
        )


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def _build_source_list(source_mapping: dict[str, dict[str, str]]) -> str:
    """Build a formatted list of available sources for the AI prompt."""
    lines = ["Available data sources and their identifiers:"]
    seen: set[str] = set()
    for table_name, info in source_mapping.items():
        key = f"{info['source_id']}:{table_name}"
        if key in seen:
            continue
        seen.add(key)
        lines.append(
            f"  - Table: {table_name} "
            f"(source_id: {info['source_id']}, "
            f"source_type: {info['source_type']})"
        )
    return "\n".join(lines)


def _build_generation_prompt(
    question: str,
    schema_context: str,
    source_list: str,
) -> str:
    """Build the prompt for SQL generation from a natural language question."""
    return f"""Given the user's question and the available data sources, generate a SQL query.

{schema_context}

{source_list}

INSTRUCTIONS:
1. Analyze the question and determine which data source is relevant.
2. Generate valid SQL for the target source. Use DuckDB dialect \
for datasets, PostgreSQL/MySQL for connections.
3. Always use read-only SELECT statements. Never generate \
INSERT, UPDATE, DELETE, DROP, or other write operations.
4. Include a LIMIT clause for broad queries (default LIMIT 1000).
5. Use aggregations (GROUP BY, COUNT, SUM, AVG, etc.) for \
totals, averages, distributions, etc.
6. Use WHERE clauses for filtering when conditions are specified.
7. Use ORDER BY for top/bottom/highest/lowest/most/least.
8. If the question is ambiguous, respond with a clarification.
9. If no data source is relevant to the question, say so.

RESPONSE FORMAT (you MUST follow this exactly):
If generating a query:
```
SQL: <the SQL query>
SOURCE_ID: <uuid of the source>
SOURCE_TYPE: <dataset or connection>
EXPLANATION: <natural language explanation of what the query does and why>
```

If clarification is needed:
```
CLARIFICATION: <your question to the user>
EXPLANATION: <why you need more information>
```

If no relevant source exists:
```
NO_SOURCE: <explanation of why no source matches>
EXPLANATION: <suggestion for what data the user might need>
```

USER QUESTION: {question}"""


def _format_attempts_summary(correction_history: list[dict[str, str]]) -> str:
    """Format correction history into a human-readable summary.

    Each entry shows the attempt number, the SQL tried, the error
    encountered, and the error category.
    """
    if not correction_history:
        return ""

    lines: list[str] = []
    for i, entry in enumerate(correction_history, 1):
        category = entry.get("category", "unknown")
        sql_preview = entry["sql"][:200]
        if len(entry["sql"]) > 200:
            sql_preview += "..."
        lines.append(
            f"Attempt {i} ({category}): {entry['error']}\n"
            f"  SQL: {sql_preview}"
        )
    return "\n".join(lines)


def _build_correction_prompt(
    question: str,
    failed_sql: str,
    error_message: str,
    schema_context: str,
    source_list: str,
    error_category: str = ErrorCategory.UNKNOWN,
    correction_history: list[dict[str, str]] | None = None,
) -> str:
    """Build the prompt for SQL self-correction after an error.

    When ``correction_history`` is provided (previous failed attempts),
    the AI receives the full history so it avoids repeating the same
    approaches that already failed.
    """
    # Build category-specific guidance
    category_hints = _get_category_hints(error_category)

    # Build previous attempts section if there are earlier failures
    previous_attempts_section = ""
    if correction_history and len(correction_history) > 1:
        # Show all previous attempts (excluding the current one which is last)
        prev = correction_history[:-1]
        attempt_lines: list[str] = []
        for i, entry in enumerate(prev, 1):
            attempt_lines.append(
                f"Attempt {i}:\n"
                f"  SQL: {entry['sql']}\n"
                f"  Error: {entry['error']}"
            )
        previous_attempts_section = (
            "\n\nPREVIOUS FAILED ATTEMPTS (do NOT repeat these approaches):\n"
            + "\n".join(attempt_lines)
        )

    return f"""The SQL query below failed. Analyze the error and \
generate a corrected query.

{schema_context}

{source_list}

ORIGINAL QUESTION: {question}

FAILED SQL:
```sql
{failed_sql}
```

ERROR MESSAGE: {error_message}
ERROR CATEGORY: {error_category}
{previous_attempts_section}

INSTRUCTIONS:
1. Analyze the error message to understand what went wrong.
{category_hints}\
2. Check the schema context for correct table and column names.
3. Generate a corrected SQL query that addresses the error.
4. Do NOT repeat any SQL from the previous failed attempts — \
try a fundamentally different approach if the same error keeps occurring.
5. Keep using read-only SELECT statements only.
6. Include a LIMIT clause for broad queries.

RESPONSE FORMAT (same as before):
```
SQL: <the corrected SQL query>
SOURCE_ID: <uuid of the source>
SOURCE_TYPE: <dataset or connection>
EXPLANATION: <explanation of the correction and what the query does>
```"""


def _get_category_hints(error_category: str) -> str:
    """Return category-specific correction guidance for the AI prompt."""
    hints: dict[str, str] = {
        ErrorCategory.SYNTAX: (
            "   - This is a SYNTAX ERROR. Check for missing keywords, "
            "unbalanced parentheses, incorrect function names, or "
            "dialect-specific syntax issues.\n"
        ),
        ErrorCategory.COLUMN_NOT_FOUND: (
            "   - A COLUMN was not found. Carefully check the schema context "
            "for the exact column names (case-sensitive). The column may "
            "be named differently or belong to a different table.\n"
        ),
        ErrorCategory.TABLE_NOT_FOUND: (
            "   - A TABLE was not found. Check the available data sources "
            "and use the exact table names from the schema. The table may "
            "be named differently or need a schema prefix.\n"
        ),
        ErrorCategory.TYPE_MISMATCH: (
            "   - There is a TYPE MISMATCH. Check that comparison values "
            "match the column types (e.g., don't compare a string column "
            "with a number). Use CAST() if needed.\n"
        ),
        ErrorCategory.AMBIGUOUS_REFERENCE: (
            "   - There is an AMBIGUOUS REFERENCE. A column name appears in "
            "multiple tables. Use table_name.column_name to disambiguate.\n"
        ),
    }
    return hints.get(error_category, "")


# ---------------------------------------------------------------------------
# AI output parsing
# ---------------------------------------------------------------------------


def _parse_ai_output(
    output: str,
    source_mapping: dict[str, dict[str, str]],
) -> SQLGenerationResult:
    """Parse the AI agent's text output into a structured SQLGenerationResult.

    Extracts SQL, SOURCE_ID, SOURCE_TYPE, EXPLANATION, CLARIFICATION, and
    NO_SOURCE fields from the formatted response.
    """
    if not output or not output.strip():
        return SQLGenerationResult(
            explanation="AI returned empty response.",
        )

    text = output.strip()

    # Check for clarification
    clarification_match = re.search(
        r"CLARIFICATION:\s*(.+?)(?=\n(?:EXPLANATION:|SQL:|SOURCE_ID:|$))",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if clarification_match:
        clarification = clarification_match.group(1).strip()
        explanation = _extract_field(text, "EXPLANATION")
        return SQLGenerationResult(
            needs_clarification=True,
            clarifying_question=clarification,
            explanation=explanation,
        )

    # Check for no source
    no_source_match = re.search(
        r"NO_SOURCE:\s*(.+?)(?=\n(?:EXPLANATION:|SQL:|SOURCE_ID:|$))",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if no_source_match:
        no_source_msg = no_source_match.group(1).strip()
        explanation = _extract_field(text, "EXPLANATION")
        return SQLGenerationResult(
            no_relevant_source=True,
            no_source_message=no_source_msg,
            explanation=explanation,
        )

    # Extract SQL query
    sql = _extract_sql(text)
    source_id = _extract_field(text, "SOURCE_ID")
    source_type = _extract_field(text, "SOURCE_TYPE")
    explanation = _extract_field(text, "EXPLANATION")
    if explanation:
        explanation = _strip_code_fences(explanation)

    # Validate source_type
    if source_type and source_type not in ("dataset", "connection"):
        source_type = None

    # Try to resolve source from mapping if not provided
    if sql and (not source_id or not source_type):
        resolved = _resolve_source_from_sql(sql, source_mapping)
        if resolved:
            source_id = source_id or resolved["source_id"]
            source_type = source_type or resolved["source_type"]

    return SQLGenerationResult(
        sql=sql,
        source_id=source_id,
        source_type=source_type,
        explanation=explanation,
    )


def _strip_code_fences(text: str) -> str:
    """Remove markdown fenced code blocks from explanation text."""
    return re.sub(r"```[\w]*\n.*?\n```", "", text, flags=re.DOTALL).strip()


def _extract_field(text: str, field_name: str) -> str:
    """Extract a field value from the AI output text."""
    # First try: look for field followed by another known field
    known_fields = (
        r"SQL:|SOURCE_ID:|SOURCE_TYPE:|"
        r"EXPLANATION:|CLARIFICATION:|NO_SOURCE:"
    )
    pattern = rf"(?:^|\n){field_name}:\s*(.+?)(?=\n(?:{known_fields})|\Z)"
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return ""


def _extract_sql(text: str) -> str | None:
    """Extract SQL from the AI output, handling code blocks and inline SQL."""
    # Try SQL: prefix first
    sql_match = re.search(
        r"SQL:\s*(.+?)(?=\n(?:SOURCE_ID:|SOURCE_TYPE:|EXPLANATION:|$))",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if sql_match:
        sql = sql_match.group(1).strip()
        # Remove markdown code fences if present
        sql = re.sub(r"^```(?:sql)?\s*", "", sql)
        sql = re.sub(r"\s*```\s*$", "", sql)
        if sql:
            return sql

    # Try extracting from code block
    code_match = re.search(r"```(?:sql)?\s*\n(.+?)\n\s*```", text, re.DOTALL)
    if code_match:
        sql = code_match.group(1).strip()
        if sql and re.match(r"(?:SELECT|WITH)\b", sql, re.IGNORECASE):
            return sql

    return None


def _resolve_source_from_sql(
    sql: str,
    source_mapping: dict[str, dict[str, str]],
) -> dict[str, str] | None:
    """Try to infer the source from table names in the SQL."""
    # Extract table names from FROM and JOIN clauses
    table_pattern = re.compile(
        r"\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)\b",
        re.IGNORECASE,
    )
    tables_in_sql = table_pattern.findall(sql)

    for table_name in tables_in_sql:
        source = _find_source_for_table(table_name, source_mapping)
        if source:
            return source

    return None
