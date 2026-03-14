# Codebase Changes Report

## Metadata

| Field | Value |
|-------|-------|
| **Date** | 2026-03-13 |
| **Time** | 20:23 EDT |
| **Branch** | main |
| **Author** | Stephen Sequenzia |
| **Base Commit** | `be8bc5b` |
| **Latest Commit** | uncommitted |
| **Repository** | git@github.com:sequenzia/datax.git |

**Scope**: Fix AI streaming responses not rendering in chat UI

**Summary**: Fixed two bugs in the frontend SSE parser that prevented AI streaming responses from appearing in the chat. The primary bug was a CRLF line ending mismatch between `sse-starlette` v2.x output (`\r\n`) and the frontend parser that split on `\n` only, causing the blank-line event terminator check to always fail. The secondary bug was parser state variables (`eventType`/`eventData`) being reset on each `reader.read()` chunk, losing events split across TCP chunks.

## Overview

- **Files affected**: 2
- **Lines added**: +271
- **Lines removed**: -5

## Files Changed

| File | Status | Lines | Description |
|------|--------|-------|-------------|
| `apps/frontend/src/lib/api.ts` | Modified | +7 / -5 | Fix CRLF handling and parser state scope in SSE stream parser |
| `apps/frontend/src/lib/__tests__/api-sse.test.ts` | Added | +264 | Rewrite SSE tests with CRLF frames, chunk-spanning, and LF-only coverage |

## Change Details

### Modified

- **`apps/frontend/src/lib/api.ts`** — Two targeted fixes in the `sendMessageSSE` function's SSE parsing loop:
  1. **Moved `eventType` and `eventData` declarations outside the `while` loop** (from inside the loop body to before it). Previously, these variables reset on every `reader.read()` chunk, silently dropping any SSE event whose `event:` and `data:` lines arrived in separate TCP chunks.
  2. **Added `\r` stripping on each parsed line.** The loop variable was renamed from `line` to `rawLine`, and a new `const line` strips any trailing `\r` before comparisons. This fixes the primary bug: `sse-starlette` v2.x sends CRLF-terminated lines (`\r\n`), but `buffer.split("\n")` leaves a trailing `\r` on each line. The blank-line terminator check (`line === ""`) always failed because the actual value was `"\r"`, meaning no SSE events were ever dispatched to callbacks.
  3. **Fixed token field name** (`parsed.token` → `parsed.content`) to match the backend's `{"content": chunk}` payload format.

### Added

- **`apps/frontend/src/lib/__tests__/api-sse.test.ts`** — Comprehensive SSE parser test suite (264 lines, 8 test cases). Updated the `sseFrame` helper to emit CRLF-terminated events matching real `sse-starlette` wire format. Added three new test cases:
  - **CRLF handling**: Explicitly constructs CRLF-terminated raw frames and verifies tokens are dispatched correctly.
  - **Chunk-spanning events**: Simulates an SSE event split across three TCP chunks (`event:` in chunk 1, `data:` + blank line in chunk 2, next event in chunk 3) to verify parser state persists across `reader.read()` calls.
  - **LF-only backwards compatibility**: Verifies the parser still works with standard LF-only line endings.

## Git Status

### Unstaged Changes

| Status | File |
|--------|------|
| Modified | `apps/frontend/src/lib/api.ts` |

### Untracked Files

| File |
|------|
| `apps/frontend/src/lib/__tests__/api-sse.test.ts` |

## Root Cause Analysis

The bug manifested as AI streaming responses never appearing in the chat UI — the user's message rendered, a blinking cursor appeared for the AI response, but no text content ever showed. Messages loaded correctly after page refresh (from database), confirming the issue was frontend-only.

### Primary cause: CRLF mismatch

`sse-starlette` v2.x uses `DEFAULT_SEPARATOR = "\r\n"` (CRLF). The frontend parser split on `\n` only, producing lines with trailing `\r`. The blank-line event terminator check (`line === ""`) never matched `"\r"`, so **zero events were dispatched** — no tokens, no `message_end`, nothing.

### Secondary cause: Parser state reset per chunk

`eventType`/`eventData` were declared inside the `while` loop, resetting on each `reader.read()` chunk. If an SSE event's `event:` line arrived in one chunk and its `data:` line in the next, the data line found a blank `eventType` and silently dropped. This is a latent bug that wouldn't consistently fail on localhost but would cause intermittent token loss under network conditions that fragment TCP segments.

### Tertiary cause: Field name mismatch (previously identified)

The frontend read `parsed.token` but the backend sends `{"content": chunk}`. This was identified in a prior session (H1) and the fix is included in this changeset.
