"""SSE streaming endpoint for conversation messages.

Provides POST /conversations/{id}/messages that accepts a user message,
processes it through the AI agent pipeline, and streams the response via
Server-Sent Events (SSE).

SSE event types:
- message_start: Sent when the assistant message is created
- token: Streamed text tokens from the AI response
- sql_generated: Generated SQL query
- query_result: Query execution results (columns, rows, row_count)
- chart_config: Plotly chart configuration
- message_end: Signals the end of the response
- error: Error information
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.errors import AppError
from app.logging import get_logger
from app.models.orm import Conversation, Message
from app.services.agent_service import NoProviderConfiguredError
from app.services.chart_config import PlotlyConfig, generate_chart_config
from app.services.chart_heuristics import ChartType, recommend_chart_type
from app.services.nl_query_service import NLQueryService
from app.services.query_service import QueryService
from app.shutdown import ShutdownManager

logger = get_logger(__name__)

router = APIRouter()


class SendMessageRequest(BaseModel):
    """Request body for sending a message."""

    content: str = Field(..., min_length=1, description="The user message content")


def _sse_event(event: str, data: dict[str, Any]) -> dict[str, str]:
    """Format an SSE event as a dict for sse-starlette."""
    return {"event": event, "data": json.dumps(data)}


def _to_frontend_chart_config(plotly_config: PlotlyConfig) -> dict[str, Any]:
    """Transform a PlotlyConfig into the frontend's ChartConfig shape.

    Handles three key differences between backend output and frontend expectations:
    - Renames ``chart_type`` to ``type``
    - Maps ``histogram`` to ``bar`` (frontend validTypes doesn't include histogram)
    - Extracts KPI fields (``kpiValue``, ``kpiLabel``) from indicator traces
    """
    chart_type = plotly_config.chart_type

    # Frontend validTypes: line, bar, pie, scatter, kpi
    if chart_type == "histogram":
        chart_type = "bar"

    result: dict[str, Any] = {"type": chart_type}

    if chart_type == "kpi":
        # Extract value/label from first indicator trace for the frontend's
        # custom KPI card (it doesn't use Plotly for KPI rendering)
        for trace in plotly_config.data:
            if trace.get("type") == "indicator":
                result["kpiValue"] = trace.get("value")
                title = trace.get("title")
                if isinstance(title, dict):
                    result["kpiLabel"] = title.get("text", "")
                elif isinstance(title, str):
                    result["kpiLabel"] = title
                break
    else:
        result["data"] = plotly_config.data
        layout = plotly_config.layout.copy()
        # Plotly uses {"text": "...", "font": {...}} for title, but the
        # frontend reads layout.title as a plain string for export filenames
        if isinstance(layout.get("title"), dict):
            layout["title"] = layout["title"].get("text", "")
        result["layout"] = layout

    return result


def _get_shutdown_manager(request: Request) -> ShutdownManager:
    """Retrieve the shutdown manager from app state."""
    return request.app.state.shutdown_manager


async def _stream_response(
    conversation_id: uuid.UUID,
    user_content: str,
    session_factory: Any,
    request: Request,
) -> AsyncGenerator[dict[str, str], None]:
    """Generate SSE events for an AI-assisted conversation response.

    This generator:
    1. Saves the user message to the database
    2. Invokes the AI agent to generate a response
    3. Streams tokens and structured data as SSE events
    4. Saves the complete assistant message with metadata
    """
    shutdown_mgr: ShutdownManager = request.app.state.shutdown_manager
    token = await shutdown_mgr.track("sse")
    db: Session | None = None

    try:
        db = session_factory()

        # Verify conversation exists
        conversation = db.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        ).scalar_one_or_none()

        if conversation is None:
            yield _sse_event("error", {
                "code": "NOT_FOUND",
                "message": f"Conversation {conversation_id} not found",
            })
            return

        # Save the user message
        user_message = Message(
            conversation_id=conversation_id,
            role="user",
            content=user_content,
        )
        db.add(user_message)
        db.commit()

        logger.info(
            "user_message_saved",
            conversation_id=str(conversation_id),
            message_id=str(user_message.id),
        )

        # Create the assistant message placeholder
        assistant_message_id = uuid.uuid4()

        # Emit message_start
        yield _sse_event("message_start", {
            "message_id": str(assistant_message_id),
            "role": "assistant",
        })

        # Process through NL query service
        duckdb_manager = request.app.state.duckdb_manager
        connection_manager = request.app.state.connection_manager
        settings = request.app.state.settings

        query_service = QueryService(
            duckdb_manager=duckdb_manager,
            connection_manager=connection_manager,
            max_query_timeout=settings.datax_max_query_timeout,
        )
        nl_service = NLQueryService(
            query_service=query_service,
            max_retries=settings.datax_max_retries,
        )

        # Check for client disconnect before expensive AI call
        if await request.is_disconnected():
            logger.info("client_disconnected_before_ai", conversation_id=str(conversation_id))
            return

        # Process the question through the NL pipeline
        try:
            result = await nl_service.process_question(
                question=user_content,
                session=db,
                conversation_id=str(conversation_id),
            )
        except NoProviderConfiguredError as exc:
            yield _sse_event("error", {
                "code": "NO_PROVIDER",
                "message": str(exc),
            })
            yield _sse_event("message_end", {
                "message_id": str(assistant_message_id),
            })
            return
        except Exception as exc:
            logger.error(
                "ai_processing_error",
                conversation_id=str(conversation_id),
                error=str(exc),
            )
            yield _sse_event("error", {
                "code": "AI_ERROR",
                "message": f"An error occurred while processing your question: {exc}",
            })
            yield _sse_event("message_end", {
                "message_id": str(assistant_message_id),
            })
            return

        # Build the response content and metadata
        metadata: dict[str, Any] = {}
        response_parts: list[str] = []

        # Handle clarification requests
        if result.needs_clarification:
            clarification = result.clarifying_question or "Could you provide more details?"
            # Stream clarification as tokens
            for chunk in _chunk_text(clarification):
                yield _sse_event("token", {"content": chunk})
                await asyncio.sleep(0)
            response_parts.append(clarification)

        # Handle no relevant source
        elif result.no_relevant_source:
            no_source_msg = result.no_source_message or "No relevant data source found."
            for chunk in _chunk_text(no_source_msg):
                yield _sse_event("token", {"content": chunk})
                await asyncio.sleep(0)
            response_parts.append(no_source_msg)

        # Handle errors from the pipeline
        elif result.error:
            yield _sse_event("error", {
                "code": "QUERY_ERROR",
                "message": result.error,
            })
            error_explanation = result.explanation or result.error
            for chunk in _chunk_text(error_explanation):
                yield _sse_event("token", {"content": chunk})
                await asyncio.sleep(0)
            response_parts.append(error_explanation)

            # If we have SQL and correction history, include in metadata
            if result.sql:
                metadata["sql"] = result.sql
            if result.correction_history:
                metadata["correction_history"] = result.correction_history

        else:
            # Successful query flow
            # Stream explanation tokens first
            if result.explanation:
                for chunk in _chunk_text(result.explanation):
                    yield _sse_event("token", {"content": chunk})
                    await asyncio.sleep(0)
                response_parts.append(result.explanation)

            # Emit sql_generated event
            if result.sql:
                yield _sse_event("sql_generated", {"sql": result.sql})
                metadata["sql"] = result.sql

            # Emit query_result event
            if result.columns or result.rows:
                yield _sse_event("query_result", {
                    "columns": result.columns,
                    "rows": result.rows,
                    "row_count": result.row_count,
                })

            # Generate chart configuration
            if result.columns and result.rows:
                try:
                    recommendation = recommend_chart_type(result.columns, result.rows)
                    if recommendation.chart_type != ChartType.TABLE:
                        plotly_config = generate_chart_config(
                            columns=result.columns,
                            rows=result.rows,
                            recommendation=recommendation,
                            query_context=user_content,
                        )
                        if not plotly_config.is_fallback:
                            chart_event = _to_frontend_chart_config(plotly_config)
                            yield _sse_event("chart_config", chart_event)
                            metadata["chart_config"] = chart_event
                except Exception as exc:
                    logger.warning(
                        "chart_generation_failed",
                        conversation_id=str(conversation_id),
                        error=str(exc),
                    )

            # Store query metadata
            if result.source_id:
                metadata["source_id"] = result.source_id
            if result.source_type:
                metadata["source_type"] = result.source_type
            if result.execution_time_ms:
                metadata["execution_time_ms"] = result.execution_time_ms
            if result.attempts > 1:
                metadata["attempts"] = result.attempts
            if result.correction_history:
                metadata["correction_history"] = result.correction_history

        # Save the assistant message
        full_content = "\n".join(response_parts) if response_parts else ""
        assistant_message = Message(
            id=assistant_message_id,
            conversation_id=conversation_id,
            role="assistant",
            content=full_content,
            metadata_=metadata if metadata else None,
        )
        db.add(assistant_message)
        db.commit()

        logger.info(
            "assistant_message_saved",
            conversation_id=str(conversation_id),
            message_id=str(assistant_message_id),
            has_sql=bool(metadata.get("sql")),
        )

        # Emit message_end
        yield _sse_event("message_end", {
            "message_id": str(assistant_message_id),
        })

    except Exception as exc:
        logger.error(
            "sse_stream_error",
            conversation_id=str(conversation_id),
            error=str(exc),
        )
        yield _sse_event("error", {
            "code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred.",
        })
    finally:
        if db is not None:
            db.close()
        await shutdown_mgr.untrack(token)


def _chunk_text(text: str, chunk_size: int = 4) -> list[str]:
    """Split text into word-based chunks for token streaming.

    Groups words into chunks to simulate token-by-token streaming
    while keeping network overhead reasonable.
    """
    if not text:
        return []
    words = text.split(" ")
    chunks: list[str] = []
    for i in range(0, len(words), chunk_size):
        chunk_words = words[i : i + chunk_size]
        chunk = " ".join(chunk_words)
        # Add a trailing space unless it's the last chunk
        if i + chunk_size < len(words):
            chunk += " "
        chunks.append(chunk)
    return chunks


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: uuid.UUID,
    body: SendMessageRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> Any:
    """Send a user message and receive AI response via SSE stream.

    The endpoint validates the conversation exists and the message content,
    then returns an SSE stream with the AI response.

    SSE events emitted:
    - message_start: {message_id, role}
    - token: {content} (streamed text chunks)
    - sql_generated: {sql}
    - query_result: {columns, rows, row_count}
    - chart_config: {type, config}
    - message_end: {message_id}
    - error: {code, message}
    """
    # Validate conversation exists before starting SSE stream
    conversation = db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    ).scalar_one_or_none()

    if conversation is None:
        raise AppError(
            code="NOT_FOUND",
            message=f"Conversation {conversation_id} not found",
            status_code=404,
        )

    # Import here to avoid circular imports with sse-starlette
    from sse_starlette.sse import EventSourceResponse

    session_factory = request.app.state.session_factory

    return EventSourceResponse(
        _stream_response(
            conversation_id=conversation_id,
            user_content=body.content,
            session_factory=session_factory,
            request=request,
        ),
        media_type="text/event-stream",
    )
