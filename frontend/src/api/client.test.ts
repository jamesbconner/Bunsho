import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { session } from '../auth/session';
import { server } from '../test/server';
import { ensureAccessToken, refreshSession, request } from './client';
import { ApiError, NetworkError } from './errors';

const SUMMARY = '/api/v1/content/summary';
const REFRESH = '/api/v1/auth/refresh';

function pair(n: number) {
  return {
    access_token: `access-${String(n)}`,
    refresh_token: `refresh-${String(n)}`,
    expires_in: 900,
  };
}

function refreshHandler(counter: { calls: number }) {
  return http.post(REFRESH, async ({ request: incoming }) => {
    counter.calls += 1;
    const body = (await incoming.json()) as { refresh_token: string };
    return body.refresh_token === 'refresh-1'
      ? HttpResponse.json({ ...pair(2), token_type: 'bearer' })
      : HttpResponse.json({ detail: 'Invalid or expired refresh token' }, { status: 401 });
  });
}

describe('request', () => {
  beforeEach(() => {
    session.clear();
    session.setTokens(pair(1));
  });

  it('attaches the bearer token', async () => {
    let seen: string | null = null;
    server.use(
      http.get(SUMMARY, ({ request: incoming }) => {
        seen = incoming.headers.get('Authorization');
        return HttpResponse.json({ ok: true });
      }),
    );
    await expect(request('/content/summary')).resolves.toEqual({ ok: true });
    expect(seen).toBe('Bearer access-1');
  });

  it('on a 401 refreshes the session once and retries the call once', async () => {
    const refresh = { calls: 0 };
    server.use(
      refreshHandler(refresh),
      http.get(SUMMARY, ({ request: incoming }) =>
        incoming.headers.get('Authorization') === 'Bearer access-2'
          ? HttpResponse.json({ ok: true })
          : HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 }),
      ),
    );
    await expect(request('/content/summary')).resolves.toEqual({ ok: true });
    expect(refresh.calls).toBe(1);
    expect(session.getRefreshToken()).toBe('refresh-2');
  });

  it('shares one refresh between concurrent calls that all get a 401', async () => {
    const refresh = { calls: 0 };
    server.use(
      refreshHandler(refresh),
      http.get(SUMMARY, ({ request: incoming }) =>
        incoming.headers.get('Authorization') === 'Bearer access-2'
          ? HttpResponse.json({ ok: true })
          : HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 }),
      ),
    );
    const results = await Promise.all([
      request('/content/summary'),
      request('/content/summary'),
      request('/content/summary'),
    ]);
    expect(results).toHaveLength(3);
    expect(refresh.calls).toBe(1);
  });

  it('refreshes first when the access token is about to expire', async () => {
    session.setTokens({ ...pair(1), expires_in: 10 });
    const refresh = { calls: 0 };
    server.use(
      refreshHandler(refresh),
      http.get(SUMMARY, () => HttpResponse.json({ ok: true })),
    );
    await request('/content/summary');
    expect(refresh.calls).toBe(1);
  });

  it('ends the session when the refresh token is rejected', async () => {
    const expired = vi.fn();
    session.onExpired(expired);
    session.setTokens({ ...pair(9) }); // refresh-9 is unknown to the server
    server.use(
      refreshHandler({ calls: 0 }),
      http.get(SUMMARY, () => HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })),
    );
    await expect(request('/content/summary')).rejects.toMatchObject({ status: 401 });
    expect(expired).toHaveBeenCalledTimes(1);
    expect(session.getRefreshToken()).toBeNull();
  });

  it('ends the session once, without calling the API, when the pre-flight refresh is rejected', async () => {
    const expired = vi.fn();
    session.onExpired(expired);
    session.setTokens({ ...pair(9), expires_in: 10 }); // about to expire; refresh-9 is unknown
    const refresh = { calls: 0 };
    let apiCalls = 0;
    server.use(
      refreshHandler(refresh),
      http.get(SUMMARY, () => {
        apiCalls += 1;
        return HttpResponse.json({ ok: true });
      }),
    );
    await expect(request('/content/summary')).rejects.toMatchObject({ status: 401 });
    expect(expired).toHaveBeenCalledTimes(1);
    expect(refresh.calls).toBe(1);
    expect(apiCalls).toBe(0);
  });

  it('ends the session once, without calling the API, when there is no refresh token', async () => {
    const expired = vi.fn();
    session.clear();
    session.onExpired(expired);
    let apiCalls = 0;
    server.use(
      http.get(SUMMARY, () => {
        apiCalls += 1;
        return HttpResponse.json({ ok: true });
      }),
    );
    await expect(request('/content/summary')).rejects.toMatchObject({ status: 401 });
    expect(expired).toHaveBeenCalledTimes(1);
    expect(apiCalls).toBe(0);
  });

  it('does not end the session when the server cannot be reached during a refresh', async () => {
    const expired = vi.fn();
    session.onExpired(expired);
    session.setTokens({ ...pair(1), expires_in: 10 });
    server.use(http.post(REFRESH, () => HttpResponse.error()));
    await expect(request('/content/summary')).rejects.toBeInstanceOf(NetworkError);
    expect(expired).not.toHaveBeenCalled();
    expect(session.getRefreshToken()).toBe('refresh-1');
  });

  it('does not retry errors other than 401', async () => {
    let calls = 0;
    server.use(
      http.get(SUMMARY, () => {
        calls += 1;
        return HttpResponse.json({ detail: 'busy' }, { status: 503 });
      }),
    );
    await expect(request('/content/summary')).rejects.toBeInstanceOf(ApiError);
    expect(calls).toBe(1);
  });

  it('gives up after one retry when the retried call is rejected again', async () => {
    let calls = 0;
    server.use(
      refreshHandler({ calls: 0 }),
      http.get(SUMMARY, () => {
        calls += 1;
        return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 });
      }),
    );
    await expect(request('/content/summary')).rejects.toMatchObject({ status: 401 });
    expect(calls).toBe(2);
  });
});

describe('sessions without a refresh token', () => {
  beforeEach(() => {
    session.clear();
  });

  it('cannot refresh: the session is reported expired', async () => {
    const expired = vi.fn();
    session.onExpired(expired);
    await expect(refreshSession()).rejects.toMatchObject({ status: 401 });
    expect(expired).toHaveBeenCalledTimes(1);
  });

  it('ensureAccessToken returns a fresh token without calling the server', async () => {
    session.setTokens(pair(1));
    await expect(ensureAccessToken()).resolves.toBe('access-1');
  });
});
