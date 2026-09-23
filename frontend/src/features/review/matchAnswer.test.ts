import { describe, expect, it } from 'vitest';

import { matches } from './matchAnswer';

describe('matches', () => {
  it('matches exactly, ignoring case', () => {
    expect(matches('Shi', ['shi', 'si'])).toBe(true);
    expect(matches('SHI', ['shi'])).toBe(true);
  });

  it('trims surrounding whitespace', () => {
    expect(matches('  shi  ', ['shi'])).toBe(true);
  });

  it('matches any of several accepted answers', () => {
    expect(matches('si', ['shi', 'si'])).toBe(true);
    expect(matches('zi', ['shi', 'si'])).toBe(false);
  });

  it('does not do partial or fuzzy matching', () => {
    expect(matches('shii', ['shi'])).toBe(false);
    expect(matches('sh', ['shi'])).toBe(false);
  });

  it('is false against an empty accepted list', () => {
    expect(matches('shi', [])).toBe(false);
  });
});
