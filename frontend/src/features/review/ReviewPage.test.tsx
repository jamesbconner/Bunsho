import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Route, Routes } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { NextCard } from '../../api/endpoints';
import { session } from '../../auth/session';
import { makeKanaCard, makeKanjiCard, makeNextCard, makeVocabCard } from '../../test/fixtures';
import { renderWithProviders } from '../../test/render';
import { server } from '../../test/server';
import { FURIGANA_KEY } from './useFuriganaPreference';
import { ReviewPage } from './ReviewPage';

const COUNTS = {
  due: { kana: 0, kanji: 0, vocab: 0 },
  new_remaining: { kana: 0, kanji: 0, vocab: 0 },
};

/** Serve `GET /reviews/next` from a queue: every accepted answer moves on to the next entry. */
function serveReviews(queue: NextCard[], answerStatus = 200) {
  const posted: Record<string, unknown>[] = [];
  let index = 0;
  server.use(
    http.get('/api/v1/reviews/next', () =>
      HttpResponse.json(queue[Math.min(index, queue.length - 1)]),
    ),
    http.post('/api/v1/reviews/answer', async ({ request }) => {
      posted.push((await request.json()) as Record<string, unknown>);
      if (answerStatus !== 200) {
        // A 409 means the card was answered elsewhere, so the server has moved on.
        if (answerStatus === 409) index += 1;
        return HttpResponse.json({ detail: 'stale' }, { status: answerStatus });
      }
      index += 1;
      return HttpResponse.json(COUNTS);
    }),
  );
  return { posted };
}

function renderReview() {
  return renderWithProviders(
    <Routes>
      <Route path="/" element={<p>Dashboard</p>} />
      <Route path="/review" element={<ReviewPage />} />
      <Route path="/build" element={<p>Build page</p>} />
    </Routes>,
    { initialEntries: ['/review'] },
  );
}

describe('ReviewPage', () => {
  beforeEach(() => {
    session.clear();
    session.setTokens({ access_token: 'a1', refresh_token: 'r1', expires_in: 900 });
  });

  afterEach(() => {
    vi.useRealTimers();
    window.localStorage.clear();
  });

  it('shows the first card and the counts, then the next card after a grade', async () => {
    const user = userEvent.setup();
    const first = makeNextCard(makeKanaCard(), {
      counts: { ...COUNTS, due: { kana: 3, kanji: 2, vocab: 0 } },
    });
    const second = makeNextCard(makeKanjiCard());
    const { posted } = serveReviews([first, second]);
    renderReview();

    expect(await screen.findByText('あ')).toBeInTheDocument();
    expect(screen.getByText('5 due · 0 new available')).toBeInTheDocument();

    await user.keyboard(' ');
    await user.keyboard('3');

    expect(await screen.findByText('日')).toBeInTheDocument();
    expect(posted).toHaveLength(1);
    expect(posted[0]).toMatchObject({
      item_id: 'kana:あ',
      direction: 'glyph_to_sound',
      grade: 3,
      expected_last_review: null,
    });
  });

  it('sends the opaque expected_last_review exactly as received', async () => {
    const user = userEvent.setup();
    const token = '2026-09-19T09:30:00.123456+00:00';
    const { posted } = serveReviews([
      makeNextCard(makeVocabCard({ expected_last_review: token })),
      makeNextCard(null),
    ]);
    renderReview();
    await screen.findByRole('button', { name: 'Show answer' });
    await user.keyboard(' ');
    await user.click(screen.getByRole('button', { name: /^Easy/ }));
    await screen.findByText("You're done for now");
    expect(posted[0]).toMatchObject({ expected_last_review: token, grade: 4 });
  });

  it('measures how long the card was on screen and keeps it within the API limit', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-09-20T10:00:00Z'));
    const user = userEvent.setup();
    const { posted } = serveReviews([
      makeNextCard(makeKanaCard()),
      makeNextCard(
        makeKanaCard({ item_id: 'kana:い', expected_last_review: '2026-09-20T10:00:06Z' }),
      ),
      makeNextCard(null),
    ]);
    renderReview();
    await screen.findByRole('button', { name: 'Show answer' });

    vi.setSystemTime(new Date('2026-09-20T10:00:05.500Z'));
    await user.keyboard(' ');
    await user.keyboard('2');
    await waitFor(() => {
      expect(posted).toHaveLength(1);
    });
    expect(posted[0]?.duration_ms).toBe(5500);

    await screen.findByRole('button', { name: 'Show answer' });
    vi.setSystemTime(new Date('2026-09-20T13:00:00Z'));
    await user.keyboard(' ');
    await user.keyboard('3');
    await waitFor(() => {
      expect(posted).toHaveLength(2);
    });
    expect(posted[1]?.duration_ms).toBe(3_600_000);
  });

  it('sends one grade only, however many keys are pressed while it is being saved', async () => {
    const user = userEvent.setup();
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const posted: unknown[] = [];
    server.use(
      http.get('/api/v1/reviews/next', () => HttpResponse.json(makeNextCard(makeKanaCard()))),
      http.post('/api/v1/reviews/answer', async ({ request }) => {
        posted.push(await request.json());
        await gate;
        return HttpResponse.json(COUNTS);
      }),
    );
    renderReview();
    await screen.findByRole('button', { name: 'Show answer' });
    await user.keyboard(' ');
    await user.keyboard('3');
    await user.keyboard('3');
    await user.keyboard('1');
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^Good/ })).toBeDisabled();
    });
    expect(posted).toHaveLength(1);
    release();
  });

  it('loads the next card with a notice when the card changed elsewhere (409)', async () => {
    const user = userEvent.setup();
    const stale = makeNextCard(makeKanaCard());
    const fresh = makeNextCard(makeKanjiCard());
    serveReviews([stale, fresh], 409);
    renderReview();
    await screen.findByText('あ');
    await user.keyboard(' ');
    await user.keyboard('3');

    expect(
      await screen.findByText('That card changed elsewhere: loading the next one.'),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('日')).toBeInTheDocument();
    });
    expect(screen.queryByText("Couldn't save your answer")).not.toBeInTheDocument();
  });

  it('keeps the card and offers a retry when the answer could not be saved', async () => {
    const user = userEvent.setup();
    let calls = 0;
    server.use(
      http.get('/api/v1/reviews/next', () => HttpResponse.json(makeNextCard(makeKanaCard()))),
      http.post('/api/v1/reviews/answer', () => {
        calls += 1;
        return calls === 1 ? HttpResponse.error() : HttpResponse.json(COUNTS);
      }),
    );
    renderReview();
    await screen.findByText('あ');
    await user.keyboard(' ');
    await user.keyboard('3');

    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText("Couldn't save your answer")).toBeInTheDocument();
    expect(screen.getByText('あ')).toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'Grade your answer' })).toBeInTheDocument();

    await user.click(within(alert).getByRole('button', { name: 'Try again' }));
    await waitFor(() => {
      expect(calls).toBe(2);
    });
    await waitFor(() => {
      expect(screen.queryByText("Couldn't save your answer")).not.toBeInTheDocument();
    });
  });

  it('shows no live grade buttons when the load after a grade fails, and recovers', async () => {
    const user = userEvent.setup();
    let loads = 0;
    server.use(
      http.get('/api/v1/reviews/next', () => {
        loads += 1;
        if (loads === 1) return HttpResponse.json(makeNextCard(makeKanaCard()));
        if (loads === 2) return HttpResponse.json({ detail: 'boom' }, { status: 500 });
        return HttpResponse.json(makeNextCard(makeKanjiCard()));
      }),
      http.post('/api/v1/reviews/answer', () => HttpResponse.json(COUNTS)),
    );
    renderReview();
    await screen.findByText('あ');
    await user.keyboard(' ');
    await user.keyboard('3');

    // The graded card must not stay on screen with live buttons: grading it again would be a 409.
    expect(await screen.findByText("Couldn't load the next card")).toBeInTheDocument();
    expect(screen.queryByRole('group', { name: 'Grade your answer' })).toBeNull();
    expect(screen.queryByText('あ')).toBeNull();

    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('日')).toBeInTheDocument();
  });

  it('leaves the status empty after a failed save, while the alert announces it', async () => {
    const user = userEvent.setup();
    serveReviews([makeNextCard(makeKanaCard())], 500);
    renderReview();
    const status = screen.getByRole('status');
    await screen.findByText('あ');
    await user.keyboard(' ');
    expect(status).toHaveTextContent('Answer shown');
    await user.keyboard('3');

    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't save your answer");
    expect(status).toBeEmptyDOMElement();
    expect(screen.getByRole('status')).toBe(status);
  });

  it('treats a 409 on the resend like a 409 on the first send', async () => {
    const user = userEvent.setup();
    const posted: unknown[] = [];
    let index = 0;
    const queue = [makeNextCard(makeKanaCard()), makeNextCard(makeKanjiCard())];
    server.use(
      http.get('/api/v1/reviews/next', () => HttpResponse.json(queue[index])),
      http.post('/api/v1/reviews/answer', async ({ request }) => {
        posted.push(await request.json());
        if (posted.length === 1) return HttpResponse.error();
        // The first POST was processed but its response was lost: the resend is now stale.
        index = 1;
        return HttpResponse.json({ detail: 'stale' }, { status: 409 });
      }),
    );
    renderReview();
    await screen.findByText('あ');
    await user.keyboard(' ');
    await user.keyboard('3');

    const alert = await screen.findByRole('alert');
    await user.click(within(alert).getByRole('button', { name: 'Try again' }));

    expect(
      await screen.findByText('That card changed elsewhere: loading the next one.'),
    ).toBeInTheDocument();
    expect(await screen.findByText('日')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByText("Couldn't save your answer")).not.toBeInTheDocument();
    });
    expect(posted).toHaveLength(2);
    expect(posted[1]).toEqual(posted[0]);
  });

  it('sends the person to the Build screen when the content is not built (503)', async () => {
    server.use(
      http.get('/api/v1/reviews/next', () =>
        HttpResponse.json({ detail: 'content is not built' }, { status: 503 }),
      ),
    );
    renderReview();
    expect(await screen.findByText('Nothing to study yet')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Build your content' })).toHaveAttribute(
      'href',
      '/build',
    );
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
    renderReview();
    expect(await screen.findByText("Couldn't load the next card")).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('あ')).toBeInTheDocument();
  });

  it('shows the finished state with the next due time and a link back', async () => {
    serveReviews([makeNextCard(null, { next_due_at: '2026-09-21T08:30:00Z' })]);
    renderReview();
    expect(await screen.findByText("You're done for now")).toBeInTheDocument();
    expect(screen.getByText(/Next card due .*2026/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back to the dashboard' })).toHaveAttribute(
      'href',
      '/',
    );
    expect(
      screen.getByRole('link', { name: 'Change your daily limits in Settings' }),
    ).toHaveAttribute('href', '/settings');
  });

  it('leaves out the next due time when nothing is scheduled', async () => {
    serveReviews([makeNextCard(null)]);
    renderReview();
    expect(await screen.findByText("You're done for now")).toBeInTheDocument();
    expect(screen.queryByText(/Next card due/)).not.toBeInTheDocument();
  });

  it('remembers the furigana switch and shows readings on the front when it is on', async () => {
    const user = userEvent.setup();
    serveReviews([makeNextCard(makeVocabCard())]);
    const { container } = renderReview();
    await screen.findByRole('button', { name: 'Show answer' });
    expect(container.querySelector('ruby')).toBeNull();

    await user.click(screen.getByRole('switch', { name: 'Show furigana' }));
    expect(container.querySelector('ruby')).not.toBeNull();
    expect(window.localStorage.getItem(FURIGANA_KEY)).toBe('true');
  });

  it('announces the state through one persistent status region', async () => {
    const user = userEvent.setup();
    serveReviews([makeNextCard(makeKanaCard()), makeNextCard(null)]);
    renderReview();
    const status = screen.getByRole('status');
    expect(status).toBeEmptyDOMElement();

    await waitFor(() => {
      expect(status).toHaveTextContent('Card shown');
    });
    await user.keyboard(' ');
    expect(status).toHaveTextContent('Answer shown');
    expect(screen.getByRole('status')).toBe(status);
    await user.keyboard('3');
    await waitFor(() => {
      expect(status).toHaveTextContent('Nothing due right now');
    });
  });
});
