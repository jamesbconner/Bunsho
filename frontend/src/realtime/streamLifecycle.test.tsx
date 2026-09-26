import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { StrictMode } from 'react';
import { Navigate, Outlet, Route, Routes } from 'react-router';
import { beforeEach, describe, expect, it } from 'vitest';

import { AuthProvider } from '../auth/AuthProvider';
import { useAuth } from '../auth/authContext';
import { RequireAuth } from '../auth/RequireAuth';
import { REFRESH_TOKEN_KEY, session } from '../auth/session';
import { FakeSocket } from '../test/fakeSocket';
import { renderWithProviders } from '../test/render';
import { server } from '../test/server';
import { RealtimeProvider } from './RealtimeProvider';

const TOKENS = { access_token: 'a2', refresh_token: 'r2', token_type: 'bearer', expires_in: 900 };

const sockets: FakeSocket[] = [];
function createSocket(url: string): FakeSocket {
  const socket = new FakeSocket(url);
  sockets.push(socket);
  return socket;
}
function liveSockets(): FakeSocket[] {
  return sockets.filter((socket) => !socket.closed);
}

/** Stands in for the login page: logs in on click, then goes to the app like the real page does. */
function LoginStub() {
  const { status, login } = useAuth();
  if (status === 'authenticated') return <Navigate to="/" replace />;
  return (
    <button
      onClick={() => {
        void login('james', 'pw');
      }}
    >
      Log in
    </button>
  );
}

function HomeStub() {
  const { logout } = useAuth();
  return <button onClick={logout}>Log out</button>;
}

/** The app's real gate (`RequireAuth`) and stream (`RealtimeProvider`) around stub pages. */
function renderApp({ strict = false }: { strict?: boolean } = {}) {
  const tree = (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginStub />} />
        <Route element={<RequireAuth />}>
          <Route
            element={
              <RealtimeProvider createSocket={createSocket}>
                <Outlet />
              </RealtimeProvider>
            }
          >
            <Route index element={<HomeStub />} />
          </Route>
        </Route>
      </Routes>
    </AuthProvider>
  );
  return renderWithProviders(strict ? <StrictMode>{tree}</StrictMode> : tree);
}

describe('the live stream across logout and login', () => {
  beforeEach(() => {
    sockets.length = 0;
    session.clear();
    window.localStorage.setItem(REFRESH_TOKEN_KEY, 'r1');
    server.use(
      http.post('/api/v1/auth/refresh', () => HttpResponse.json(TOKENS)),
      http.post('/api/v1/auth/login', () => HttpResponse.json(TOKENS)),
      http.post('/api/v1/auth/logout', () => new HttpResponse(null, { status: 204 })),
    );
  });

  it('closes the stream on logout and opens a new one after the next login', async () => {
    renderApp();
    await screen.findByRole('button', { name: 'Log out' });
    await waitFor(() => {
      expect(sockets).toHaveLength(1);
    });

    await userEvent.click(screen.getByRole('button', { name: 'Log out' }));
    await screen.findByRole('button', { name: 'Log in' });
    expect(liveSockets()).toHaveLength(0);
    expect(sockets).toHaveLength(1); // logging out opened nothing new

    await userEvent.click(screen.getByRole('button', { name: 'Log in' }));
    await screen.findByRole('button', { name: 'Log out' });
    await waitFor(() => {
      expect(sockets).toHaveLength(2);
    });
    expect(liveSockets()).toEqual([sockets[1]]); // the old one stays closed
  });

  it('keeps exactly one live stream under StrictMode double mounting, and none after logout', async () => {
    renderApp({ strict: true });
    await screen.findByRole('button', { name: 'Log out' });
    await waitFor(() => {
      expect(liveSockets()).toHaveLength(1);
    });

    await userEvent.click(screen.getByRole('button', { name: 'Log out' }));
    await screen.findByRole('button', { name: 'Log in' });
    expect(liveSockets()).toHaveLength(0); // a leaked socket from the double mount would show here
  });
});
