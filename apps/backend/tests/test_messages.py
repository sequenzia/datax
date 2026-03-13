"""Tests for the SSE streaming message endpoint.

Covers:
- Functional: User message saved, AI streams tokens, sql_generated event,
  query_result event, assistant message saved with metadata,
  conversation history maintained
- Edge Cases: Conversation not found 404, empty message 400,
  client disconnect cleanup
- Error Handling: AI error -> error SSE event, query error -> error event
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.main import create_app
from app.models.base import Base
from app.models.orm import Message
from app.services.nl_query_service import NLQueryResult


@pytest.fixture(autouse=True)
def reset_sse_app_status():
    """Reset sse-starlette AppStatus to avoid event loop binding issues in tests."""
    from sse_starlette.sse import AppStatus

    AppStatus.should_exit_event = None
    yield
    AppStatus.should_exit_event = None


@pytest.fixture
def db_path():
    """Create a temporary file for SQLite database."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d) / "test.db"


def _test_settings(db_path: Path) -> Settings:
    """Create test settings with required fields."""
    env = {
        "DATABASE_URL": f"sqlite:///{db_path}",
        "DATAX_ENCRYPTION_KEY": "test-encryption-key",
    }
    with patch.dict(os.environ, env, clear=True):
        return Settings()  # type: ignore[call-arg]


@pytest.fixture
def db_engine(db_path):
    """Create a SQLite engine backed by a temp file with foreign key support."""
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(db_engine):
    """Create a sessionmaker bound to the test engine."""
    return sessionmaker(bind=db_engine, autocommit=False, autoflush=False)


@pytest.fixture
def app(db_path, db_engine, session_factory):
    """Create a FastAPI app with a test SQLite database."""
    application = create_app(settings=_test_settings(db_path))
    application.state.db_engine = db_engine
    application.state.session_factory = session_factory
    return application


@pytest.fixture
async def client(app):
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest.fixture
def db(session_factory) -> Session:
    """Create a database session for test setup/teardown."""
    session = session_factory()
    yield session
    session.close()


def _parse_sse_events(text: str) -> list[dict]:
    """Parse SSE event stream text into a list of {event, data} dicts."""
    events = []
    current_event = None
    current_data_lines = []

    for line in text.split("\n"):
        if line.startswith("event:"):
            if current_event is not None and current_data_lines:
                data_str = "\n".join(current_data_lines)
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    data = data_str
                events.append({"event": current_event, "data": data})
            current_event = line[len("event:"):].strip()
            current_data_lines = []
        elif line.startswith("data:"):
            current_data_lines.append(line[len("data:"):].strip())
        elif line.strip() == "" and current_event is not None and current_data_lines:
            data_str = "\n".join(current_data_lines)
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                data = data_str
            events.append({"event": current_event, "data": data})
            current_event = None
            current_data_lines = []

    # Handle last event if no trailing newline
    if current_event is not None and current_data_lines:
        data_str = "\n".join(current_data_lines)
        try:
            data = json.loads(data_str)
        except json.JSONDecodeError:
            data = data_str
        events.append({"event": current_event, "data": data})

    return events


def _mock_nl_service_result(
    explanation: str = "Test explanation",
    sql: str | None = None,
    columns: list[str] | None = None,
    rows: list[list] | None = None,
    error: str | None = None,
    needs_clarification: bool = False,
    clarifying_question: str | None = None,
    no_relevant_source: bool = False,
    no_source_message: str | None = None,
) -> NLQueryResult:
    """Create a mock NLQueryResult for testing."""
    return NLQueryResult(
        columns=columns or [],
        rows=rows or [],
        row_count=len(rows) if rows else 0,
        execution_time_ms=42,
        sql=sql,
        source_id=str(uuid.uuid4()) if sql else None,
        source_type="dataset" if sql else None,
        explanation=explanation,
        needs_clarification=needs_clarification,
        clarifying_question=clarifying_question,
        no_relevant_source=no_relevant_source,
        no_source_message=no_source_message,
        error=error,
        attempts=1,
        correction_history=[],
    )


# ---------------------------------------------------------------------------
# Edge Cases: Conversation not found / Empty message
# ---------------------------------------------------------------------------


class TestMessageValidation:
    """Test request validation for the message endpoint."""

    @pytest.mark.asyncio
    async def test_conversation_not_found_returns_404(self, client) -> None:
        """Sending a message to a non-existent conversation returns 404."""
        fake_id = uuid.uuid4()
        response = await client.post(
            f"/api/v1/conversations/{fake_id}/messages",
            json={"content": "Hello"},
        )
        assert response.status_code == 404
        body = response.json()
        assert body["error"]["code"] == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_empty_message_returns_422(self, client) -> None:
        """Sending an empty message returns 422 validation error."""
        # First create a conversation
        resp = await client.post("/api/v1/conversations")
        conv_id = resp.json()["id"]

        response = await client.post(
            f"/api/v1/conversations/{conv_id}/messages",
            json={"content": ""},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_content_returns_422(self, client) -> None:
        """Sending a request without content field returns 422."""
        resp = await client.post("/api/v1/conversations")
        conv_id = resp.json()["id"]

        response = await client.post(
            f"/api/v1/conversations/{conv_id}/messages",
            json={},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_uuid_returns_422(self, client) -> None:
        """Invalid conversation UUID format returns 422."""
        response = await client.post(
            "/api/v1/conversations/not-a-uuid/messages",
            json={"content": "Hello"},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Functional: User message saved
# ---------------------------------------------------------------------------


class TestUserMessageSaved:
    """Test that user messages are persisted to the database."""

    @pytest.mark.asyncio
    async def test_user_message_saved_to_db(self, client, db) -> None:
        """The user message is saved to the database before streaming."""
        # Create conversation
        resp = await client.post("/api/v1/conversations")
        conv_id = uuid.UUID(resp.json()["id"])

        # Mock the NL service to return a simple response
        mock_result = _mock_nl_service_result(explanation="Test response")

        with patch(
            "app.api.v1.messages.NLQueryService"
        ) as mock_nl_cls:
            mock_instance = mock_nl_cls.return_value
            mock_instance.process_question = AsyncMock(return_value=mock_result)

            response = await client.post(
                f"/api/v1/conversations/{conv_id}/messages",
                json={"content": "What data do I have?"},
            )
            assert response.status_code == 200

        # Verify user message was saved
        db.expire_all()
        messages = db.execute(
            select(Message)
            .where(Message.conversation_id == conv_id)
            .order_by(Message.created_at)
        ).scalars().all()

        user_messages = [m for m in messages if m.role == "user"]
        assert len(user_messages) >= 1
        assert user_messages[0].content == "What data do I have?"


# ---------------------------------------------------------------------------
# Functional: SSE stream contains expected events
# ---------------------------------------------------------------------------


class TestSSEStreamEvents:
    """Test SSE event structure and content."""

    @pytest.mark.asyncio
    async def test_stream_contains_message_start_and_end(self, client) -> None:
        """SSE stream includes message_start and message_end events."""
        resp = await client.post("/api/v1/conversations")
        conv_id = resp.json()["id"]

        mock_result = _mock_nl_service_result(explanation="Test response")

        with patch(
            "app.api.v1.messages.NLQueryService"
        ) as mock_nl_cls:
            mock_instance = mock_nl_cls.return_value
            mock_instance.process_question = AsyncMock(return_value=mock_result)

            response = await client.post(
                f"/api/v1/conversations/{conv_id}/messages",
                json={"content": "Hello"},
            )

        events = _parse_sse_events(response.text)
        event_types = [e["event"] for e in events]

        assert "message_start" in event_types
        assert "message_end" in event_types

        # message_start should have message_id and role
        start_event = next(e for e in events if e["event"] == "message_start")
        assert "message_id" in start_event["data"]
        assert start_event["data"]["role"] == "assistant"

        # message_end should have message_id
        end_event = next(e for e in events if e["event"] == "message_end")
        assert "message_id" in end_event["data"]

    @pytest.mark.asyncio
    async def test_stream_contains_token_events(self, client) -> None:
        """SSE stream includes token events with content."""
        resp = await client.post("/api/v1/conversations")
        conv_id = resp.json()["id"]

        mock_result = _mock_nl_service_result(explanation="Here are your results")

        with patch(
            "app.api.v1.messages.NLQueryService"
        ) as mock_nl_cls:
            mock_instance = mock_nl_cls.return_value
            mock_instance.process_question = AsyncMock(return_value=mock_result)

            response = await client.post(
                f"/api/v1/conversations/{conv_id}/messages",
                json={"content": "Show me data"},
            )

        events = _parse_sse_events(response.text)
        token_events = [e for e in events if e["event"] == "token"]

        assert len(token_events) > 0
        # All token events should have content
        for te in token_events:
            assert "content" in te["data"]

    @pytest.mark.asyncio
    async def test_stream_contains_sql_generated_event(self, client) -> None:
        """SSE stream includes sql_generated event when SQL is produced."""
        resp = await client.post("/api/v1/conversations")
        conv_id = resp.json()["id"]

        mock_result = _mock_nl_service_result(
            explanation="Querying sales data",
            sql="SELECT * FROM sales LIMIT 10",
            columns=["id", "amount"],
            rows=[[1, 100], [2, 200]],
        )

        with patch(
            "app.api.v1.messages.NLQueryService"
        ) as mock_nl_cls:
            mock_instance = mock_nl_cls.return_value
            mock_instance.process_question = AsyncMock(return_value=mock_result)

            response = await client.post(
                f"/api/v1/conversations/{conv_id}/messages",
                json={"content": "Show me sales"},
            )

        events = _parse_sse_events(response.text)
        sql_events = [e for e in events if e["event"] == "sql_generated"]

        assert len(sql_events) == 1
        assert sql_events[0]["data"]["sql"] == "SELECT * FROM sales LIMIT 10"

    @pytest.mark.asyncio
    async def test_stream_contains_query_result_event(self, client) -> None:
        """SSE stream includes query_result event with columns and rows."""
        resp = await client.post("/api/v1/conversations")
        conv_id = resp.json()["id"]

        mock_result = _mock_nl_service_result(
            explanation="Results found",
            sql="SELECT id, name FROM users",
            columns=["id", "name"],
            rows=[[1, "Alice"], [2, "Bob"]],
        )

        with patch(
            "app.api.v1.messages.NLQueryService"
        ) as mock_nl_cls:
            mock_instance = mock_nl_cls.return_value
            mock_instance.process_question = AsyncMock(return_value=mock_result)

            response = await client.post(
                f"/api/v1/conversations/{conv_id}/messages",
                json={"content": "List users"},
            )

        events = _parse_sse_events(response.text)
        result_events = [e for e in events if e["event"] == "query_result"]

        assert len(result_events) == 1
        assert result_events[0]["data"]["columns"] == ["id", "name"]
        assert result_events[0]["data"]["rows"] == [[1, "Alice"], [2, "Bob"]]
        assert result_events[0]["data"]["row_count"] == 2


# ---------------------------------------------------------------------------
# Functional: Assistant message saved with metadata
# ---------------------------------------------------------------------------


class TestAssistantMessageSaved:
    """Test that assistant messages are persisted with metadata."""

    @pytest.mark.asyncio
    async def test_assistant_message_saved_with_sql_metadata(self, client, db) -> None:
        """Assistant message is saved with SQL in metadata."""
        resp = await client.post("/api/v1/conversations")
        conv_id = uuid.UUID(resp.json()["id"])

        mock_result = _mock_nl_service_result(
            explanation="Query executed",
            sql="SELECT COUNT(*) FROM users",
            columns=["count"],
            rows=[[42]],
        )

        with patch(
            "app.api.v1.messages.NLQueryService"
        ) as mock_nl_cls:
            mock_instance = mock_nl_cls.return_value
            mock_instance.process_question = AsyncMock(return_value=mock_result)

            await client.post(
                f"/api/v1/conversations/{conv_id}/messages",
                json={"content": "How many users?"},
            )

        # Verify assistant message was saved
        db.expire_all()
        messages = db.execute(
            select(Message)
            .where(
                Message.conversation_id == conv_id,
                Message.role == "assistant",
            )
        ).scalars().all()

        assert len(messages) == 1
        assert messages[0].metadata_ is not None
        assert messages[0].metadata_["sql"] == "SELECT COUNT(*) FROM users"

    @pytest.mark.asyncio
    async def test_conversation_history_maintained(self, client, db) -> None:
        """Multiple messages maintain conversation history order."""
        resp = await client.post("/api/v1/conversations")
        conv_id = uuid.UUID(resp.json()["id"])

        mock_result = _mock_nl_service_result(explanation="Response 1")

        with patch(
            "app.api.v1.messages.NLQueryService"
        ) as mock_nl_cls:
            mock_instance = mock_nl_cls.return_value
            mock_instance.process_question = AsyncMock(return_value=mock_result)

            # Send first message
            await client.post(
                f"/api/v1/conversations/{conv_id}/messages",
                json={"content": "First question"},
            )

            # Send second message
            mock_result2 = _mock_nl_service_result(explanation="Response 2")
            mock_instance.process_question = AsyncMock(return_value=mock_result2)

            await client.post(
                f"/api/v1/conversations/{conv_id}/messages",
                json={"content": "Second question"},
            )

        # Verify conversation history
        db.expire_all()
        messages = db.execute(
            select(Message)
            .where(Message.conversation_id == conv_id)
            .order_by(Message.created_at)
        ).scalars().all()

        assert len(messages) == 4  # 2 user + 2 assistant
        assert messages[0].role == "user"
        assert messages[0].content == "First question"
        assert messages[1].role == "assistant"
        assert messages[2].role == "user"
        assert messages[2].content == "Second question"
        assert messages[3].role == "assistant"


# ---------------------------------------------------------------------------
# Error Handling: AI errors and query errors
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Test error handling in the SSE stream."""

    @pytest.mark.asyncio
    async def test_ai_error_produces_error_event(self, client) -> None:
        """AI processing error produces an error SSE event."""
        resp = await client.post("/api/v1/conversations")
        conv_id = resp.json()["id"]

        with patch(
            "app.api.v1.messages.NLQueryService"
        ) as mock_nl_cls:
            mock_instance = mock_nl_cls.return_value
            mock_instance.process_question = AsyncMock(
                side_effect=Exception("AI provider unavailable")
            )

            response = await client.post(
                f"/api/v1/conversations/{conv_id}/messages",
                json={"content": "What data?"},
            )

        events = _parse_sse_events(response.text)
        error_events = [e for e in events if e["event"] == "error"]

        assert len(error_events) >= 1
        assert error_events[0]["data"]["code"] == "AI_ERROR"

    @pytest.mark.asyncio
    async def test_query_error_produces_error_event(self, client) -> None:
        """Query execution error produces an error SSE event."""
        resp = await client.post("/api/v1/conversations")
        conv_id = resp.json()["id"]

        mock_result = _mock_nl_service_result(
            explanation="The query failed",
            error="SQL syntax error near 'SELCET'",
            sql="SELCET * FROM users",
        )

        with patch(
            "app.api.v1.messages.NLQueryService"
        ) as mock_nl_cls:
            mock_instance = mock_nl_cls.return_value
            mock_instance.process_question = AsyncMock(return_value=mock_result)

            response = await client.post(
                f"/api/v1/conversations/{conv_id}/messages",
                json={"content": "Show users"},
            )

        events = _parse_sse_events(response.text)
        error_events = [e for e in events if e["event"] == "error"]

        assert len(error_events) >= 1
        assert error_events[0]["data"]["code"] == "QUERY_ERROR"

    @pytest.mark.asyncio
    async def test_no_provider_produces_error_event(self, client) -> None:
        """No AI provider configured produces an error SSE event."""
        resp = await client.post("/api/v1/conversations")
        conv_id = resp.json()["id"]

        with patch(
            "app.api.v1.messages.NLQueryService"
        ) as mock_nl_cls:
            mock_instance = mock_nl_cls.return_value
            mock_instance.process_question = AsyncMock(
                side_effect=Exception("No AI provider is configured")
            )

            response = await client.post(
                f"/api/v1/conversations/{conv_id}/messages",
                json={"content": "Hello"},
            )

        events = _parse_sse_events(response.text)
        error_events = [e for e in events if e["event"] == "error"]

        assert len(error_events) >= 1

    @pytest.mark.asyncio
    async def test_stream_always_ends_with_message_end_or_error(self, client) -> None:
        """Stream always terminates with message_end even after errors."""
        resp = await client.post("/api/v1/conversations")
        conv_id = resp.json()["id"]

        with patch(
            "app.api.v1.messages.NLQueryService"
        ) as mock_nl_cls:
            mock_instance = mock_nl_cls.return_value
            mock_instance.process_question = AsyncMock(
                side_effect=Exception("Unexpected error")
            )

            response = await client.post(
                f"/api/v1/conversations/{conv_id}/messages",
                json={"content": "Hello"},
            )

        events = _parse_sse_events(response.text)
        event_types = [e["event"] for e in events]

        # Should have both error and message_end
        assert "error" in event_types
        assert "message_end" in event_types


# ---------------------------------------------------------------------------
# Functional: SSE event ordering
# ---------------------------------------------------------------------------


class TestSSEEventOrdering:
    """Test that SSE events are emitted in the correct order."""

    @pytest.mark.asyncio
    async def test_event_order_for_successful_query(self, client) -> None:
        """Events for a successful query follow the correct order."""
        resp = await client.post("/api/v1/conversations")
        conv_id = resp.json()["id"]

        mock_result = _mock_nl_service_result(
            explanation="Found results",
            sql="SELECT * FROM data",
            columns=["col1"],
            rows=[["val1"]],
        )

        with patch(
            "app.api.v1.messages.NLQueryService"
        ) as mock_nl_cls:
            mock_instance = mock_nl_cls.return_value
            mock_instance.process_question = AsyncMock(return_value=mock_result)

            response = await client.post(
                f"/api/v1/conversations/{conv_id}/messages",
                json={"content": "Show data"},
            )

        events = _parse_sse_events(response.text)
        event_types = [e["event"] for e in events]

        # message_start should be first
        assert event_types[0] == "message_start"
        # message_end should be last
        assert event_types[-1] == "message_end"

        # sql_generated should come before query_result
        if "sql_generated" in event_types and "query_result" in event_types:
            sql_idx = event_types.index("sql_generated")
            result_idx = event_types.index("query_result")
            assert sql_idx < result_idx


# ---------------------------------------------------------------------------
# Edge Cases: Clarification and no-source responses
# ---------------------------------------------------------------------------


class TestEdgeCaseResponses:
    """Test edge case response types."""

    @pytest.mark.asyncio
    async def test_clarification_response_streams_tokens(self, client) -> None:
        """Clarification requests stream as token events."""
        resp = await client.post("/api/v1/conversations")
        conv_id = resp.json()["id"]

        mock_result = _mock_nl_service_result(
            needs_clarification=True,
            clarifying_question="Which table are you referring to?",
        )

        with patch(
            "app.api.v1.messages.NLQueryService"
        ) as mock_nl_cls:
            mock_instance = mock_nl_cls.return_value
            mock_instance.process_question = AsyncMock(return_value=mock_result)

            response = await client.post(
                f"/api/v1/conversations/{conv_id}/messages",
                json={"content": "Show me the data"},
            )

        events = _parse_sse_events(response.text)
        token_events = [e for e in events if e["event"] == "token"]

        # Should have token events with the clarification text
        assert len(token_events) > 0
        combined = "".join(e["data"]["content"] for e in token_events)
        assert "Which table" in combined

    @pytest.mark.asyncio
    async def test_no_source_response_streams_tokens(self, client) -> None:
        """No-source responses stream as token events."""
        resp = await client.post("/api/v1/conversations")
        conv_id = resp.json()["id"]

        mock_result = _mock_nl_service_result(
            no_relevant_source=True,
            no_source_message="No data sources available. Please upload a file.",
        )

        with patch(
            "app.api.v1.messages.NLQueryService"
        ) as mock_nl_cls:
            mock_instance = mock_nl_cls.return_value
            mock_instance.process_question = AsyncMock(return_value=mock_result)

            response = await client.post(
                f"/api/v1/conversations/{conv_id}/messages",
                json={"content": "What data?"},
            )

        events = _parse_sse_events(response.text)
        token_events = [e for e in events if e["event"] == "token"]

        assert len(token_events) > 0
        combined = "".join(e["data"]["content"] for e in token_events)
        assert "No data sources" in combined
