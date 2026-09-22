function normalize(text: string): string {
  return text.trim().toLowerCase();
}

/**
 * Whether `given` matches any of `accepted`, ignoring case and surrounding whitespace. Exact
 * match only after normalization — no partial or fuzzy matching, by design (a near-miss typo
 * is simply wrong).
 */
export function matches(given: string, accepted: readonly string[]): boolean {
  const normalized = normalize(given);
  return accepted.some((answer) => normalize(answer) === normalized);
}
