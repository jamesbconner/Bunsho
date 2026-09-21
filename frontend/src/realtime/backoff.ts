const BASE_DELAY_MS = 1_000;
const MAX_DELAY_MS = 30_000;
/** Even a lucky jitter draw waits a little, so a broken server is never hammered. */
const MIN_DELAY_MS = 250;

/**
 * Reconnect delay after `attempt` failed attempts (0 for the first retry): exponential growth from
 * one second, capped at 30 seconds, with full jitter (a uniform draw between zero and the cap).
 */
export function nextDelayMs(attempt: number, random: () => number = Math.random): number {
  const ceiling = Math.min(MAX_DELAY_MS, BASE_DELAY_MS * 2 ** attempt);
  return Math.max(MIN_DELAY_MS, Math.round(random() * ceiling));
}
