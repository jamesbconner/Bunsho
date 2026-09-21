import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ReviewSettings } from '../../api/endpoints';
import { session } from '../../auth/session';
import { makeSettings } from '../../test/fixtures';
import { renderWithProviders } from '../../test/render';
import { server } from '../../test/server';
import { SettingsPage } from './SettingsPage';

/** Serve the settings and record every PUT body; the server echoes the document it was sent. */
function serveSettings(initial: ReviewSettings = makeSettings()) {
  const puts: unknown[] = [];
  server.use(
    http.get('/api/v1/settings', () => HttpResponse.json(initial)),
    http.put('/api/v1/settings', async ({ request }) => {
      const body = await request.json();
      puts.push(body);
      return HttpResponse.json(body);
    }),
  );
  return puts;
}

async function openSettings() {
  const view = renderWithProviders(<SettingsPage />);
  await screen.findByRole('button', { name: 'Save' });
  return view;
}

async function setNumber(user: ReturnType<typeof userEvent.setup>, name: string, value: string) {
  const input = screen.getByRole('textbox', { name });
  await user.clear(input);
  if (value !== '') await user.type(input, value);
}

describe('SettingsPage', () => {
  beforeEach(() => {
    session.clear();
    session.setTokens({ access_token: 'a1', refresh_token: 'r1', expires_in: 900 });
  });

  it('fills the form from the saved settings', async () => {
    serveSettings(
      makeSettings({
        new_card_policy: 'mastery_unlock',
        new_limits: { kana: 5, kanji: 6, vocab: 7 },
        target_retention: 0.85,
        rollover_hour: 6,
        active_levels: ['N5', 'N4'],
        mastery_threshold: 0.65,
      }),
    );
    await openSettings();

    expect(screen.getByRole('radio', { name: /Mastery unlock/ })).toBeChecked();
    expect(screen.getByRole('textbox', { name: 'Kana per day' })).toHaveValue('5');
    expect(screen.getByRole('textbox', { name: 'Kanji per day' })).toHaveValue('6');
    expect(screen.getByRole('textbox', { name: 'Vocabulary per day' })).toHaveValue('7');
    expect(screen.getByRole('slider', { name: 'Target retention' })).toHaveAttribute(
      'aria-valuenow',
      '85',
    );
    expect(screen.getByRole('combobox', { name: /A new study day starts at/ })).toHaveValue('6');
    expect(screen.getByRole('checkbox', { name: 'N5' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'N4' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'N3' })).not.toBeChecked();
    expect(screen.getByRole('textbox', { name: /Mastery needed/ })).toHaveValue('65%');
  });

  it('keeps Save disabled until something changes, and says when there are unsaved changes', async () => {
    const user = userEvent.setup();
    serveSettings();
    await openSettings();
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
    expect(screen.queryByText('Unsaved changes')).not.toBeInTheDocument();

    await setNumber(user, 'Kana per day', '30');
    expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled();
    expect(screen.getByText('Unsaved changes')).toBeInTheDocument();
  });

  it('saves the whole edited document, then shows a toast and a clean form', async () => {
    const user = userEvent.setup();
    const puts = serveSettings();
    await openSettings();

    await setNumber(user, 'Kana per day', '30');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText('Settings saved')).toBeInTheDocument();
    expect(puts).toEqual([makeSettings({ new_limits: { kana: 30, kanji: 15, vocab: 20 } })]);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
    });
    expect(screen.queryByText('Unsaved changes')).not.toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Kana per day' })).toHaveValue('30');
  });

  it('sends a changed slider, select and levels as the API expects them', async () => {
    const user = userEvent.setup();
    const puts = serveSettings();
    await openSettings();

    await user.click(screen.getByRole('radio', { name: /Pinned levels/ }));
    await user.click(screen.getByRole('checkbox', { name: 'N4' }));
    await user.selectOptions(
      screen.getByRole('combobox', { name: /A new study day starts at/ }),
      '6:00',
    );
    screen.getByRole('slider', { name: 'Target retention' }).focus();
    await user.keyboard('{ArrowRight}{ArrowRight}');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    await screen.findByText('Settings saved');
    expect(puts).toEqual([
      makeSettings({
        new_card_policy: 'pinned_levels',
        active_levels: ['N5', 'N4'],
        rollover_hour: 6,
        target_retention: 0.92,
      }),
    ]);
  });

  it('shows the API rules as messages and sends nothing while a field is wrong', async () => {
    const user = userEvent.setup();
    const puts = serveSettings();
    await openSettings();

    await setNumber(user, 'Kana per day', '');
    await setNumber(user, 'Kanji per day', '');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    const message = 'Enter a whole number from 0 to 10,000.';
    expect(await screen.findAllByText(message)).toHaveLength(2);
    expect(puts).toEqual([]);
  });

  it('needs at least one level even when the policy does not use them', async () => {
    const user = userEvent.setup();
    const puts = serveSettings();
    await openSettings();
    await user.click(screen.getByRole('radio', { name: /Pinned levels/ }));
    await user.click(screen.getByRole('checkbox', { name: 'N5' }));
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByText('Pick at least one level.')).toBeInTheDocument();
    expect(puts).toEqual([]);
  });

  it('enables the levels and the mastery threshold only for the policies that use them', async () => {
    const user = userEvent.setup();
    serveSettings();
    await openSettings();
    const chip = () => screen.getByRole('checkbox', { name: 'N4' });
    const mastery = () => screen.getByRole('textbox', { name: /Mastery needed/ });

    expect(chip()).toBeDisabled();
    expect(mastery()).toBeDisabled();
    expect(screen.getByText('Only used by "Pinned levels".')).toBeInTheDocument();
    expect(screen.getByText('Only used by "Mastery unlock".')).toBeInTheDocument();

    await user.click(screen.getByRole('radio', { name: /Pinned levels/ }));
    expect(chip()).toBeEnabled();
    expect(mastery()).toBeDisabled();

    await user.click(screen.getByRole('radio', { name: /Mastery unlock/ }));
    expect(chip()).toBeDisabled();
    expect(mastery()).toBeEnabled();
  });

  it('still saves the values of fields the chosen policy does not use', async () => {
    const user = userEvent.setup();
    const puts = serveSettings(
      makeSettings({ active_levels: ['N5', 'N3'], mastery_threshold: 0.7 }),
    );
    await openSettings();
    await setNumber(user, 'Kana per day', '21');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    await screen.findByText('Settings saved');
    expect(puts).toEqual([
      makeSettings({
        new_limits: { kana: 21, kanji: 15, vocab: 20 },
        active_levels: ['N5', 'N3'],
        mastery_threshold: 0.7,
      }),
    ]);
  });

  it('puts a server 422 on the matching fields and the rest in an alert', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('/api/v1/settings', () => HttpResponse.json(makeSettings())),
      http.put('/api/v1/settings', () =>
        HttpResponse.json(
          {
            detail: [
              {
                loc: ['body', 'new_limits', 'kana'],
                msg: 'Input should be at most 10000',
                type: 'x',
              },
              { loc: ['body', 'surprise'], msg: 'Extra inputs are not permitted', type: 'y' },
            ],
          },
          { status: 422 },
        ),
      ),
    );
    await openSettings();
    await setNumber(user, 'Kana per day', '30');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText('Input should be at most 10000')).toBeInTheDocument();
    const alert = screen.getByRole('alert');
    expect(within(alert).getByText("Couldn't save your settings")).toBeInTheDocument();
    expect(within(alert).getByText('surprise: Extra inputs are not permitted')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Kana per day' })).toHaveValue('30');
  });

  it('keeps the edits after a network failure and re-sends the identical request on Try again', async () => {
    const user = userEvent.setup();
    const bodies: Record<string, unknown>[] = [];
    let calls = 0;
    server.use(
      http.get('/api/v1/settings', () => HttpResponse.json(makeSettings())),
      http.put('/api/v1/settings', async ({ request }) => {
        bodies.push((await request.json()) as Record<string, unknown>);
        calls += 1;
        return calls === 1 ? HttpResponse.error() : HttpResponse.json(bodies[0]);
      }),
    );
    await openSettings();
    await setNumber(user, 'Kana per day', '30');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText("Couldn't save your settings")).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Kana per day' })).toHaveValue('30');
    expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled();

    await user.click(within(alert).getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('Settings saved')).toBeInTheDocument();
    expect(bodies).toHaveLength(2);
    expect(bodies[1]).toEqual(bodies[0]);
    expect(screen.queryByText("Couldn't save your settings")).not.toBeInTheDocument();
  });

  it('refills the form with the recommended values without saving them', async () => {
    const user = userEvent.setup();
    const puts = serveSettings(
      makeSettings({
        new_card_policy: 'pinned_levels',
        new_limits: { kana: 50, kanji: 40, vocab: 30 },
        target_retention: 0.8,
        rollover_hour: 9,
        active_levels: ['N3'],
        mastery_threshold: 0.5,
      }),
    );
    await openSettings();
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();

    await user.click(screen.getByRole('button', { name: 'Reset to recommended values' }));

    expect(screen.getByRole('radio', { name: /Strict order/ })).toBeChecked();
    expect(screen.getByRole('textbox', { name: 'Kana per day' })).toHaveValue('20');
    expect(screen.getByRole('textbox', { name: 'Kanji per day' })).toHaveValue('15');
    expect(screen.getByRole('textbox', { name: 'Vocabulary per day' })).toHaveValue('20');
    expect(screen.getByRole('slider', { name: 'Target retention' })).toHaveAttribute(
      'aria-valuenow',
      '90',
    );
    expect(screen.getByRole('combobox', { name: /A new study day starts at/ })).toHaveValue('4');
    expect(screen.getByRole('checkbox', { name: 'N5' })).toBeChecked();
    expect(puts).toEqual([]);
    expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled();
    expect(screen.getByText('Unsaved changes')).toBeInTheDocument();
  });

  it('marks the next card and the statistics stale after a save', async () => {
    const user = userEvent.setup();
    serveSettings();
    const { queryClient } = await openSettings();
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
    await setNumber(user, 'Kana per day', '30');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    await screen.findByText('Settings saved');
    const keys = invalidate.mock.calls.map((call) => call[0]?.queryKey);
    expect(keys).toEqual([
      ['review', 'next'],
      ['stats', 'summary'],
    ]);
  });

  it('explains a failed load and can try again', async () => {
    const user = userEvent.setup();
    let calls = 0;
    server.use(
      http.get('/api/v1/settings', () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json({ detail: 'boom' }, { status: 500 })
          : HttpResponse.json(makeSettings());
      }),
    );
    renderWithProviders(<SettingsPage />);
    expect(await screen.findByText("Couldn't load your settings")).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('button', { name: 'Save' })).toBeInTheDocument();
  });
});
