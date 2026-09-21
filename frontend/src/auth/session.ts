/**
 * The login session: the refresh token is remembered in localStorage, the short-lived access
 * token only in memory. Nothing here ever logs or exposes a token outside this module's API.
 */

import type { components } from '../api/schema';

export const REFRESH_TOKEN_KEY = 'bunsho.refresh_token';
/** Treat an access token as expired this long before it really is, so requests never race it. */
const EXPIRY_MARGIN_MS = 30_000;

export type TokenPair = Pick<
  components['schemas']['TokenResponse'],
  'access_token' | 'refresh_token' | 'expires_in'
>;

let accessToken: string | null = null;
let accessExpiresAt = 0;
const expiredListeners = new Set<() => void>();

function readStoredRefreshToken(): string | null {
  try {
    return window.localStorage.getItem(REFRESH_TOKEN_KEY);
  } catch {
    return null; // storage blocked (private mode, policy): the session is simply not remembered
  }
}

function writeStoredRefreshToken(value: string | null): void {
  try {
    if (value === null) {
      window.localStorage.removeItem(REFRESH_TOKEN_KEY);
    } else {
      window.localStorage.setItem(REFRESH_TOKEN_KEY, value);
    }
  } catch {
    // storage blocked: keep going with the in-memory access token only
  }
}

export const session = {
  /** The remembered refresh token, or null when there is none (or storage is blocked). */
  getRefreshToken: readStoredRefreshToken,

  /** The access token, or null when missing or about to expire. */
  getAccessToken(now: number = Date.now()): string | null {
    return accessToken !== null && now < accessExpiresAt - EXPIRY_MARGIN_MS ? accessToken : null;
  },

  /** Store a fresh token pair (after login or refresh). */
  setTokens(pair: TokenPair, now: number = Date.now()): void {
    accessToken = pair.access_token;
    accessExpiresAt = now + pair.expires_in * 1000;
    writeStoredRefreshToken(pair.refresh_token);
  },

  /** Forget everything (logout). Does not notify. */
  clear(): void {
    accessToken = null;
    accessExpiresAt = 0;
    writeStoredRefreshToken(null);
  },

  /** The server rejected the refresh token: forget everything and tell the listeners. */
  expire(): void {
    this.clear();
    for (const listener of [...expiredListeners]) {
      listener();
    }
  },

  /** Be told when the session expired. Returns an unsubscribe function. */
  onExpired(listener: () => void): () => void {
    expiredListeners.add(listener);
    return () => {
      expiredListeners.delete(listener);
    };
  },
};
