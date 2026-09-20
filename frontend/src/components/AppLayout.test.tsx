import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router';
import { describe, expect, it, vi } from 'vitest';

import { AuthContext, type AuthContextValue } from '../auth/authContext';
import { RealtimeContext } from '../realtime/realtimeContext';
import { renderWithProviders } from '../test/render';
import { AppLayout } from './AppLayout';

function renderLayout(logout = vi.fn()) {
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
          </Route>
        </Routes>
      </RealtimeContext>
    </AuthContext>,
  );
  return logout;
}

describe('AppLayout', () => {
  it('frames the page with the wordmark, navigation and the connection state', () => {
    renderLayout();
    expect(screen.getByRole('heading', { name: /Bunshō/ })).toBeInTheDocument();
    expect(document.querySelector('span[lang="ja"]')).toHaveTextContent('文章');
    expect(screen.getByRole('link', { name: 'Home' })).toBeInTheDocument();
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

  it('says that logging out only affects this browser', () => {
    renderLayout();
    expect(screen.getByRole('button', { name: 'Log out' })).toHaveAttribute(
      'title',
      expect.stringMatching(/this browser only/i),
    );
  });

  it('has a theme toggle', () => {
    renderLayout();
    expect(screen.getByRole('radio', { name: 'Dark' })).toBeInTheDocument();
  });
});
