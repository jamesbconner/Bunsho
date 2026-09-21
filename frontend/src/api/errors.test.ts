import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { server } from '../test/server';
import { ApiError, messageFor, NetworkError } from './errors';
import { rawRequest } from './http';

describe('error normalization', () => {
  it('maps an HTTP error to an ApiError with a string detail', async () => {
    server.use(http.get('/api/v1/x', () => HttpResponse.json({ detail: 'Nope' }, { status: 404 })));
    await expect(rawRequest('/x')).rejects.toMatchObject({
      name: 'ApiError',
      status: 404,
      detail: 'Nope',
    });
  });

  it('maps a 422 list to per-field messages (first message per field)', async () => {
    server.use(
      http.post('/api/v1/x', () =>
        HttpResponse.json(
          {
            detail: [
              { loc: ['body', 'username'], msg: 'Field required', type: 'missing' },
              { loc: ['body', 'username'], msg: 'Second message', type: 'x' },
              { loc: ['body', 'password'], msg: 'Too short', type: 'string_too_short' },
            ],
          },
          { status: 422 },
        ),
      ),
    );
    const error = (await rawRequest('/x', { method: 'POST', body: {} }).catch(
      (caught: unknown) => caught,
    )) as ApiError;
    expect(error.status).toBe(422);
    expect(error.fieldErrors).toEqual({ username: 'Field required', password: 'Too short' });
  });

  it('reads Retry-After from a 429', async () => {
    server.use(
      http.post('/api/v1/x', () =>
        HttpResponse.json(
          { detail: 'slow down' },
          { status: 429, headers: { 'Retry-After': '7' } },
        ),
      ),
    );
    await expect(rawRequest('/x', { method: 'POST', body: {} })).rejects.toMatchObject({
      status: 429,
      retryAfterSeconds: 7,
    });
  });

  it('maps a connection failure to a NetworkError', async () => {
    server.use(http.get('/api/v1/x', () => HttpResponse.error()));
    await expect(rawRequest('/x')).rejects.toBeInstanceOf(NetworkError);
  });

  it('does not retry on its own', async () => {
    let calls = 0;
    server.use(
      http.get('/api/v1/x', () => {
        calls += 1;
        return HttpResponse.json({ detail: 'busy' }, { status: 503 });
      }),
    );
    await expect(rawRequest('/x')).rejects.toBeInstanceOf(ApiError);
    expect(calls).toBe(1);
  });
});

describe('messageFor', () => {
  it('never shows raw status codes', () => {
    const cases: [unknown, RegExp][] = [
      [new NetworkError(), /can't reach the server/i],
      [new ApiError(401, 'x'), /session has expired/i],
      [new ApiError(409, 'A build is already running'), /already running/i],
      [new ApiError(422, 'x'), /invalid/i],
      [new ApiError(429, 'x', {}, 7), /7 seconds/],
      [new ApiError(429, 'x'), /wait a moment/i],
      [new ApiError(503, 'x'), /isn't built yet/i],
      [new ApiError(500, 'boom'), /server had a problem/i],
      [new ApiError(404, 'Not found'), /not found/i],
      [new Error('weird'), /something went wrong/i],
    ];
    for (const [error, pattern] of cases) {
      const message = messageFor(error);
      expect(message).toMatch(pattern);
      expect(message).not.toMatch(/\b(401|409|422|429|500|503)\b/);
    }
  });
});
