import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { session } from '../../auth/session';
import { server } from '../../test/server';
import { chooseMode, openSettings, openTab, serveSettings, setNumber } from './settingsTestUtils';

describe('Settings save bar and rows', () => {
  beforeEach(() => {
    session.clear();
    session.setTokens({ access_token: 'a1', refresh_token: 'r1', expires_in: 900 });
  });

  it('says all changes are saved and offers no Discard while the form is clean', async () => {
    serveSettings();
    await openSettings();
    expect(screen.getByText('All changes saved')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Discard changes' })).toBeDisabled();
  });

  it('discards the edits of every tab back to the saved values', async () => {
    const user = userEvent.setup();
    serveSettings();
    await openSettings();
    await openTab(user, 'Pace');
    await setNumber(user, 'Kana per day', '30');
    await openTab(user, 'Reviewing');
    await chooseMode(user, 'Kana', 'Typed');
    expect(screen.getByText('Unsaved changes')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Discard changes' }));

    const kana = screen.getByRole('radiogroup', { name: 'Kana review mode' });
    expect(within(kana).getByRole('radio', { name: 'Flip' })).toBeChecked();
    await openTab(user, 'Pace');
    expect(screen.getByRole('textbox', { name: 'Kana per day' })).toHaveValue('20');
    expect(screen.getByText('All changes saved')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
  });

  it('clears the save error when the edits are discarded', async () => {
    const user = userEvent.setup();
    serveSettings();
    server.use(http.put('/api/v1/settings', () => new HttpResponse(null, { status: 500 })));
    await openSettings();
    await openTab(user, 'Pace');
    await setNumber(user, 'Kana per day', '30');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByText("Couldn't save your settings")).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Discard changes' }));

    expect(screen.queryByText("Couldn't save your settings")).not.toBeInTheDocument();
  });

  it('locks the form while a save is in flight, then unlocks it', async () => {
    const user = userEvent.setup();
    serveSettings();
    let release: () => void = () => undefined;
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    server.use(
      http.put('/api/v1/settings', async ({ request }) => {
        await held;
        return HttpResponse.json(await request.json());
      }),
    );
    await openSettings();
    await openTab(user, 'Pace');
    await setNumber(user, 'Kana per day', '30');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      expect(screen.getByRole('textbox', { name: 'Kana per day' })).toBeDisabled();
    });
    expect(screen.getByRole('button', { name: 'Discard changes' })).toBeDisabled();
    expect(
      screen.getByRole('button', { name: 'Reset all tabs to recommended values' }),
    ).toBeDisabled();

    release();
    expect(await screen.findByText('Settings saved')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Kana per day' })).toBeEnabled();
  });

  it('keeps a switch named by its label alone and describes it with the explanation', async () => {
    const user = userEvent.setup();
    serveSettings();
    await openSettings();
    const kana = screen.getByRole('switch', { name: 'Introduce new kana' });
    expect(kana).toHaveAccessibleDescription('Hiragana and katakana.');
    expect(kana).toBeChecked();

    // The visible label toggles the switch too.
    await user.click(screen.getByText('Introduce new kana'));
    expect(kana).not.toBeChecked();
  });
});
