/** A fraction as a percentage with one decimal: 0.8765 becomes "87.7%". */
export function formatPercent(fraction: number): string {
  return `${(Math.round(fraction * 1000) / 10).toFixed(1)}%`;
}

/** A study day ("2026-09-20") as a short label ("Sep 20"), the same in every timezone. */
export function formatShortDay(day: string): string {
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(`${day}T00:00:00Z`));
}
