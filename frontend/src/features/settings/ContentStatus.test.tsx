import { screen, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { session } from '../../auth/session';
import { renderWithProviders } from '../../test/render';
import { server } from '../../test/server';
import { ContentStatus } from './ContentStatus';

function serveSummary(built: boolean) {
  server.use(
    http.get('/api/v1/content/summary', () =>
      HttpResponse.json({
        built,
        kana: built ? 208 : 0,
        kanji: built ? 3088 : 0,
        vocab: built ? 7734 : 0,
        unleveled_kanji: 0,
        kanji_by_level: {},
        vocab_by_level: {},
        meta: {},
      }),
    ),
  );
}

describe('ContentStatus', () => {
  beforeEach(() => {
    session.clear();
    session.setTokens({ access_token: 'a1', refresh_token: 'r1', expires_in: 900 });
  });

  it('shows the counts of built content', async () => {
    serveSummary(true);
    renderWithProviders(<ContentStatus />);
    const region = await screen.findByRole('region', { name: 'Content' });
    expect(await within(region).findByText('Built')).toBeInTheDocument();
    expect(within(region).getByText('208')).toBeInTheDocument();
    expect(within(region).getByText('3,088')).toBeInTheDocument();
    expect(within(region).getByText('7,734')).toBeInTheDocument();
  });

  it('says so when nothing is built yet, without counts', async () => {
    serveSummary(false);
    renderWithProviders(<ContentStatus />);
    const region = await screen.findByRole('region', { name: 'Content' });
    expect(await within(region).findByText('Not built')).toBeInTheDocument();
    expect(within(region).queryByText('Kanji')).not.toBeInTheDocument();
  });

  it('explains a failed load and can try again', async () => {
    server.use(http.get('/api/v1/content/summary', () => HttpResponse.error()));
    renderWithProviders(<ContentStatus />);
    expect(await screen.findByText("Couldn't load the content status")).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });
});
