import { describe, expect, it } from 'vitest';

import { formatCount } from './format';

describe('formatCount', () => {
  it('groups thousands the same way everywhere', () => {
    expect(formatCount(0)).toBe('0');
    expect(formatCount(999)).toBe('999');
    expect(formatCount(7734)).toBe('7,734');
    expect(formatCount(1234567)).toBe('1,234,567');
  });
});
