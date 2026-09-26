import { describe, expect, it } from 'vitest';

import { returnPath } from './returnPath';

describe('returnPath', () => {
  it.each([
    ['/build', '/build'],
    ['/', '/'],
    ['/review?mode=typed', '/review?mode=typed'],
    ['/stats#kana', '/stats#kana'],
    ['/build?tab=system#top', '/build?tab=system#top'],
  ])('keeps the same-site path %s', (from, expected) => {
    expect(returnPath({ from })).toBe(expected);
  });

  it.each([
    ['a protocol-relative URL', '//evil.example'],
    ['a backslash after the slash', '/\\evil.example'],
    ['a backslash anywhere', '/build\\..\\x'],
    ['a tab', '/\t/evil.example'],
    ['a line feed', '/build\nx'],
    ['a carriage return', '/build\rx'],
    ['a NUL', '/build\u0000'],
    ['a DEL', '/build\u007f'],
    ['an absolute URL', 'https://evil.example/'],
    ['a relative path', 'build'],
    ['an empty string', ''],
  ])('falls back to the home page for %s', (_name, from) => {
    expect(returnPath({ from })).toBe('/');
  });

  it.each([
    ['no state', null],
    ['undefined state', undefined],
    ['a string state', '/build'],
    ['state without from', {}],
    ['a non-string from', { from: 42 }],
  ])('falls back to the home page for %s', (_name, state) => {
    expect(returnPath(state)).toBe('/');
  });
});
