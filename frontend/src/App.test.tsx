import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { App } from './App';
import { REFRESH_TOKEN_KEY, session } from './auth/session';
import { FakeSocket } from './test/fakeSocket';
import { makeKanaCard, makeNextCard } from './test/fixtures';
import { server } from './test/server';

const TOKENS = { access_token: 'a2', refresh_token: 'r2', token_type: 'bearer', expires_in: 900 };
const SUMMARY = {
  built: true,
  kana: 208,
  kanji: 3088,
  vocab: 7734,
  unleveled_kanji: 979,
  kanji_by_level: { N5: 480, N4: 352, N3: 544, N2: 357, N1: 376 },
  vocab_by_level: { N5: 667, N4: 630, N3: 1647, N2: 1737, N1: 3053 },
  meta: {},
};

/** A FakeSocket that remembers every instance the app creates through the global WebSocket. */
class TrackedSocket extends FakeSocket {
  static instances: TrackedSocket[] = [];

  constructor(url: string) {
    super(url);
    TrackedSocket.instances.push(this);
  }
}

function rememberLogin() {
  window.localStorage.setItem(REFRESH_TOKEN_KEY, 'r1');
  server.use(
    http.post('/api/v1/auth/refresh', () => HttpResponse.json(TOKENS)),
    http.get('/api/v1/content/summary', () => HttpResponse.json(SUMMARY)),
    http.get('/api/v1/reviews/next', () => HttpResponse.json(makeNextCard(makeKanaCard()))),
    http.get('/api/v1/admin/config-check', () => HttpResponse.json({ ok: true, checks: [] })),
    http.get('/api/v1/admin/content/build', () =>
      HttpResponse.json({ detail: 'no build has run yet' }, { status: 404 }),
    ),
  );
}

function goTo(path: string) {
  window.history.pushState({}, '', path);
}

describe('App', () => {
  beforeEach(() => {
    session.clear();
    TrackedSocket.instances = [];
    vi.stubGlobal('WebSocket', TrackedSocket); // no real connection attempts from the live stream
    goTo('/');
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sends a visitor without a login to the login page', async () => {
    render(<App />);
    expect(await screen.findByLabelText('Username')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/login');
  });

  it('opens straight on the home page for a remembered login', async () => {
    rememberLogin();
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'Your content' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Bunshō/ })).toBeInTheDocument();
  });

  it('navigates to the build page and back', async () => {
    rememberLogin();
    render(<App />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole('link', { name: 'Build content' }));
    expect(await screen.findByRole('heading', { name: 'Content' })).toBeInTheDocument();
    expect(window.location.pathname).toBe('/build');
    await user.click(screen.getByRole('link', { name: 'Home' }));
    expect(await screen.findByRole('heading', { name: 'Your content' })).toBeInTheDocument();
  });

  it('starts a study session from the dashboard and finds its way back', async () => {
    rememberLogin();
    render(<App />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole('link', { name: 'Study now' }));
    expect(await screen.findByRole('heading', { name: 'Study' })).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: 'Show answer' })).toBeInTheDocument();
    expect(window.location.pathname).toBe('/review');
    await user.click(screen.getByRole('link', { name: 'Home' }));
    expect(await screen.findByRole('heading', { name: 'Today' })).toBeInTheDocument();
  });

  it('serves a deep link after the login is restored', async () => {
    rememberLogin();
    goTo('/build');
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'Content' })).toBeInTheDocument();
  });

  it('answers an unknown address with a not-found page', async () => {
    rememberLogin();
    goTo('/nothing/here');
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument();
  });

  it('logs out and forgets the remembered login', async () => {
    rememberLogin();
    render(<App />);
    await userEvent.click(await screen.findByRole('button', { name: 'Log out' }));
    expect(await screen.findByLabelText('Username')).toBeInTheDocument();
    expect(window.localStorage.getItem(REFRESH_TOKEN_KEY)).toBeNull();
    await waitFor(() => {
      expect(window.location.pathname).toBe('/login');
    });
  });

  it('lands on the login page with a notice when the live stream loses its session', async () => {
    rememberLogin();
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'Your content' })).toBeInTheDocument();
    await waitFor(() => {
      expect(TrackedSocket.instances).toHaveLength(1);
    });
    const socket = TrackedSocket.instances[0];
    if (socket === undefined) throw new Error('the live stream never connected');

    // From now on the server rejects the refresh token; the stream is told to go away (1008).
    server.use(
      http.post('/api/v1/auth/refresh', () =>
        HttpResponse.json({ detail: 'Invalid or expired refresh token' }, { status: 401 }),
      ),
    );
    socket.open();
    socket.serverClose(1008);

    expect(await screen.findByLabelText('Username')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/login');
    expect(window.localStorage.getItem(REFRESH_TOKEN_KEY)).toBeNull();
    expect(screen.getByText('Your session has expired. Please log in again.')).toBeInTheDocument();
    expect(await screen.findByText('Log in again to continue.')).toBeInTheDocument();
  });
});
