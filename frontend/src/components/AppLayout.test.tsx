import { act, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { lazy } from 'react';
import { Route, Routes } from 'react-router';
import { describe, expect, it, vi } from 'vitest';

import { AuthContext, type AuthContextValue } from '../auth/authContext';
import { RealtimeContext } from '../realtime/realtimeContext';
import { renderWithProviders } from '../test/render';
import { AppLayout } from './AppLayout';

let releaseSlowPage: () => void = () => undefined;
const SlowPage = lazy(
  () =>
    new Promise<{ default: () => React.JSX.Element }>((resolve) => {
      releaseSlowPage = () => {
        resolve({ default: () => <p>Slow page loaded</p> });
      };
    }),
);

function renderLayout(logout = vi.fn(), initialEntries: string[] = ['/']) {
  const auth: AuthContextValue = {
    status: 'authenticated',
    sessionExpired: false,
    login: () => Promise.resolve(),
    logout,
    retry: () => {},
  };
  renderWithProviders(
    <AuthContext value={auth}>
      <RealtimeContext value={{ kind: 'connected' }}>
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<p>Home content</p>} />
            <Route path="build" element={<p>Build content page</p>} />
            <Route path="slow" element={<SlowPage />} />
          </Route>
        </Routes>
      </RealtimeContext>
    </AuthContext>,
    { initialEntries },
  );
  return logout;
}

describe('AppLayout', () => {
  it('frames the page with the wordmark, navigation and the connection state', () => {
    renderLayout();
    expect(screen.getByRole('heading', { name: /Bunshō/ })).toBeInTheDocument();
    expect(document.querySelector('span[lang="ja"]')).toHaveTextContent('文章');
    expect(screen.getByRole('link', { name: 'Home' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Study' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Statistics' })).toHaveAttribute('href', '/stats');
    expect(screen.getByRole('link', { name: 'Settings' })).toHaveAttribute('href', '/settings');
    expect(screen.getByRole('link', { name: 'Build content' })).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Live');
    expect(screen.getByText('Home content')).toBeInTheDocument();
  });

  it('navigates between pages', async () => {
    renderLayout();
    await userEvent.click(screen.getByRole('link', { name: 'Build content' }));
    expect(screen.getByText('Build content page')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('link', { name: 'Home' }));
    expect(screen.getByText('Home content')).toBeInTheDocument();
  });

  it('logs out on request', async () => {
    const logout = renderLayout();
    await userEvent.click(screen.getByRole('button', { name: 'Log out' }));
    expect(logout).toHaveBeenCalledTimes(1);
  });

  it('says, in visible text, that logging out only affects this browser', () => {
    renderLayout();
    const note = screen.getByText(
      'Logging out only affects this browser: the server cannot end sessions yet.',
    );
    expect(note).toBeVisible();
    expect(note).toHaveAttribute('id');
    expect(screen.getByRole('button', { name: 'Log out' })).toHaveAccessibleDescription(
      note.textContent,
    );
    expect(screen.getByRole('button', { name: 'Log out' })).toHaveAttribute(
      'aria-describedby',
      note.id,
    );
  });

  it('has a theme toggle', () => {
    renderLayout();
    expect(screen.getByRole('radio', { name: 'Dark' })).toBeInTheDocument();
  });

  it('shows a loading indicator while a page is being fetched, then the page', async () => {
    renderLayout(vi.fn(), ['/slow']);
    expect(screen.getByRole('status', { name: 'Loading page' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Home' })).toBeInTheDocument();
    await act(async () => {
      releaseSlowPage();
      await Promise.resolve();
    });
    expect(await screen.findByText('Slow page loaded')).toBeInTheDocument();
    expect(screen.queryByRole('status', { name: 'Loading page' })).not.toBeInTheDocument();
  });
});
