import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { session } from '../../auth/session';
import { openSettings, openTab, serveSettings, setNumber } from './settingsTestUtils';

// The System tab is loaded on demand; make that load fail, as a stale chunk does after a redeploy:
// the import resolves, but using it rejects the `.then` that picks the component out of it.
vi.mock('./SystemTab', () => ({
  get SystemTab(): never {
    throw new Error('chunk failed');
  },
}));

describe('Settings tabs when the System tab cannot be loaded', () => {
  beforeEach(() => {
    session.clear();
    session.setTokens({ access_token: 'a1', refresh_token: 'r1', expires_in: 900 });
    // React logs the caught render error; it is expected here.
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('contains the failure to the System panel and keeps the unsaved edits', async () => {
    const user = userEvent.setup();
    serveSettings();
    await openSettings();
    await openTab(user, 'Pace');
    await setNumber(user, 'Kana per day', '30');

    await openTab(user, 'System');
    expect(await screen.findByText('Something went wrong')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'System' })).toHaveAttribute('aria-selected', 'true');

    await openTab(user, 'Pace');
    expect(screen.queryByText('Something went wrong')).not.toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Kana per day' })).toHaveValue('30');
    expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled();
  });
});
