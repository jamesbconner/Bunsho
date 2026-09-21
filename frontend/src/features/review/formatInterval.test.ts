import { describe, expect, it } from 'vitest';

import { formatDueTime, formatInterval } from './formatInterval';

describe('formatInterval', () => {
  it.each([
    [0, '0 s'],
    [-5, '0 s'],
    [45, '45 s'],
    [60, '1 m'],
    [600, '10 m'],
    [3_600, '1 h'],
    [7_200, '2 h'],
    [86_400, '1 d'],
    [345_600, '4 d'],
    [2_592_000, '1 mo'],
    [7_776_000, '3 mo'],
    [31_536_000, '1 y'],
  ])('formats %i seconds as %s', (seconds, label) => {
    expect(formatInterval(seconds)).toBe(label);
  });
});

describe('formatDueTime', () => {
  it('formats an ISO instant with a date and a time', () => {
    const text = formatDueTime('2026-09-21T08:30:00Z');
    expect(text).toMatch(/2026/);
    expect(text).toMatch(/\d{1,2}:\d{2}/);
  });
});
