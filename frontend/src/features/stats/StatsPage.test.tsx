import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Route, Routes } from 'react-router';
import { beforeEach, describe, expect, it } from 'vitest';

import type { StatsSummary } from '../../api/endpoints';
import { session } from '../../auth/session';
import { makeDailyReviews, makeStatsSummary } from '../../test/fixtures';
import { renderWithProviders } from '../../test/render';
import { server } from '../../test/server';
import { StatsPage } from './StatsPage';

function serve(stats: StatsSummary) {
  server.use(http.get('/api/v1/stats/summary', () => HttpResponse.json(stats)));
}

function renderStats() {
  return renderWithProviders(
    <Routes>
      <Route path="/" element={<StatsPage />} />
      <Route path="/settings" element={<p>Build page</p>} />
    </Routes>,
  );
}

describe('StatsPage', () => {
  beforeEach(() => {
    session.clear();
    session.setTokens({ access_token: 'a1', refresh_token: 'r1', expires_in: 900 });
  });

  it('shows today, retention, the chart, the cards and the progress by level', async () => {
    serve(makeStatsSummary());
    const { container } = renderStats();

    expect(await screen.findByRole('heading', { name: 'Statistics' })).toBeInTheDocument();
    const reviewed = screen.getByText('Reviewed today').parentElement;
    expect(reviewed).toHaveTextContent('42');
    const introduced = screen.getByText('New cards today').parentElement;
    expect(introduced).toHaveTextContent('16');
    expect(introduced).toHaveTextContent('5 kana, 3 kanji, 8 vocabulary');
    const retention = screen.getByText('Retention, last 30 days').parentElement;
    expect(retention).toHaveTextContent('87.7%');

    expect(screen.getByRole('heading', { name: 'Last 30 days' })).toBeInTheDocument();
    const chart = container.querySelector('.mantine-BarChart-root');
    expect(chart).not.toBeNull();
    expect(chart?.closest('[aria-hidden="true"]')).not.toBeNull();
    expect(screen.getByRole('heading', { name: 'Your cards' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Progress by level' })).toBeInTheDocument();
  });

  it('gives the numbers behind the chart in a table for screen readers', async () => {
    serve(makeStatsSummary());
    renderStats();
    const table = await screen.findByRole('table', { name: 'Reviews per day, last 30 days' });
    const rows = within(table).getAllByRole('row');
    expect(rows).toHaveLength(31);
    expect(within(rows[1] as HTMLElement).getByText('0')).toBeInTheDocument();
    expect(rows[30]).toHaveTextContent(/Sep(tember)? 20/);
    expect(rows[30]).toHaveTextContent('58');
  });

  it('says so instead of drawing an empty chart', async () => {
    serve(
      makeStatsSummary({
        daily_reviews: makeDailyReviews().map((day) => ({ ...day, reviews: 0 })),
      }),
    );
    const { container } = renderStats();
    expect(await screen.findByText(/No reviews yet/)).toBeInTheDocument();
    expect(container.querySelector('.mantine-BarChart-root')).toBeNull();
    expect(
      screen.queryByRole('table', { name: 'Reviews per day, last 30 days' }),
    ).not.toBeInTheDocument();
  });

  it('explains a missing retention figure', async () => {
    serve(makeStatsSummary({ retention_30d: null }));
    renderStats();
    const retention = (await screen.findByText('Retention, last 30 days')).parentElement;
    expect(retention).toHaveTextContent('Not enough reviews yet');
  });

  it('lists the cards of each type by state', async () => {
    serve(makeStatsSummary());
    renderStats();
    const table = await screen.findByRole('table', { name: 'Cards by type and state' });
    const kanji = within(table).getByRole('row', { name: /Kanji/ });
    expect(kanji).toHaveTextContent('2,109');
    expect(kanji).toHaveTextContent('30');
    expect(kanji).toHaveTextContent('200');
    expect(kanji).toHaveTextContent('5');
    expect(within(table).getByRole('row', { name: /Vocabulary/ })).toHaveTextContent('15,468');
    expect(within(table).getByRole('row', { name: /Kana/ })).toHaveTextContent('416');
  });

  it('shows progress per level with the numbers beside the bar and skips empty levels', async () => {
    serve(makeStatsSummary());
    renderStats();
    const kanji = await screen.findByRole('region', { name: 'Kanji progress by level' });
    expect(within(kanji).getByText('N5')).toBeInTheDocument();
    expect(within(kanji).getByText('180 in review, 300 of 960 introduced')).toBeInTheDocument();
    expect(within(kanji).getByText('5 in review, 20 of 704 introduced')).toBeInTheDocument();
    expect(within(kanji).queryByText('N3')).not.toBeInTheDocument();
    const vocab = screen.getByRole('region', { name: 'Vocabulary progress by level' });
    expect(within(vocab).getByText('500 in review, 700 of 1,334 introduced')).toBeInTheDocument();
  });

  it('leaves out a type that has no levels with cards', async () => {
    serve(makeStatsSummary({ by_level: [] }));
    renderStats();
    await screen.findByRole('heading', { name: 'Progress by level' });
    expect(screen.queryByRole('region', { name: /progress by level/ })).not.toBeInTheDocument();
  });

  it('links to the Build screen when the content is not built (503)', async () => {
    server.use(
      http.get('/api/v1/stats/summary', () =>
        HttpResponse.json({ detail: 'content is not built' }, { status: 503 }),
      ),
    );
    renderStats();
    expect(await screen.findByText('Nothing to show yet')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Build your content' })).toHaveAttribute(
      'href',
      '/settings?tab=system',
    );
  });

  it('explains a failed load and can try again', async () => {
    const user = userEvent.setup();
    let calls = 0;
    server.use(
      http.get('/api/v1/stats/summary', () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json({ detail: 'boom' }, { status: 500 })
          : HttpResponse.json(makeStatsSummary());
      }),
    );
    renderStats();
    expect(await screen.findByText("Couldn't load your statistics")).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('heading', { name: 'Statistics' })).toBeInTheDocument();
  });
});
