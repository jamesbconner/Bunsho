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
/**
 * Counts how many times the session was ended (logout, expiry). A refresh remembers the epoch it
 * started in and its answer is dropped when the epoch has moved on, so a slow refresh can never
 * bring back a session the user has since left, or end the one they logged in to afterwards.
 */
let epoch = 0;
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

  /** The current epoch (see above); capture it before an asynchronous call that stores tokens. */
  getEpoch(): number {
    return epoch;
  },

  /**
   * Store a fresh token pair (after login or refresh). With `expectedEpoch`, a pair from an earlier
   * epoch is dropped. Returns whether the pair was stored.
   */
  setTokens(pair: TokenPair, now: number = Date.now(), expectedEpoch?: number): boolean {
    if (expectedEpoch !== undefined && expectedEpoch !== epoch) return false;
    accessToken = pair.access_token;
    accessExpiresAt = now + pair.expires_in * 1000;
    writeStoredRefreshToken(pair.refresh_token);
    return true;
  },

  /** Forget everything (logout) and start a new epoch. Does not notify. */
  clear(): void {
    epoch += 1;
    accessToken = null;
    accessExpiresAt = 0;
    writeStoredRefreshToken(null);
  },

  /**
   * The server rejected the refresh token: forget everything and tell the listeners. With
   * `expectedEpoch`, a rejection that belongs to an earlier epoch is ignored.
   */
  expire(expectedEpoch?: number): void {
    if (expectedEpoch !== undefined && expectedEpoch !== epoch) return;
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
