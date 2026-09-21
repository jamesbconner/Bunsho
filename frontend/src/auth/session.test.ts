import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { session } from './session';

const PAIR = { access_token: 'access-1', refresh_token: 'refresh-1', expires_in: 900 };

describe('session', () => {
  beforeEach(() => {
    session.clear();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('remembers the refresh token in localStorage and the access token in memory', () => {
    session.setTokens(PAIR, 1_000);
    expect(session.getRefreshToken()).toBe('refresh-1');
    expect(window.localStorage.getItem('bunsho.refresh_token')).toBe('refresh-1');
    expect(session.getAccessToken(1_000)).toBe('access-1');
    // The access token itself never reaches storage.
    expect(JSON.stringify({ ...window.localStorage })).not.toContain('access-1');
  });

  it('treats an access token as expired 30 seconds early', () => {
    session.setTokens(PAIR, 0);
    expect(session.getAccessToken(869_000)).toBe('access-1');
    expect(session.getAccessToken(870_000)).toBeNull();
  });

  it('clear forgets both tokens without notifying', () => {
    const listener = vi.fn();
    session.onExpired(listener);
    session.setTokens(PAIR);
    session.clear();
    expect(session.getRefreshToken()).toBeNull();
    expect(session.getAccessToken()).toBeNull();
    expect(listener).not.toHaveBeenCalled();
  });

  it('expire forgets both tokens and notifies every listener once', () => {
    const first = vi.fn();
    const second = vi.fn();
    const stopFirst = session.onExpired(first);
    session.onExpired(second);
    session.setTokens(PAIR);
    session.expire();
    expect(session.getRefreshToken()).toBeNull();
    expect(first).toHaveBeenCalledTimes(1);
    expect(second).toHaveBeenCalledTimes(1);
    stopFirst();
    session.expire();
    expect(first).toHaveBeenCalledTimes(1);
    expect(second).toHaveBeenCalledTimes(2);
  });

  it('keeps working when storage is blocked', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(() => {
      session.setTokens(PAIR, 0);
    }).not.toThrow();
    expect(session.getRefreshToken()).toBeNull(); // not remembered
    expect(session.getAccessToken(0)).toBe('access-1'); // but this tab still works
    expect(() => {
      session.clear();
    }).not.toThrow();
  });
});
