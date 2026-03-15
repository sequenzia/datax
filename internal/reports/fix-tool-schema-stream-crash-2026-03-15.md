# Codebase Changes Report

## Metadata

| Field | Value |
|-------|-------|
| **Date** | 2026-03-15 |
| **Time** | 15:54 EDT |
| **Branch** | main |
| **Author** | Stephen Sequenzia |
| **Base Commit** | a215160 |
| **Latest Commit** | uncommitted |
| **Repository** | git@github.com:sequenzia/datax.git |

**Scope**: Fix chat stream crash caused by tool schema rejected by LLM provider

**Summary**: Replaced `list[list[Any]]` type annotations in agent tool parameters with an explicit `JsonScalar` union type (`str | int | float | bool | None`) to prevent OpenAI's function calling API from rejecting tool schemas that contain empty `{}` items without a `type` key. Added `_ensure_run_defaults` to the AG-UI endpoint to inject missing `RunAgentInput` fields that CopilotKit v1.54 omits, and comprehensive tests for both fixes.

## Overview

- **Files affected**: 3
- **Lines added**: +226
- **Lines removed**: -5
- **Commits**: 0 (all changes uncommitted)

## Files Changed

| File | Status | Lines | Description |
|------|--------|-------|-------------|
| `apps/backend/src/app/services/agent_tools.py` | Modified | +7 / -2 | Add `JsonScalar` type alias, replace `Any` in `render_chart` and `render_table` params |
| `apps/backend/src/app/agui.py` | Modified | +33 / -2 | Add `_ensure_run_defaults` function and wire it into both agent and error endpoints |
| `apps/backend/tests/test_agui.py` | Modified | +186 / -1 | Add tool schema validity test, `_ensure_run_defaults` unit/integration tests |

## Change Details

### Modified

- **`apps/backend/src/app/services/agent_tools.py`** — Added `JsonScalar = str | int | float | bool | None` type alias at module level with explanatory comment. Changed the `rows` parameter type annotation in both `render_chart` (line 438) and `render_table` (line 488) from `list[list[Any]]` to `list[list[JsonScalar]]`. This ensures pydantic-ai generates JSON schemas with explicit `type` keys on all `items` nodes, which OpenAI's function calling API requires. Result models (`QueryResult`, `TableResult`, etc.) were intentionally left unchanged since they are only used for `.model_dump()` serialization, not schema generation.

- **`apps/backend/src/app/agui.py`** — Added `_RUN_INPUT_DEFAULTS` dict and `_ensure_run_defaults()` function that injects safe empty defaults for `state`, `tools`, `context`, and `forwardedProps` fields when CopilotKit v1.54 omits them from the `RunAgentInput` payload. Wired the function into both the `_error_endpoint` (no-provider path) and `_agent_endpoint` (normal path), called after `_unwrap_envelope`. Also fixed the `_unwrap_envelope` call sites to capture the returned body value (`body = _unwrap_envelope(body, request)` instead of discarding the return).

- **`apps/backend/tests/test_agui.py`** — Added `TestToolSchemaValidity` class with `test_no_empty_schema_in_tool_params` that creates a pydantic-ai Agent with the test model, registers all 9 tools, and recursively walks each tool's parameter JSON schema to verify no empty `{}` nodes exist. Added `TestAGUIEnvelopeNoProvider` class (extracted from `TestAGUIEnvelopeUnwrap`) for the no-provider envelope test. Added `TestAGUIRunDefaults` class with 4 tests: `test_injects_missing_fields` (unit), `test_preserves_existing_values` (unit), `test_missing_defaults_returns_200` (integration), and `test_envelope_missing_defaults_returns_200` (integration). Updated import to include `_ensure_run_defaults`.

## Git Status

### Unstaged Changes

| File | Status |
|------|--------|
| `apps/backend/src/app/agui.py` | Modified |
| `apps/backend/src/app/services/agent_tools.py` | Modified |
| `apps/backend/tests/test_agui.py` | Modified |

## Session Commits

No commits in this session. All changes are uncommitted.

## Root Cause Analysis

The SSE stream crash occurred because:

1. `list[list[Any]]` in Python generates `{"items": {"items": {}, "type": "array"}, "type": "array"}` in JSON Schema — the inner `{}` has no `type` key.
2. OpenAI's function calling API requires every schema element to have an explicit `type` key, rejecting tool definitions with empty `{}` schemas.
3. This error occurred mid-stream (during the model request phase after SSE connection was established), causing pydantic-ai to emit a `RUN_ERROR` event and terminate the stream.
4. CopilotKit surfaced this as `ERR_INCOMPLETE_CHUNKED_ENCODING` / "network error" in the browser.

The fix replaces `Any` with `JsonScalar` (`str | int | float | bool | None`), which generates proper `anyOf` arrays where every entry has an explicit `type` key.

## Test Results

All 26 tests pass (`uv run pytest tests/test_agui.py -v`):

- `TestAGUIMount`: 4 passed
- `TestAGUIHandshake`: 5 passed
- `TestAGUINoProvider`: 3 passed
- `TestAGUIHealth`: 3 passed
- `TestAGUIEnvelopeUnwrap`: 5 passed
- `TestToolSchemaValidity`: 1 passed
- `TestAGUIEnvelopeNoProvider`: 1 passed
- `TestAGUIRunDefaults`: 4 passed
