import { act, screen, waitFor, within } from '@testing-library/react';
import { type QueryClient } from '@tanstack/react-query';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import type { BuildStatus } from '../../api/endpoints';
import { queryKeys } from '../../api/queries';
import { session } from '../../auth/session';
import { makeBuildStatus, makeReport } from '../../test/fixtures';
import { renderWithProviders } from '../../test/render';
import { server } from '../../test/server';
import { BuildPage } from './BuildPage';

const BUILD = '/api/v1/admin/content/build';

const ALL_OK = {
  ok: true,
  checks: [
    { name: 'deck_present', ok: true, detail: 'resources/deck.apkg' },
    { name: 'deck_checksum', ok: true, detail: 'matches' },
    { name: 'data_dir_writable', ok: true, detail: '/data' },
    { name: 'jamdict_available', ok: true, detail: 'jamdict-data-fix' },
  ],
};

function summary(built: boolean) {
  return {
    built,
    kana: built ? 208 : 0,
    kanji: 0,
    vocab: 0,
    unleveled_kanji: 0,
    kanji_by_level: {},
    vocab_by_level: {},
    meta: {},
  };
}

interface Scenario {
  built?: boolean;
  latest?: BuildStatus | null;
  checks?: Record<string, unknown>;
}

/** Serve the read endpoints; returns the bodies received by POST /admin/content/build. */
function serve({ built = false, latest = null, checks = ALL_OK }: Scenario = {}) {
  const posted: unknown[] = [];
  server.use(
    http.get('/api/v1/content/summary', () => HttpResponse.json(summary(built))),
    http.get('/api/v1/admin/config-check', () => HttpResponse.json(checks)),
    http.get(BUILD, () =>
      latest === null
        ? HttpResponse.json({ detail: 'no build has run yet' }, { status: 404 })
        : HttpResponse.json(latest),
    ),
    http.post(BUILD, async ({ request }) => {
      posted.push(await request.json());
      return HttpResponse.json(makeBuildStatus(), { status: 202 });
    }),
  );
  return posted;
}

/** Wait until the latest-build query has answered, so a test can then set what the stream would. */
async function latestBuildLoaded(queryClient: QueryClient) {
  await waitFor(() => {
    expect(queryClient.getQueryState(queryKeys.latestBuild)?.status).toBe('success');
  });
}

describe('BuildPage', () => {
  beforeEach(() => {
    session.clear();
    session.setTokens({ access_token: 'a1', refresh_token: 'r1', expires_in: 900 });
  });

  it('shows what the server found in the environment, problems included', async () => {
    serve({
      checks: {
        ok: false,
        checks: [
          { name: 'deck_present', ok: false, detail: 'deck not found' },
          { name: 'jamdict_available', ok: true, detail: 'jamdict-data-fix' },
        ],
      },
    });
    renderWithProviders(<BuildPage />);
    expect(await screen.findByText('deck not found')).toBeInTheDocument();
    expect(screen.getByText('Vocabulary deck')).toBeInTheDocument();
    expect(screen.getByText('Problem')).toBeInTheDocument();
    expect(screen.getByText('OK')).toBeInTheDocument();
  });

  it('welcomes a first run and starts the first build without asking', async () => {
    const posted = serve({ built: false });
    renderWithProviders(<BuildPage />);
    expect(await screen.findByText('First run')).toBeInTheDocument();
    await userEvent.click(await screen.findByRole('button', { name: 'Build content' }));
    await waitFor(() => {
      expect(posted).toEqual([{ dry_run: false }]);
    });
    expect(await screen.findByText('Reading the vocabulary deck')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Build content' })).toBeDisabled();
  });

  it('asks before replacing built content, and does nothing on Cancel', async () => {
    const posted = serve({ built: true });
    renderWithProviders(<BuildPage />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Rebuild content' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/progress is kept/i)).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(posted).toEqual([]);

    await user.click(screen.getByRole('button', { name: 'Rebuild content' }));
    await user.click(
      within(await screen.findByRole('dialog')).getByRole('button', { name: 'Rebuild' }),
    );
    await waitFor(() => {
      expect(posted).toEqual([{ dry_run: false }]);
    });
  });

  it('starts a dry run without asking, even when content is built', async () => {
    const posted = serve({ built: true });
    renderWithProviders(<BuildPage />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole('switch', { name: /dry run/i }));
    await user.click(screen.getByRole('button', { name: 'Start dry run' }));
    await waitFor(() => {
      expect(posted).toEqual([{ dry_run: true }]);
    });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('says so when a build is already running (409)', async () => {
    serve({ built: false });
    server.use(
      http.post(BUILD, () =>
        HttpResponse.json(
          { detail: 'build 5f0c1e5e-6c47-4a51-9f3e-0d2a8f9a7b11 is already running' },
          { status: 409 },
        ),
      ),
    );
    renderWithProviders(<BuildPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Build content' }));
    expect(await screen.findByText('A build is already running.')).toBeInTheDocument();
    expect(screen.getByText('Could not start the build')).toBeInTheDocument();
    expect(screen.queryByText(/5f0c1e5e/)).not.toBeInTheDocument();
  });

  it('shows the progress of a build that is already running', async () => {
    serve({
      built: true,
      latest: makeBuildStatus({ progress: { stage: 'enrich_kanji', current: 1200, total: 3088 } }),
    });
    renderWithProviders(<BuildPage />);
    expect(await screen.findByText(/Looking up kanji details \(/)).toHaveTextContent(
      '1,200 of 3,088',
    );
    expect(screen.getByRole('button', { name: 'Rebuild content' })).toBeDisabled();
  });

  it('shows the message of a failed build', async () => {
    serve({
      latest: makeBuildStatus({ state: 'failed', progress: null, error: 'the deck is missing' }),
    });
    renderWithProviders(<BuildPage />);
    expect(await screen.findByText('The build failed')).toBeInTheDocument();
    expect(screen.getByText('the deck is missing')).toBeInTheDocument();
  });

  it('shows the report of a finished build', async () => {
    serve({
      built: true,
      latest: makeBuildStatus({ state: 'succeeded', progress: null, report: makeReport() }),
    });
    renderWithProviders(<BuildPage />);
    expect(await screen.findByText('Finished')).toBeInTheDocument();
    const table = screen.getByRole('table', { name: 'Items per JLPT level' });
    expect(within(table).getByText('3,053')).toBeInTheDocument(); // N1 vocabulary
    expect(screen.getByText(/7,734 vocabulary items/)).toBeInTheDocument();
    expect(screen.getByText(/Finished in 31\.4 seconds/)).toBeInTheDocument();
  });

  it('keeps other start failures on the shared readable message', async () => {
    serve({ built: false });
    server.use(http.post(BUILD, () => HttpResponse.error()));
    renderWithProviders(<BuildPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Build content' }));
    expect(await screen.findByText(/Can't reach the server/)).toBeInTheDocument();
  });

  it('announces the build state in one live region that is always on the page', async () => {
    serve({ built: true });
    const { queryClient } = renderWithProviders(<BuildPage />);
    await latestBuildLoaded(queryClient);
    const status = screen.getByRole('status');
    expect(status).toHaveAttribute('aria-live', 'polite');
    expect(status).toBeEmptyDOMElement();

    act(() => {
      queryClient.setQueryData(queryKeys.latestBuild, makeBuildStatus());
    });
    await waitFor(() => {
      expect(status).toHaveTextContent('Build running: Reading the vocabulary deck');
    });
    expect(status).not.toHaveTextContent('of');

    act(() => {
      queryClient.setQueryData(
        queryKeys.latestBuild,
        makeBuildStatus({ state: 'succeeded', progress: null, report: makeReport() }),
      );
    });
    expect(screen.getByRole('status')).toBe(status);
    await waitFor(() => {
      expect(status).toHaveTextContent('Build finished');
    });
  });

  it('announces a failure once, with its message, in the same live region', async () => {
    serve({ built: true });
    const { queryClient } = renderWithProviders(<BuildPage />);
    await latestBuildLoaded(queryClient);
    const status = screen.getByRole('status');
    act(() => {
      queryClient.setQueryData(
        queryKeys.latestBuild,
        makeBuildStatus({ state: 'failed', progress: null, error: 'the deck is missing' }),
      );
    });
    await waitFor(() => {
      expect(status).toHaveTextContent('Build failed: the deck is missing');
    });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('announces a dry run as such', async () => {
    serve({ built: true });
    const { queryClient } = renderWithProviders(<BuildPage />);
    await latestBuildLoaded(queryClient);
    act(() => {
      queryClient.setQueryData(
        queryKeys.latestBuild,
        makeBuildStatus({
          state: 'succeeded',
          dry_run: true,
          progress: null,
          report: makeReport(),
        }),
      );
    });
    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent('Dry run finished');
    });
  });

  it('marks a dry-run report as such', async () => {
    serve({
      latest: makeBuildStatus({
        state: 'succeeded',
        dry_run: true,
        progress: null,
        report: makeReport({ dry_run: true }),
      }),
    });
    renderWithProviders(<BuildPage />);
    expect(await screen.findByText('Dry run: nothing was written.')).toBeInTheDocument();
  });
});
