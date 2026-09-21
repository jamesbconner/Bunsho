import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Route, Routes } from 'react-router';
import { beforeEach, describe, expect, it } from 'vitest';

import { AuthProvider } from '../../auth/AuthProvider';
import { RequireAuth } from '../../auth/RequireAuth';
import { REFRESH_TOKEN_KEY, session } from '../../auth/session';
import { renderWithProviders } from '../../test/render';
import { server } from '../../test/server';
import { LoginPage } from './LoginPage';

const TOKENS = { access_token: 'a1', refresh_token: 'r1', token_type: 'bearer', expires_in: 900 };

function renderApp(initialEntries: Parameters<typeof renderWithProviders>[1] = {}) {
  return renderWithProviders(
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<RequireAuth />}>
          <Route path="/" element={<p>Home page</p>} />
          <Route path="/build" element={<p>Build page</p>} />
        </Route>
      </Routes>
    </AuthProvider>,
    initialEntries,
  );
}

async function fillAndSubmit(username: string, password: string) {
  const user = userEvent.setup();
  if (username !== '') await user.type(screen.getByLabelText('Username'), username);
  if (password !== '') await user.type(screen.getByLabelText('Password'), password);
  await user.click(screen.getByRole('button', { name: 'Log in' }));
}

describe('LoginPage', () => {
  beforeEach(() => {
    session.clear();
  });

  it('sends anonymous visitors to the login page', async () => {
    renderApp();
    expect(await screen.findByLabelText('Username')).toBeInTheDocument();
  });

  it('puts the cursor in the username field', async () => {
    renderApp({ initialEntries: ['/login'] });
    expect(await screen.findByLabelText('Username')).toHaveFocus();
  });

  it('asks for both fields before contacting the server', async () => {
    renderApp({ initialEntries: ['/login'] });
    await fillAndSubmit('', '');
    expect(await screen.findByText('Enter your username')).toBeInTheDocument();
    expect(screen.getByText('Enter your password')).toBeInTheDocument();
  });

  it('logs in and lands on the home page', async () => {
    let body: unknown = null;
    server.use(
      http.post('/api/v1/auth/login', async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(TOKENS);
      }),
    );
    renderApp({ initialEntries: ['/login'] });
    await fillAndSubmit(' james ', 'secret');
    expect(await screen.findByText('Home page')).toBeInTheDocument();
    expect(body).toEqual({ username: 'james', password: 'secret' });
    expect(session.getRefreshToken()).toBe('r1');
  });

  it('returns to the page the visitor was heading for', async () => {
    server.use(http.post('/api/v1/auth/login', () => HttpResponse.json(TOKENS)));
    renderApp({ initialEntries: ['/build'] });
    await fillAndSubmit('james', 'secret');
    expect(await screen.findByText('Build page')).toBeInTheDocument();
  });

  it('says so when the credentials are wrong', async () => {
    server.use(
      http.post('/api/v1/auth/login', () =>
        HttpResponse.json({ detail: 'Invalid credentials' }, { status: 401 }),
      ),
    );
    renderApp({ initialEntries: ['/login'] });
    await fillAndSubmit('james', 'wrong');
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid username or password.');
    expect(screen.queryByText('Home page')).not.toBeInTheDocument();
  });

  it('shows a countdown and disables the button while throttled', async () => {
    server.use(
      http.post('/api/v1/auth/login', () =>
        HttpResponse.json(
          { detail: 'Too many failed logins; try again later' },
          { status: 429, headers: { 'Retry-After': '42' } },
        ),
      ),
    );
    renderApp({ initialEntries: ['/login'] });
    await fillAndSubmit('james', 'secret');
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/too many attempts/i);
    // The announced alert must not carry the ticking number; the visible countdown is aria-hidden.
    expect(alert).not.toHaveTextContent(/\d+ s\b/);
    const countdown = screen.getByText(/try again in 42 s/i);
    expect(countdown).toHaveAttribute('aria-hidden', 'true');
    expect(alert).not.toContainElement(countdown);
    expect(screen.getByRole('button', { name: 'Log in' })).toBeDisabled();
  });

  it('explains an expired remembered login', async () => {
    window.localStorage.setItem(REFRESH_TOKEN_KEY, 'stale');
    server.use(
      http.post('/api/v1/auth/refresh', () =>
        HttpResponse.json({ detail: 'Invalid or expired refresh token' }, { status: 401 }),
      ),
    );
    renderApp();
    expect(await screen.findByText(/your session has expired/i)).toBeInTheDocument();
  });

  it('lets a user with a remembered login straight in', async () => {
    window.localStorage.setItem(REFRESH_TOKEN_KEY, 'r1');
    server.use(http.post('/api/v1/auth/refresh', () => HttpResponse.json(TOKENS)));
    renderApp();
    await waitFor(() => {
      expect(screen.getByText('Home page')).toBeInTheDocument();
    });
  });
});
