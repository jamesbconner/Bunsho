import { session } from '../auth/session';
import { ApiError } from './errors';
import { rawRequest, type RequestOptions } from './http';
import type { components } from './schema';

type TokenResponse = components['schemas']['TokenResponse'];

let refreshInFlight: { epoch: number; promise: Promise<void> } | null = null;

async function refreshOnce(epoch: number): Promise<void> {
  const refreshToken = session.getRefreshToken();
  if (refreshToken === null) {
    session.expire(epoch);
    throw new ApiError(401, 'Not signed in');
  }
  let pair: TokenResponse;
  try {
    pair = await rawRequest<TokenResponse>('/auth/refresh', {
      method: 'POST',
      body: { refresh_token: refreshToken },
    });
  } catch (error) {
    // A 401 only ends the session it belongs to: after a logout and a new login it is stale.
    if (error instanceof ApiError && error.status === 401) session.expire(epoch);
    throw error;
  }
  // The user logged out (or the session ended) while this was in flight: drop the answer.
  if (!session.setTokens(pair, Date.now(), epoch)) throw new ApiError(401, 'Session changed');
}

/**
 * Exchange the refresh token for a new pair. Concurrent callers of the same session share one
 * request. A 401 from the server ends the session (listeners of `session.onExpired` are told);
 * other errors propagate and leave the session untouched, so a server restart never logs anybody
 * out. If the session ended while the request was in flight the answer is discarded and this
 * rejects with a 401 without notifying anybody.
 */
export function refreshSession(): Promise<void> {
  const epoch = session.getEpoch();
  if (refreshInFlight?.epoch === epoch) return refreshInFlight.promise;
  const promise = refreshOnce(epoch).finally(() => {
    if (refreshInFlight?.promise === promise) refreshInFlight = null;
  });
  refreshInFlight = { epoch, promise };
  return promise;
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

/**
 * Ask the server to end the login session behind `refreshToken`. Best effort: it never throws.
 * The caller has already forgotten the session locally, so when the server cannot be reached the
 * token simply stays valid until it expires, as it did before logout reached the server.
 */
export async function revokeSession(refreshToken: string): Promise<void> {
  try {
    await rawRequest<void>('/auth/logout', {
      method: 'POST',
      body: { refresh_token: refreshToken },
    });
  } catch {
    // Nothing to do: logging the error could only leak information, and the user is logged out here.
  }
}
