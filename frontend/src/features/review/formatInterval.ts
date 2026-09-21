const MINUTE = 60;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;
const MONTH = 30 * DAY;
const YEAR = 365 * DAY;

/** A projected interval in seconds as a short label for a grade button: "10 m", "4 d", "2 mo". */
export function formatInterval(seconds: number): string {
  const value = Math.max(0, seconds);
  if (value < MINUTE) return `${Math.round(value)} s`;
  if (value < HOUR) return `${Math.round(value / MINUTE)} m`;
  if (value < DAY) return `${Math.round(value / HOUR)} h`;
  if (value < MONTH) return `${Math.round(value / DAY)} d`;
  if (value < YEAR) return `${Math.round(value / MONTH)} mo`;
  return `${Math.round(value / YEAR)} y`;
}

/** When something is next due, in the reader's locale: "Sep 21, 2026, 8:30 AM". */
export function formatDueTime(iso: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(
    new Date(iso),
  );
}
