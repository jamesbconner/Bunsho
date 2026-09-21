import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useCountdown, useSecondsUntil } from './useCountdown';

describe('useCountdown', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(0);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('is idle until started, then counts whole seconds down to zero', () => {
    const { result } = renderHook(() => useCountdown());
    expect(result.current.remaining).toBe(0);
    act(() => {
      result.current.start(3);
    });
    expect(result.current.remaining).toBe(3);
    act(() => {
      vi.advanceTimersByTime(1_000);
    });
    expect(result.current.remaining).toBe(2);
    act(() => {
      vi.advanceTimersByTime(5_000);
    });
    expect(result.current.remaining).toBe(0);
  });

  it('can be restarted', () => {
    const { result } = renderHook(() => useCountdown());
    act(() => {
      result.current.start(2);
    });
    act(() => {
      vi.advanceTimersByTime(5_000);
    });
    expect(result.current.remaining).toBe(0);
    act(() => {
      result.current.start(10);
    });
    expect(result.current.remaining).toBe(10);
  });
});

describe('useSecondsUntil', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(0);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('is zero without a deadline and rounds partial seconds up', () => {
    expect(renderHook(() => useSecondsUntil(null)).result.current).toBe(0);
    const { result } = renderHook(() => useSecondsUntil(2_500));
    expect(result.current).toBe(3);
    act(() => {
      vi.advanceTimersByTime(1_000);
    });
    expect(result.current).toBe(2);
  });
});
