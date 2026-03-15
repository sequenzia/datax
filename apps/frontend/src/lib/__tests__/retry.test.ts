import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { retryWithBackoff, getRetryDelay } from "../retry";

describe("retryWithBackoff", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("returns immediately on first success", async () => {
    const fn = vi.fn().mockResolvedValue("ok");

    const promise = retryWithBackoff(fn);
    const result = await promise;

    expect(result).toEqual({ data: "ok", attempts: 1 });
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it("retries on failure and succeeds on second attempt", async () => {
    const fn = vi
      .fn()
      .mockRejectedValueOnce(new Error("fail"))
      .mockResolvedValue("ok");

    const promise = retryWithBackoff(fn);

    // First call fails, then waits 1s before retry
    await vi.advanceTimersByTimeAsync(1000);

    const result = await promise;
    expect(result).toEqual({ data: "ok", attempts: 2 });
    expect(fn).toHaveBeenCalledTimes(2);
  });

  it("uses exponential backoff: 1s, 2s, 4s delays", async () => {
    const fn = vi
      .fn()
      .mockRejectedValueOnce(new Error("fail 1"))
      .mockRejectedValueOnce(new Error("fail 2"))
      .mockResolvedValue("ok");

    const promise = retryWithBackoff(fn);

    // After first failure, wait 1s (baseDelayMs * 2^0 = 1000)
    await vi.advanceTimersByTimeAsync(1000);
    expect(fn).toHaveBeenCalledTimes(2);

    // After second failure, wait 2s (baseDelayMs * 2^1 = 2000)
    await vi.advanceTimersByTimeAsync(2000);

    const result = await promise;
    expect(result).toEqual({ data: "ok", attempts: 3 });
    expect(fn).toHaveBeenCalledTimes(3);
  });

  it("throws after maxAttempts exhausted", async () => {
    const fn = vi.fn().mockRejectedValue(new Error("always fails"));

    // Attach the error handler immediately so the rejection is never "unhandled"
    let caughtError: unknown;
    const promise = retryWithBackoff(fn, { maxAttempts: 3 }).catch((err) => {
      caughtError = err;
    });

    // Advance past all retry delays: 1s then 2s
    await vi.advanceTimersByTimeAsync(1000);
    await vi.advanceTimersByTimeAsync(2000);
    await vi.advanceTimersByTimeAsync(0);

    await promise;
    expect(caughtError).toBeInstanceOf(Error);
    expect((caughtError as Error).message).toBe("always fails");
    expect(fn).toHaveBeenCalledTimes(3);
  });

  it("does not retry AbortErrors", async () => {
    const fn = vi
      .fn()
      .mockRejectedValue(new DOMException("Aborted", "AbortError"));

    await expect(retryWithBackoff(fn)).rejects.toThrow("Aborted");
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it("respects custom options", async () => {
    const fn = vi
      .fn()
      .mockRejectedValueOnce(new Error("fail"))
      .mockResolvedValue("ok");

    const promise = retryWithBackoff(fn, {
      maxAttempts: 2,
      baseDelayMs: 500,
      multiplier: 3,
    });

    // First retry delay: 500ms * 3^0 = 500ms
    await vi.advanceTimersByTimeAsync(500);

    const result = await promise;
    expect(result).toEqual({ data: "ok", attempts: 2 });
  });

  it("aborts waiting when signal is triggered", async () => {
    const fn = vi.fn().mockRejectedValue(new Error("fail"));
    const controller = new AbortController();

    let caughtError: unknown;
    const promise = retryWithBackoff(fn, { maxAttempts: 3 }, controller.signal).catch(
      (err) => {
        caughtError = err;
      },
    );

    // First call fails, then it starts waiting 1s
    // Abort during the wait
    controller.abort();

    await promise;
    expect(caughtError).toBeInstanceOf(DOMException);
    expect((caughtError as DOMException).name).toBe("AbortError");
    expect(fn).toHaveBeenCalledTimes(1);
  });
});

describe("getRetryDelay", () => {
  it("returns correct delays for default options", () => {
    expect(getRetryDelay(0)).toBe(1000);
    expect(getRetryDelay(1)).toBe(2000);
    expect(getRetryDelay(2)).toBe(4000);
  });

  it("returns correct delays for custom options", () => {
    expect(getRetryDelay(0, { baseDelayMs: 500, multiplier: 3 })).toBe(500);
    expect(getRetryDelay(1, { baseDelayMs: 500, multiplier: 3 })).toBe(1500);
    expect(getRetryDelay(2, { baseDelayMs: 500, multiplier: 3 })).toBe(4500);
  });
});
