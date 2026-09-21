import { describe, expect, it } from 'vitest';

import { formatPercent, formatShortDay } from './format';

describe('formatPercent', () => {
  it.each([
    [0, '0.0%'],
    [0.8765, '87.7%'],
    [0.9, '90.0%'],
    [1, '100.0%'],
    [0.00049, '0.0%'],
  ])('formats %s as %s', (fraction, label) => {
    expect(formatPercent(fraction)).toBe(label);
  });
});

describe('formatShortDay', () => {
  it('formats a study day as month and day whatever the timezone', () => {
    expect(formatShortDay('2026-09-20')).toMatch(/Sep(tember)? 20/);
    expect(formatShortDay('2026-01-01')).toMatch(/Jan(uary)? 1/);
  });
});
