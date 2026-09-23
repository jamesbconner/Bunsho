import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { server } from '../test/server';
import { endpoints } from './endpoints';
import { ApiError, NetworkError } from './errors';

const OK_BODY = {
  status: 'ok',
  version: '1.2.0',
  components: { database: { status: 'ok', detail: 'reachable', latency_ms: 1.5 } },
};
const ERROR_BODY = {
  status: 'error',
  version: '1.2.0',
  components: { content: { status: 'error', detail: 'content.db is missing', latency_ms: 0.2 } },
};

describe('endpoints.health', () => {
  it('returns the body of a healthy answer', async () => {
    server.use(http.get('/api/v1/health', () => HttpResponse.json(OK_BODY)));
    await expect(endpoints.health()).resolves.toEqual(OK_BODY);
  });

  it('returns the body of a 503 as data, so a failing component can be shown', async () => {
    server.use(http.get('/api/v1/health', () => HttpResponse.json(ERROR_BODY, { status: 503 })));
    await expect(endpoints.health()).resolves.toEqual(ERROR_BODY);
  });

  it('does not treat a proxy error page (503, not JSON) as a health report', async () => {
    server.use(
      http.get('/api/v1/health', () =>
        HttpResponse.text('<html>Service Unavailable</html>', {
          status: 503,
          headers: { 'Content-Type': 'text/html' },
        }),
      ),
    );
    const failure = await endpoints.health().catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(ApiError);
    expect((failure as ApiError).status).toBe(503);
  });

  it('does not treat a 503 JSON body of the wrong shape as a health report', async () => {
    server.use(
      http.get('/api/v1/health', () => HttpResponse.json({ detail: 'busy' }, { status: 503 })),
    );
    await expect(endpoints.health()).rejects.toBeInstanceOf(ApiError);
  });

  it('still fails on other error statuses', async () => {
    server.use(http.get('/api/v1/health', () => HttpResponse.json(ERROR_BODY, { status: 500 })));
    await expect(endpoints.health()).rejects.toMatchObject({ status: 500 });
  });

  it('reports an unreachable server as a network error', async () => {
    server.use(http.get('/api/v1/health', () => HttpResponse.error()));
    await expect(endpoints.health()).rejects.toBeInstanceOf(NetworkError);
  });
});
