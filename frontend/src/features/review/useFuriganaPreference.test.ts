import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { FURIGANA_KEY, useFuriganaPreference } from './useFuriganaPreference';

describe('useFuriganaPreference', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('is off by default', () => {
    const { result } = renderHook(() => useFuriganaPreference());
    expect(result.current[0]).toBe(false);
  });

  it('remembers the choice in this browser', () => {
    const first = renderHook(() => useFuriganaPreference());
    act(() => {
      first.result.current[1](true);
    });
    expect(first.result.current[0]).toBe(true);
    expect(window.localStorage.getItem(FURIGANA_KEY)).toBe('true');

    const second = renderHook(() => useFuriganaPreference());
    expect(second.result.current[0]).toBe(true);
  });

  it('still works for this visit when storage is blocked', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });
    const { result } = renderHook(() => useFuriganaPreference());
    expect(result.current[0]).toBe(false);
    act(() => {
      result.current[1](true);
    });
    expect(result.current[0]).toBe(true);
  });
});
