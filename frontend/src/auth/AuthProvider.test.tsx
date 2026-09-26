import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { server } from '../test/server';
import { renderWithProviders } from '../test/render';
import { AuthProvider } from './AuthProvider';
import { useAuth } from './authContext';
import { REFRESH_TOKEN_KEY, session } from './session';

function Probe() {
  const { status, sessionExpired, logout, retry } = useAuth();
  return (
    <div>
      <span data-testid="status">{status}</span>
      <span data-testid="expired">{String(sessionExpired)}</span>
      <button onClick={logout}>logout</button>
      <button onClick={retry}>retry</button>
    </div>
  );
}

function renderProbe() {
  return renderWithProviders(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  );
}

const TOKENS = { access_token: 'a2', refresh_token: 'r2', token_type: 'bearer', expires_in: 900 };

describe('AuthProvider bootstrap', () => {
  beforeEach(() => {
    session.clear();
  });

  it('is anonymous without a remembered login', async () => {
    renderProbe();
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('anonymous');
    });
    expect(screen.getByTestId('expired')).toHaveTextContent('false');
  });

  it('logs in again from the remembered refresh token', async () => {
    window.localStorage.setItem(REFRESH_TOKEN_KEY, 'r1');
    server.use(http.post('/api/v1/auth/refresh', () => HttpResponse.json(TOKENS)));
    renderProbe();
    expect(screen.getByTestId('status')).toHaveTextContent('checking');
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('authenticated');
    });
    expect(session.getRefreshToken()).toBe('r2');
  });

  it('is anonymous, and tells the user, when the server rejects the remembered login', async () => {
    window.localStorage.setItem(REFRESH_TOKEN_KEY, 'stale');
    server.use(
      http.post('/api/v1/auth/refresh', () =>
        HttpResponse.json({ detail: 'Invalid or expired refresh token' }, { status: 401 }),
      ),
    );
    renderProbe();
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('anonymous');
    });
    expect(screen.getByTestId('expired')).toHaveTextContent('true');
    expect(session.getRefreshToken()).toBeNull();
  });

  it('keeps the remembered login when the server cannot be reached, and retries', async () => {
    window.localStorage.setItem(REFRESH_TOKEN_KEY, 'r1');
    server.use(http.post('/api/v1/auth/refresh', () => HttpResponse.error()));
    renderProbe();
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('unreachable');
    });
    expect(session.getRefreshToken()).toBe('r1');

    server.use(http.post('/api/v1/auth/refresh', () => HttpResponse.json(TOKENS)));
    await userEvent.click(screen.getByRole('button', { name: 'retry' }));
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('authenticated');
    });
  });
});

describe('AuthProvider sessions', () => {
  beforeEach(() => {
    session.clear();
    window.localStorage.setItem(REFRESH_TOKEN_KEY, 'r1');
    server.use(
      http.post('/api/v1/auth/refresh', () => HttpResponse.json(TOKENS)),
      http.post('/api/v1/auth/logout', () => new HttpResponse(null, { status: 204 })),
    );
  });

  it('logout forgets the tokens and clears the query cache', async () => {
    const { queryClient } = renderProbe();
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('authenticated');
    });
    queryClient.setQueryData(['content', 'summary'], { built: true });
    await userEvent.click(screen.getByRole('button', { name: 'logout' }));
    expect(screen.getByTestId('status')).toHaveTextContent('anonymous');
    expect(session.getRefreshToken()).toBeNull();
    expect(queryClient.getQueryData(['content', 'summary'])).toBeUndefined();
  });

  it('follows another tab that logged out', async () => {
    renderProbe();
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('authenticated');
    });
    window.dispatchEvent(new StorageEvent('storage', { key: REFRESH_TOKEN_KEY, newValue: null }));
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('anonymous');
    });
  });

  it('becomes anonymous when the session expires while in use', async () => {
    renderProbe();
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('authenticated');
    });
    session.expire();
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('anonymous');
    });
    expect(screen.getByTestId('expired')).toHaveTextContent('true');
    expect(await screen.findByText('Session ended')).toBeInTheDocument();
  });

  it('logout also asks the server to end the session it just left', async () => {
    let body: unknown = null;
    server.use(
      http.post('/api/v1/auth/logout', async ({ request }) => {
        body = await request.json();
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderProbe();
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('authenticated');
    });
    await userEvent.click(screen.getByRole('button', { name: 'logout' }));
    await waitFor(() => {
      expect(body).toEqual({ refresh_token: 'r2' }); // the token the restore stored
    });
  });

  it('logout still works here when the server cannot be reached', async () => {
    let attempted = false;
    server.use(
      http.post('/api/v1/auth/logout', () => {
        attempted = true;
        return HttpResponse.error();
      }),
    );
    renderProbe();
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('authenticated');
    });
    await userEvent.click(screen.getByRole('button', { name: 'logout' }));
    expect(screen.getByTestId('status')).toHaveTextContent('anonymous');
    expect(session.getRefreshToken()).toBeNull();
    await waitFor(() => {
      expect(attempted).toBe(true);
    });
  });

  it('logout still works here when the server answers with an error', async () => {
    let attempted = false;
    server.use(
      http.post('/api/v1/auth/logout', () => {
        attempted = true;
        return HttpResponse.json({ detail: 'boom' }, { status: 500 });
      }),
    );
    renderProbe();
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('authenticated');
    });
    await userEvent.click(screen.getByRole('button', { name: 'logout' }));
    expect(screen.getByTestId('status')).toHaveTextContent('anonymous');
    await waitFor(() => {
      expect(attempted).toBe(true);
    });
  });

  it('does not call the server when another tab logged out', async () => {
    let calls = 0;
    server.use(
      http.post('/api/v1/auth/logout', () => {
        calls += 1;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderProbe();
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('authenticated');
    });
    window.dispatchEvent(new StorageEvent('storage', { key: REFRESH_TOKEN_KEY, newValue: null }));
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('anonymous');
    });
    await new Promise((resolve) => setTimeout(resolve, 50)); // a call would have arrived by now
    expect(calls).toBe(0);
  });
});
