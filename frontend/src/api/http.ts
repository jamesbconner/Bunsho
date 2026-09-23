import { FetchError, ofetch } from 'ofetch';

import { toClientError } from './errors';

/** Absolute URL of an API path. Node's fetch (used by the tests) cannot resolve relative URLs. */
export function apiUrl(path: string): string {
  return new URL(`/api/v1${path}`, window.location.origin).toString();
}

/** Absolute ws:// or wss:// URL of an API WebSocket path. */
export function wsUrl(path: string): string {
  const url = new URL(`/api/v1${path}`, window.location.origin);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return url.toString();
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT';
  body?: Record<string, unknown>;
  headers?: Record<string, string>;
}

/** One HTTP call with JSON in and out. No authentication and no retries; errors are normalized. */
export async function rawRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  try {
    return await ofetch<T>(apiUrl(path), { ...options, retry: 0 });
  } catch (error) {
    throw toClientError(error);
  }
}

/**
 * Like `rawRequest`, but an error response with one of `statuses` whose body passes `isBody` is
 * returned as data. `GET /health` answers 503 with its full report when a dependency is down; that
 * report is what the caller wants. A body that fails `isBody` (a proxy's HTML error page, say) is
 * still an error.
 */
export async function rawRequestAllowing<T>(
  path: string,
  statuses: readonly number[],
  isBody: (data: unknown) => data is T,
): Promise<T> {
  try {
    return await ofetch<T>(apiUrl(path), { retry: 0 });
  } catch (error) {
    if (
      error instanceof FetchError &&
      error.response !== undefined &&
      statuses.includes(error.response.status)
    ) {
      const data: unknown = error.data;
      if (isBody(data)) return data;
    }
    throw toClientError(error);
  }
}
