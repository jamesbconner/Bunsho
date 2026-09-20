/** Whole numbers with thousands separators, the same on every machine. */
export function formatCount(value: number): string {
  return value.toLocaleString('en-US');
}
