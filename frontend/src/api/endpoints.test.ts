import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { session } from '../auth/session';
import { makeSettings, makeStatsSummary } from '../test/fixtures';
import { server } from '../test/server';
import { endpoints } from './endpoints';

const TASK = {
  task_id: 'abc 123',
  state: 'running',
  dry_run: false,
  started_at: '2026-09-20T12:00:00Z',
  finished_at: null,
  progress: { stage: 'import_deck', current: 0, total: 1 },
  report: null,
  error: null,
};

describe('endpoints', () => {
  beforeEach(() => {
    session.clear();
    session.setTokens({ access_token: 'a1', refresh_token: 'r1', expires_in: 900 });
  });

  it('reads the content summary and the environment checks', async () => {
    server.use(
      http.get('/api/v1/content/summary', () => HttpResponse.json({ built: false })),
      http.get('/api/v1/admin/config-check', () => HttpResponse.json({ ok: true, checks: [] })),
    );
    await expect(endpoints.contentSummary()).resolves.toEqual({ built: false });
    await expect(endpoints.configCheck()).resolves.toEqual({ ok: true, checks: [] });
  });

  it('starts a build with the dry-run flag in the body', async () => {
    const bodies: unknown[] = [];
    server.use(
      http.post('/api/v1/admin/content/build', async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(TASK, { status: 202 });
      }),
    );
    await endpoints.startBuild(true);
    await endpoints.startBuild(false);
    expect(bodies).toEqual([{ dry_run: true }, { dry_run: false }]);
  });

  it('treats "no build yet" (404) as null and passes other errors on', async () => {
    server.use(
      http.get('/api/v1/admin/content/build', () =>
        HttpResponse.json({ detail: 'no build has run yet' }, { status: 404 }),
      ),
    );
    await expect(endpoints.latestBuild()).resolves.toBeNull();

    server.use(
      http.get('/api/v1/admin/content/build', () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    );
    await expect(endpoints.latestBuild()).rejects.toMatchObject({ status: 500 });
  });

  it('reads the latest build and a build by id (the id is URL-encoded)', async () => {
    let requestedPath = '';
    server.use(
      http.get('/api/v1/admin/content/build', () => HttpResponse.json(TASK)),
      http.get('/api/v1/admin/content/build/:id', ({ request }) => {
        requestedPath = new URL(request.url).pathname;
        return HttpResponse.json(TASK);
      }),
    );
    await expect(endpoints.latestBuild()).resolves.toMatchObject({ task_id: 'abc 123' });
    await endpoints.getBuild('abc 123');
    expect(requestedPath).toBe('/api/v1/admin/content/build/abc%20123');
  });
  it('asks for the next card', async () => {
    const payload = {
      card: null,
      counts: {
        due: { kana: 0, kanji: 0, vocab: 0 },
        new_remaining: { kana: 0, kanji: 0, vocab: 0 },
      },
      next_due_at: null,
    };
    server.use(http.get('/api/v1/reviews/next', () => HttpResponse.json(payload)));
    await expect(endpoints.nextReview()).resolves.toEqual(payload);
  });

  it('posts a grade exactly as given, including the opaque expected_last_review', async () => {
    const bodies: unknown[] = [];
    const counts = {
      due: { kana: 0, kanji: 1, vocab: 0 },
      new_remaining: { kana: 0, kanji: 0, vocab: 0 },
    };
    server.use(
      http.post('/api/v1/reviews/answer', async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(counts);
      }),
    );
    const answer = {
      item_id: 'kanji:日',
      direction: 'kanji_to_meaning',
      grade: 3,
      expected_last_review: '2026-09-19T08:00:00.123456Z',
      duration_ms: 4200,
    } as const;
    await expect(endpoints.answerReview(answer)).resolves.toEqual(counts);
    expect(bodies).toEqual([answer]);
  });
  it('reads the statistics summary', async () => {
    const payload = makeStatsSummary();
    server.use(http.get('/api/v1/stats/summary', () => HttpResponse.json(payload)));
    await expect(endpoints.statsSummary()).resolves.toEqual(payload);
  });

  it('reads the settings and replaces them with a PUT of the whole document', async () => {
    const bodies: unknown[] = [];
    const saved = makeSettings({ new_card_policy: 'pinned_levels', active_levels: ['N5', 'N4'] });
    server.use(
      http.get('/api/v1/settings', () => HttpResponse.json(makeSettings())),
      http.put('/api/v1/settings', async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(saved);
      }),
    );
    await expect(endpoints.getSettings()).resolves.toEqual(makeSettings());
    await expect(endpoints.updateSettings(saved)).resolves.toEqual(saved);
    expect(bodies).toEqual([saved]);
  });
});
