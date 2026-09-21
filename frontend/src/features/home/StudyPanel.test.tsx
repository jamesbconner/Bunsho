import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Route, Routes } from 'react-router';
import { beforeEach, describe, expect, it } from 'vitest';

import { session } from '../../auth/session';
import { makeKanaCard, makeNextCard } from '../../test/fixtures';
import { renderWithProviders } from '../../test/render';
import { server } from '../../test/server';
import { StudyPanel } from './StudyPanel';

function renderPanel() {
  return renderWithProviders(
    <Routes>
      <Route index element={<StudyPanel />} />
      <Route path="review" element={<p>Review page</p>} />
    </Routes>,
  );
}

describe('StudyPanel', () => {
  beforeEach(() => {
    session.clear();
    session.setTokens({ access_token: 'a1', refresh_token: 'r1', expires_in: 900 });
  });

  it('shows what is due and what is new for each type, with a way to start', async () => {
    const user = userEvent.setup();
    const payload = makeNextCard(makeKanaCard(), {
      counts: {
        due: { kana: 4, kanji: 12, vocab: 30 },
        new_remaining: { kana: 20, kanji: 15, vocab: 0 },
      },
    });
    server.use(http.get('/api/v1/reviews/next', () => HttpResponse.json(payload)));
    renderPanel();

    expect(await screen.findByRole('heading', { name: 'Today' })).toBeInTheDocument();
    const kanji = screen.getByText('Kanji').closest('div');
    expect(kanji).not.toBeNull();
    expect(within(kanji as HTMLElement).getByText('12 due')).toBeInTheDocument();
    expect(within(kanji as HTMLElement).getByText('15 new available')).toBeInTheDocument();
    expect(screen.getByText('30 due')).toBeInTheDocument();

    await user.click(screen.getByRole('link', { name: 'Study now' }));
    expect(screen.getByText('Review page')).toBeInTheDocument();
  });

  it('says nothing is due, with the next due time, instead of offering to study', async () => {
    server.use(
      http.get('/api/v1/reviews/next', () =>
        HttpResponse.json(makeNextCard(null, { next_due_at: '2026-09-21T08:30:00Z' })),
      ),
    );
    renderPanel();
    expect(
      await screen.findByText(/Nothing due right now\. Next card due .*2026/),
    ).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Study now' })).not.toBeInTheDocument();
  });

  it('says nothing is due without a time when nothing is scheduled', async () => {
    server.use(http.get('/api/v1/reviews/next', () => HttpResponse.json(makeNextCard(null))));
    renderPanel();
    expect(await screen.findByText('Nothing due right now.')).toBeInTheDocument();
  });

  it('explains a failed load and can try again', async () => {
    const user = userEvent.setup();
    let calls = 0;
    server.use(
      http.get('/api/v1/reviews/next', () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json({ detail: 'boom' }, { status: 500 })
          : HttpResponse.json(makeNextCard(makeKanaCard()));
      }),
    );
    renderPanel();
    expect(await screen.findByText("Couldn't load your study queue")).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('link', { name: 'Study now' })).toBeInTheDocument();
  });
});
