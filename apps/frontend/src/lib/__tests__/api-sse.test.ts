import { describe, it, expect, vi, beforeEach } from "vitest";
import { sendMessageSSE } from "../api";
import type { SSECallbacks } from "../api";

/** Encode a series of SSE frames into a ReadableStream of Uint8Array chunks. */
function sseStream(frames: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  let index = 0;
  return new ReadableStream({
    pull(controller) {
      if (index < frames.length) {
        controller.enqueue(encoder.encode(frames[index]));
        index++;
      } else {
        controller.close();
      }
    },
  });
}

/**
 * Build a single SSE frame string (event + data + blank line terminator).
 * Uses CRLF separators to match real sse-starlette v2.x output.
 */
function sseFrame(event: string, data: Record<string, unknown>): string {
  return `event: ${event}\r\ndata: ${JSON.stringify(data)}\r\n\r\n`;
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("sendMessageSSE", () => {
  it("passes content field from token events to onToken callback", async () => {
    const frames = [
      sseFrame("token", { content: "Hello" }),
      sseFrame("token", { content: " world" }),
      sseFrame("message_end", { message_id: "m1" }),
    ];

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        body: sseStream(frames),
      }),
    );

    const callbacks: SSECallbacks = {
      onToken: vi.fn(),
      onMessageEnd: vi.fn(),
    };

    sendMessageSSE("conv-1", "hi", callbacks);

    // Wait for the stream to be fully consumed
    await vi.waitFor(() => {
      expect(callbacks.onMessageEnd).toHaveBeenCalled();
    });

    expect(callbacks.onToken).toHaveBeenCalledTimes(2);
    expect(callbacks.onToken).toHaveBeenNthCalledWith(1, "Hello");
    expect(callbacks.onToken).toHaveBeenNthCalledWith(2, " world");
  });

  it("handles sql_generated events", async () => {
    const frames = [
      sseFrame("sql_generated", { sql: "SELECT 1" }),
      sseFrame("message_end", { message_id: "m2" }),
    ];

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        body: sseStream(frames),
      }),
    );

    const callbacks: SSECallbacks = {
      onSqlGenerated: vi.fn(),
      onMessageEnd: vi.fn(),
    };

    sendMessageSSE("conv-1", "query", callbacks);

    await vi.waitFor(() => {
      expect(callbacks.onMessageEnd).toHaveBeenCalled();
    });

    expect(callbacks.onSqlGenerated).toHaveBeenCalledWith("SELECT 1");
  });

  it("handles query_result and chart_config events", async () => {
    const queryResult = { columns: ["a"], rows: [[1]] };
    const chartConfig = { type: "bar", data: {} };

    const frames = [
      sseFrame("query_result", queryResult),
      sseFrame("chart_config", chartConfig),
      sseFrame("message_end", { message_id: "m3" }),
    ];

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        body: sseStream(frames),
      }),
    );

    const callbacks: SSECallbacks = {
      onQueryResult: vi.fn(),
      onChartConfig: vi.fn(),
      onMessageEnd: vi.fn(),
    };

    sendMessageSSE("conv-1", "chart", callbacks);

    await vi.waitFor(() => {
      expect(callbacks.onMessageEnd).toHaveBeenCalled();
    });

    expect(callbacks.onQueryResult).toHaveBeenCalledWith(queryResult);
    expect(callbacks.onChartConfig).toHaveBeenCalledWith(chartConfig);
  });

  it("handles error events", async () => {
    const frames = [
      sseFrame("error", { message: "Something went wrong" }),
      sseFrame("message_end", { message_id: "m4" }),
    ];

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        body: sseStream(frames),
      }),
    );

    const callbacks: SSECallbacks = {
      onError: vi.fn(),
      onMessageEnd: vi.fn(),
    };

    sendMessageSSE("conv-1", "fail", callbacks);

    await vi.waitFor(() => {
      expect(callbacks.onMessageEnd).toHaveBeenCalled();
    });

    expect(callbacks.onError).toHaveBeenCalledWith("Something went wrong");
  });

  it("calls onError when response is not ok", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        statusText: "Internal Server Error",
        text: vi.fn().mockResolvedValue("server error"),
      }),
    );

    const callbacks: SSECallbacks = {
      onError: vi.fn(),
    };

    sendMessageSSE("conv-1", "fail", callbacks);

    await vi.waitFor(() => {
      expect(callbacks.onError).toHaveBeenCalled();
    });

    expect(callbacks.onError).toHaveBeenCalledWith("server error");
  });

  it("handles CRLF line endings from sse-starlette", async () => {
    // Explicitly construct CRLF-terminated frames to verify \r stripping
    const raw =
      "event: token\r\ndata: {\"content\":\"crlftest\"}\r\n\r\n" +
      "event: message_end\r\ndata: {\"message_id\":\"m5\"}\r\n\r\n";

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        body: sseStream([raw]),
      }),
    );

    const callbacks: SSECallbacks = {
      onToken: vi.fn(),
      onMessageEnd: vi.fn(),
    };

    sendMessageSSE("conv-1", "crlf", callbacks);

    await vi.waitFor(() => {
      expect(callbacks.onMessageEnd).toHaveBeenCalled();
    });

    expect(callbacks.onToken).toHaveBeenCalledWith("crlftest");
  });

  it("handles SSE events split across multiple chunks", async () => {
    // Simulate TCP splitting the event: line and data: line into separate chunks
    const chunk1 = "event: token\r\n";
    const chunk2 = "data: {\"content\":\"split\"}\r\n\r\n";
    const chunk3 =
      "event: message_end\r\ndata: {\"message_id\":\"m6\"}\r\n\r\n";

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        body: sseStream([chunk1, chunk2, chunk3]),
      }),
    );

    const callbacks: SSECallbacks = {
      onToken: vi.fn(),
      onMessageEnd: vi.fn(),
    };

    sendMessageSSE("conv-1", "split", callbacks);

    await vi.waitFor(() => {
      expect(callbacks.onMessageEnd).toHaveBeenCalled();
    });

    expect(callbacks.onToken).toHaveBeenCalledWith("split");
  });

  it("handles LF-only line endings (standard SSE)", async () => {
    // Ensure backwards compatibility with LF-only servers
    const raw =
      "event: token\ndata: {\"content\":\"lfonly\"}\n\n" +
      "event: message_end\ndata: {\"message_id\":\"m7\"}\n\n";

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        body: sseStream([raw]),
      }),
    );

    const callbacks: SSECallbacks = {
      onToken: vi.fn(),
      onMessageEnd: vi.fn(),
    };

    sendMessageSSE("conv-1", "lf", callbacks);

    await vi.waitFor(() => {
      expect(callbacks.onMessageEnd).toHaveBeenCalled();
    });

    expect(callbacks.onToken).toHaveBeenCalledWith("lfonly");
  });
});
