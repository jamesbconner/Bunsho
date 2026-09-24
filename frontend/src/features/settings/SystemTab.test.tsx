import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { session } from '../../auth/session';
import { makeBuildStatus } from '../../test/fixtures';
import { renderWithProviders } from '../../test/render';
import { server } from '../../test/server';
import { SystemTab } from './SystemTab';

const BUILD = '/api/v1/admin/content/build';

function serve({ built = true }: { built?: boolean } = {}) {
  const posted: unknown[] = [];
  server.use(
    http.get('/api/v1/health', () =>
      HttpResponse.json({
        status: 'ok',
        version: '1.2.0',
        components: { database: { status: 'ok', detail: 'reachable', latency_ms: 1 } },
      }),
    ),
    http.get('/api/v1/content/summary', () =>
      HttpResponse.json({
        built,
        kana: built ? 208 : 0,
        kanji: 0,
        vocab: 0,
        unleveled_kanji: 0,
        kanji_by_level: {},
        vocab_by_level: {},
        meta: {},
      }),
    ),
    http.get('/api/v1/admin/config-check', () =>
      HttpResponse.json({
        ok: false,
        checks: [
          { name: 'deck_present', ok: false, detail: 'deck not found' },
          { name: 'jamdict_available', ok: true, detail: 'jamdict-data-fix' },
        ],
      }),
    ),
    http.get(BUILD, () => HttpResponse.json({ detail: 'no build has run yet' }, { status: 404 })),
    http.post(BUILD, async ({ request }) => {
      posted.push(await request.json());
      return HttpResponse.json(makeBuildStatus(), { status: 202 });
    }),
  );
  return posted;
}

describe('SystemTab', () => {
  beforeEach(() => {
    session.clear();
    session.setTokens({ access_token: 'a1', refresh_token: 'r1', expires_in: 900 });
  });

  it('shows the server, content, environment and build blocks in that order', async () => {
    serve();
    renderWithProviders(<SystemTab />);
    // Every block shows a skeleton until its request answers; wait for all of them.
    await screen.findByRole('region', { name: 'Server' });
    await screen.findByRole('region', { name: 'Content' });
    await screen.findByRole('region', { name: 'Environment' });
    const headings = screen
      .getAllByRole('heading', { level: 3 })
      .map((heading) => heading.textContent);
    expect(headings).toEqual(['Server', 'Content', 'Environment', 'Build']);
  });

  it('shows what the server found in the environment, problems included', async () => {
    serve();
    renderWithProviders(<SystemTab />);
    const region = await screen.findByRole('region', { name: 'Environment' });
    expect(await within(region).findByText('deck not found')).toBeInTheDocument();
    expect(within(region).getByText('Vocabulary deck')).toBeInTheDocument();
    expect(within(region).getByText('Problem')).toBeInTheDocument();
    expect(within(region).getByText('OK')).toBeInTheDocument();
  });

  it('welcomes a first run at the top, before the other blocks', async () => {
    serve({ built: false });
    renderWithProviders(<SystemTab />);
    const notice = await screen.findByText('First run');
    const server_ = await screen.findByRole('region', { name: 'Server' });
    expect(notice.compareDocumentPosition(server_) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('does not show the first-run notice once content is built', async () => {
    serve({ built: true });
    renderWithProviders(<SystemTab />);
    await screen.findByText('Built');
    expect(screen.queryByText('First run')).not.toBeInTheDocument();
  });

  it('starts a build from the tab', async () => {
    const posted = serve({ built: false });
    renderWithProviders(<SystemTab />);
    await userEvent.click(await screen.findByRole('button', { name: 'Build content' }));
    await waitFor(() => {
      expect(posted).toEqual([{ dry_run: false }]);
    });
  });
});
