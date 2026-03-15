/**
 * Exponential backoff retry utility.
 *
 * Retries a function up to `maxAttempts` times with exponential delays.
 * Default: 3 attempts with 1s, 2s, 4s delays.
 */

export interface RetryOptions {
  /** Maximum number of attempts (including the first). Default: 3 */
  maxAttempts?: number;
  /** Base delay in ms before the first retry. Default: 1000 */
  baseDelayMs?: number;
  /** Multiplier applied to the delay on each retry. Default: 2 */
  multiplier?: number;
}

export interface RetryResult<T> {
  data: T;
  attempts: number;
}

const DEFAULT_OPTIONS: Required<RetryOptions> = {
  maxAttempts: 3,
  baseDelayMs: 1000,
  multiplier: 2,
};

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        reject(new DOMException("Aborted", "AbortError"));
      },
      { once: true },
    );
  });
}

/**
 * Execute `fn` with exponential backoff retry.
 *
 * Delays between attempts: baseDelayMs, baseDelayMs * multiplier, baseDelayMs * multiplier^2, ...
 * With defaults: 1s, 2s, 4s
 */
export async function retryWithBackoff<T>(
  fn: () => Promise<T>,
  options?: RetryOptions,
  signal?: AbortSignal,
): Promise<RetryResult<T>> {
  const { maxAttempts, baseDelayMs, multiplier } = {
    ...DEFAULT_OPTIONS,
    ...options,
  };

  let lastError: unknown;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      const data = await fn();
      return { data, attempts: attempt };
    } catch (err) {
      lastError = err;

      // Don't retry AbortErrors
      if (err instanceof DOMException && err.name === "AbortError") {
        throw err;
      }

      // Don't retry after the last attempt
      if (attempt === maxAttempts) {
        break;
      }

      // Wait with exponential delay: 1s, 2s, 4s for defaults
      const delay = baseDelayMs * Math.pow(multiplier, attempt - 1);
      await sleep(delay, signal);
    }
  }

  throw lastError;
}

/**
 * Calculate the delay for a given attempt (0-indexed retry number).
 * Useful for displaying retry timing or testing.
 */
export function getRetryDelay(
  retryIndex: number,
  options?: RetryOptions,
): number {
  const { baseDelayMs, multiplier } = { ...DEFAULT_OPTIONS, ...options };
  return baseDelayMs * Math.pow(multiplier, retryIndex);
}
