import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router';
import { describe, expect, it, vi } from 'vitest';

import { AuthContext, type AuthContextValue } from '../auth/authContext';
import { RealtimeContext } from '../realtime/realtimeContext';
import { renderWithProviders } from '../test/render';
import { AppLayout } from './AppLayout';

const NOTE = 'Logging out also ends this session on the server.';

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
            <Route path="settings" element={<p>Settings page</p>} />
          </Route>
        </Routes>
      </RealtimeContext>
    </AuthContext>,
    { initialEntries },
  );
  return logout;
}

/** The page links in the header (the phone drawer is closed and unmounted until the burger opens it). */
function headerLinks() {
  return within(screen.getByRole('navigation', { name: 'Main' }));
}

describe('AppLayout header', () => {
  it('frames the page with the wordmark, the page links and the connection state', () => {
    renderLayout();
    expect(screen.getByRole('heading', { name: /Bunshō/ })).toBeInTheDocument();
    expect(document.querySelector('span[lang="ja"]')).toHaveTextContent('文章');
    expect(headerLinks().getByRole('link', { name: 'Home' })).toHaveAttribute('href', '/');
    expect(headerLinks().getByRole('link', { name: 'Study' })).toHaveAttribute('href', '/review');
    expect(headerLinks().getByRole('link', { name: 'Statistics' })).toHaveAttribute(
      'href',
      '/stats',
    );
    expect(headerLinks().getByRole('link', { name: 'Settings' })).toHaveAttribute(
      'href',
      '/settings',
    );
    expect(screen.queryByRole('link', { name: 'Build content' })).not.toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Live');
    expect(screen.getByText('Home content')).toBeInTheDocument();
  });

  it('marks only the current page as current', () => {
    renderLayout(vi.fn(), ['/settings']);
    expect(headerLinks().getByRole('link', { name: 'Settings' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(headerLinks().getByRole('link', { name: 'Home' })).not.toHaveAttribute('aria-current');
    expect(headerLinks().getByRole('link', { name: 'Study' })).not.toHaveAttribute('aria-current');
  });

  it('navigates between pages and moves the current-page marker', async () => {
    renderLayout();
    await userEvent.click(headerLinks().getByRole('link', { name: 'Settings' }));
    expect(screen.getByText('Settings page')).toBeInTheDocument();
    expect(headerLinks().getByRole('link', { name: 'Settings' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    await userEvent.click(headerLinks().getByRole('link', { name: 'Home' }));
    expect(screen.getByText('Home content')).toBeInTheDocument();
    expect(headerLinks().getByRole('link', { name: 'Home' })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('has a theme toggle', () => {
    renderLayout();
    expect(screen.getByRole('radio', { name: 'Dark' })).toBeInTheDocument();
  });
});

describe('Account menu', () => {
  it('keeps Log out out of sight until the menu is opened', () => {
    renderLayout();
    expect(screen.getByRole('button', { name: 'Account' })).toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: 'Log out' })).not.toBeInTheDocument();
  });

  it('logs out on request', async () => {
    const logout = renderLayout();
    await userEvent.click(screen.getByRole('button', { name: 'Account' }));
    await userEvent.click(await screen.findByRole('menuitem', { name: 'Log out' }));
    expect(logout).toHaveBeenCalledTimes(1);
  });

  it('says, in visible text, that logging out also ends the session on the server', async () => {
    renderLayout();
    await userEvent.click(screen.getByRole('button', { name: 'Account' }));
    const item = await screen.findByRole('menuitem', { name: 'Log out' });
    const note = screen.getByText(NOTE);
    expect(note).toBeVisible();
    expect(note).toHaveAttribute('id');
    expect(item).toHaveAttribute('aria-describedby', note.id);
    expect(item).toHaveAccessibleDescription(NOTE);
  });
});

describe('Phone navigation drawer', () => {
  it('is closed until the burger is pressed', () => {
    renderLayout();
    const burger = screen.getByRole('button', { name: 'Toggle navigation' });
    expect(burger).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('opens with the pages, Log out and the note, and closes again', async () => {
    const logout = renderLayout();
    const burger = screen.getByRole('button', { name: 'Toggle navigation' });
    await userEvent.click(burger);
    expect(burger).toHaveAttribute('aria-expanded', 'true');
    const drawer = within(await screen.findByRole('dialog', { name: 'Menu' }));
    for (const name of ['Home', 'Study', 'Statistics', 'Settings']) {
      expect(drawer.getByRole('link', { name })).toBeInTheDocument();
    }
    expect(drawer.getByRole('radio', { name: 'Dark' })).toBeInTheDocument();
    const note = drawer.getByText(NOTE);
    expect(note).toBeVisible();
    expect(drawer.getByRole('button', { name: 'Log out' })).toHaveAccessibleDescription(NOTE);
    await userEvent.click(drawer.getByRole('button', { name: 'Log out' }));
    expect(logout).toHaveBeenCalledTimes(1);
  });

  it('closes when a page is chosen', async () => {
    renderLayout();
    await userEvent.click(screen.getByRole('button', { name: 'Toggle navigation' }));
    const drawer = within(await screen.findByRole('dialog', { name: 'Menu' }));
    await userEvent.click(drawer.getByRole('link', { name: 'Settings' }));
    expect(screen.getByText('Settings page')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });

  it('closes on Escape', async () => {
    renderLayout();
    await userEvent.click(screen.getByRole('button', { name: 'Toggle navigation' }));
    await screen.findByRole('dialog', { name: 'Menu' });
    await userEvent.keyboard('{Escape}');
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });

  it('stays closed when the viewport is at least the phone breakpoint wide', async () => {
    // jsdom's stub in src/test/setup.ts never matches; make every query match (a wide viewport).
    const matchMedia = vi.spyOn(window, 'matchMedia').mockImplementation((query: string) => ({
      matches: true,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }));
    try {
      renderLayout();
      const burger = screen.getByRole('button', { name: 'Toggle navigation' });
      await userEvent.click(burger);
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      expect(burger).toHaveAttribute('aria-expanded', 'false');
    } finally {
      matchMedia.mockRestore();
    }
  });
});
