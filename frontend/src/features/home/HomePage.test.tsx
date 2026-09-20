import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Route, Routes } from 'react-router';
import { beforeEach, describe, expect, it } from 'vitest';

import { session } from '../../auth/session';
import { renderWithProviders } from '../../test/render';
import { server } from '../../test/server';
import { HomePage } from './HomePage';

const BUILT = {
  built: true,
  kana: 208,
  kanji: 3088,
  vocab: 7734,
  unleveled_kanji: 979,
  kanji_by_level: { N5: 480, N4: 352, N3: 544, N2: 357, N1: 376 },
  vocab_by_level: { N5: 667, N4: 630, N3: 1647, N2: 1737, N1: 3053 },
  meta: {},
};

function renderHome() {
  return renderWithProviders(
    <Routes>
      <Route index element={<HomePage />} />
      <Route path="build" element={<p>Build page</p>} />
    </Routes>,
  );
}

describe('HomePage', () => {
  beforeEach(() => {
    session.clear();
    session.setTokens({ access_token: 'a1', refresh_token: 'r1', expires_in: 900 });
  });

  it('shows the totals and the per-level table of built content', async () => {
    server.use(http.get('/api/v1/content/summary', () => HttpResponse.json(BUILT)));
    renderHome();
    expect(await screen.findByRole('heading', { name: 'Your content' })).toBeInTheDocument();
    expect(screen.getByText('208')).toBeInTheDocument();
    expect(screen.getByText('3,088')).toBeInTheDocument();
    expect(screen.getByText('7,734')).toBeInTheDocument();
    expect(screen.getByText('979 not in the JLPT vocabulary')).toBeInTheDocument();
    const table = screen.getByRole('table', { name: 'Items per JLPT level' });
    const n5 = within(table).getByRole('row', { name: /N5/ });
    expect(within(n5).getByText('667')).toBeInTheDocument();
    expect(within(n5).getByText('480')).toBeInTheDocument();
  });

  it('invites a first-time user to build the content', async () => {
    server.use(
      http.get('/api/v1/content/summary', () =>
        HttpResponse.json({
          ...BUILT,
          built: false,
          kana: 0,
          kanji: 0,
          vocab: 0,
          unleveled_kanji: 0,
          kanji_by_level: {},
          vocab_by_level: {},
        }),
      ),
    );
    renderHome();
    expect(await screen.findByText('Welcome to Bunshō')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('link', { name: 'Build your content' }));
    expect(screen.getByText('Build page')).toBeInTheDocument();
  });

  it('says what went wrong and lets the user try again', async () => {
    server.use(
      http.get('/api/v1/content/summary', () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    );
    renderHome();
    expect(await screen.findByText("Couldn't load the content summary")).toBeInTheDocument();
    expect(screen.getByText(/server had a problem/i)).toBeInTheDocument();

    server.use(http.get('/api/v1/content/summary', () => HttpResponse.json(BUILT)));
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('heading', { name: 'Your content' })).toBeInTheDocument();
  });
});
