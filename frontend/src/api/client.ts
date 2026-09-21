import { session } from '../auth/session';
import { ApiError } from './errors';
import { rawRequest, type RequestOptions } from './http';
import type { components } from './schema';

type TokenResponse = components['schemas']['TokenResponse'];

let refreshInFlight: Promise<void> | null = null;

async function refreshOnce(): Promise<void> {
  const refreshToken = session.getRefreshToken();
  if (refreshToken === null) {
    session.expire();
    throw new ApiError(401, 'Not signed in');
  }
  try {
    const pair = await rawRequest<TokenResponse>('/auth/refresh', {
      method: 'POST',
      body: { refresh_token: refreshToken },
    });
    session.setTokens(pair);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) session.expire();
    throw error;
  }
}

/**
 * Exchange the refresh token for a new pair. Concurrent callers share one request. A 401 from the
 * server ends the session (listeners of `session.onExpired` are told); other errors propagate and
 * leave the session untouched, so a server restart never logs anybody out.
 */
export function refreshSession(): Promise<void> {
  refreshInFlight ??= refreshOnce().finally(() => {
    refreshInFlight = null;
  });
  return refreshInFlight;
}

/** A usable access token, refreshing first when there is none or it is about to expire. */
export async function ensureAccessToken(): Promise<string> {
  const current = session.getAccessToken();
  if (current !== null) return current;
  await refreshSession();
  const refreshed = session.getAccessToken();
  if (refreshed === null) throw new ApiError(401, 'Not signed in');
  return refreshed;
}

/**
 * An authenticated API call: attaches the bearer token and, when the server answers 401,
 * refreshes the session once and retries the call once.
 */
export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const send = (token: string): Promise<T> =>
    rawRequest<T>(path, {
      ...options,
      headers: { ...options.headers, Authorization: `Bearer ${token}` },
    });
  // Outside the try: a 401 raised while getting a token is not the server rejecting this call, so
  // it must not trigger a second refresh (which would end the session, and notify, twice).
  const token = await ensureAccessToken();
  try {
    return await send(token);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      await refreshSession();
      return send(await ensureAccessToken());
    }
    throw error;
  }
}
