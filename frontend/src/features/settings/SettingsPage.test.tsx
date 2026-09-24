import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { session } from '../../auth/session';
import { makeSettings } from '../../test/fixtures';
import { renderWithProviders } from '../../test/render';
import { server } from '../../test/server';
import { SettingsPage } from './SettingsPage';
import { KANA_GATE_MESSAGE } from './settingsForm';
import { openSettings, openTab, serveSettings, setNumber } from './settingsTestUtils';

describe('SettingsPage', () => {
  beforeEach(() => {
    session.clear();
    session.setTokens({ access_token: 'a1', refresh_token: 'r1', expires_in: 900 });
  });

  it('fills the form from the saved settings', async () => {
    const user = userEvent.setup();
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
    await openTab(user, 'Pace');
    expect(screen.getByRole('textbox', { name: 'Kana per day' })).toHaveValue('5');
    expect(screen.getByRole('textbox', { name: 'Kanji per day' })).toHaveValue('6');
    expect(screen.getByRole('textbox', { name: 'Vocabulary per day' })).toHaveValue('7');
    expect(screen.getByRole('slider', { name: 'Target retention' })).toHaveAttribute(
      'aria-valuenow',
      '85',
    );
    expect(screen.getByRole('slider', { name: 'Target retention' })).toHaveAttribute(
      'aria-valuetext',
      '85%',
    );
    expect(screen.getByRole('combobox', { name: /A new study day starts at/ })).toHaveValue('6');
    await openTab(user, 'Learning path');
    expect(screen.getByRole('checkbox', { name: 'N5' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'N4' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'N3' })).not.toBeChecked();
    expect(screen.getByRole('textbox', { name: /Mastery needed/ })).toHaveValue('65%');
  });

  it('shows the three review-mode selects and sends the changed modes', async () => {
    const user = userEvent.setup();
    const puts = serveSettings();
    await openSettings();
    await openTab(user, 'Reviewing');
    const kanaSelect = await screen.findByLabelText('Kana review mode');
    await user.selectOptions(kanaSelect, 'Typed answer');
    await user.selectOptions(screen.getByLabelText('Kanji review mode'), 'Multiple choice');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => {
      expect(screen.getByText('Settings saved')).toBeInTheDocument();
    });
    expect(puts).toEqual([makeSettings({ kana_mode: 'typed', kanji_mode: 'multiple_choice' })]);
  });

  it('keeps Save disabled until something changes, and says when there are unsaved changes', async () => {
    const user = userEvent.setup();
    serveSettings();
    await openSettings();
    await openTab(user, 'Pace');
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
    await openTab(user, 'Pace');

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
    await openTab(user, 'Pace');
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
    await openTab(user, 'Pace');

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
    await openTab(user, 'Pace');
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
    await openTab(user, 'Pace');
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
    await openTab(user, 'Pace');
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

    await user.click(screen.getByRole('button', { name: 'Reset all tabs to recommended values' }));

    expect(screen.getByRole('radio', { name: /Strict order/ })).toBeChecked();
    await openTab(user, 'Pace');
    expect(screen.getByRole('textbox', { name: 'Kana per day' })).toHaveValue('20');
    expect(screen.getByRole('textbox', { name: 'Kanji per day' })).toHaveValue('15');
    expect(screen.getByRole('textbox', { name: 'Vocabulary per day' })).toHaveValue('20');
    expect(screen.getByRole('slider', { name: 'Target retention' })).toHaveAttribute(
      'aria-valuenow',
      '90',
    );
    expect(screen.getByRole('combobox', { name: /A new study day starts at/ })).toHaveValue('4');
    await openTab(user, 'Learning path');
    expect(screen.getByRole('checkbox', { name: 'N5' })).toBeChecked();
    expect(puts).toEqual([]);
    expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled();
    expect(screen.getByText('Unsaved changes')).toBeInTheDocument();
  });

  it('lets Save through after Reset even when an earlier edit was undone by hand', async () => {
    const user = userEvent.setup();
    serveSettings(makeSettings({ new_limits: { kana: 50, kanji: 15, vocab: 20 } }));
    await openSettings();
    await user.click(screen.getByRole('radio', { name: /Pinned levels/ }));
    await user.click(screen.getByRole('radio', { name: /Strict order/ }));
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();

    await user.click(screen.getByRole('button', { name: 'Reset all tabs to recommended values' }));

    await openTab(user, 'Pace');
    expect(screen.getByRole('textbox', { name: 'Kana per day' })).toHaveValue('20');
    expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled();
    expect(screen.getByText('Unsaved changes')).toBeInTheDocument();
  });

  it('keeps Save disabled when Reset lands on what is already saved after an edit', async () => {
    const user = userEvent.setup();
    serveSettings();
    await openSettings();
    await openTab(user, 'Pace');
    await setNumber(user, 'Kana per day', '30');
    expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled();

    await user.click(screen.getByRole('button', { name: 'Reset all tabs to recommended values' }));

    expect(screen.getByRole('textbox', { name: 'Kana per day' })).toHaveValue('20');
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
    expect(screen.queryByText('Unsaved changes')).not.toBeInTheDocument();
  });

  it('still counts Reset as a change after one field was nudged and put back', async () => {
    const user = userEvent.setup();
    serveSettings(makeSettings({ new_limits: { kana: 50, kanji: 15, vocab: 20 } }));
    await openSettings();
    await user.click(screen.getByRole('button', { name: 'Reset all tabs to recommended values' }));
    await openTab(user, 'Pace');
    await setNumber(user, 'Kanji per day', '16');
    await setNumber(user, 'Kanji per day', '15');

    expect(screen.getByRole('textbox', { name: 'Kana per day' })).toHaveValue('20');
    expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled();
    expect(screen.getByText('Unsaved changes')).toBeInTheDocument();
  });

  it('is not changed by unticking and ticking a level again', async () => {
    const user = userEvent.setup();
    serveSettings(makeSettings({ new_card_policy: 'pinned_levels', active_levels: ['N5', 'N4'] }));
    await openSettings();
    await user.click(screen.getByRole('checkbox', { name: 'N5' }));
    expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled();
    await user.click(screen.getByRole('checkbox', { name: 'N5' }));

    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
    expect(screen.queryByText('Unsaved changes')).not.toBeInTheDocument();
  });

  it('is clean again when an edit is put back by hand', async () => {
    const user = userEvent.setup();
    serveSettings();
    await openSettings();
    await openTab(user, 'Pace');
    await setNumber(user, 'Kana per day', '30');
    expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled();
    await setNumber(user, 'Kana per day', '20');

    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
    expect(screen.queryByText('Unsaved changes')).not.toBeInTheDocument();
  });

  it('keeps the form and its edits when a background refetch fails', async () => {
    const user = userEvent.setup();
    let failing = false;
    server.use(
      http.get('/api/v1/settings', () =>
        failing
          ? HttpResponse.json({ detail: 'boom' }, { status: 500 })
          : HttpResponse.json(makeSettings()),
      ),
    );
    const { queryClient } = await openSettings();
    await openTab(user, 'Pace');
    await setNumber(user, 'Kana per day', '30');

    failing = true;
    await act(async () => {
      await queryClient.refetchQueries({ queryKey: ['settings'] });
      // TanStack Query hands its result to React on a timer: let it arrive before asserting.
      await new Promise((resolve) => setTimeout(resolve, 20));
    });
    expect(queryClient.getQueryState(['settings'])?.status).toBe('error');

    expect(screen.getByRole('textbox', { name: 'Kana per day' })).toHaveValue('30');
    expect(screen.queryByText("Couldn't load your settings")).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled();
  });

  it('names the levels as a group and ties the hint and the error to it', async () => {
    const user = userEvent.setup();
    serveSettings();
    await openSettings();
    const levels = screen.getByRole('group', { name: 'Levels to study' });
    expect(within(levels).getAllByRole('checkbox')).toHaveLength(5);
    expect(levels).toHaveAccessibleDescription('Only used by "Pinned levels".');

    await user.click(screen.getByRole('radio', { name: /Pinned levels/ }));
    expect(levels).toHaveAccessibleDescription('New cards come only from these levels.');
    await user.click(screen.getByRole('checkbox', { name: 'N5' }));
    await user.click(screen.getByRole('button', { name: 'Save' }));

    await screen.findByText('Pick at least one level.');
    expect(levels).toHaveAccessibleDescription(
      'Pick at least one level. New cards come only from these levels.',
    );
  });

  it('ties the retention help and a server message to the retention control', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('/api/v1/settings', () => HttpResponse.json(makeSettings())),
      http.put('/api/v1/settings', () =>
        HttpResponse.json(
          {
            detail: [
              {
                loc: ['body', 'target_retention'],
                msg: 'Input should be at least 0.7',
                type: 'x',
              },
            ],
          },
          { status: 422 },
        ),
      ),
    );
    await openSettings();
    await openTab(user, 'Pace');
    const retention = screen.getByRole('group', { name: /Target retention/ });
    expect(retention).toHaveAccessibleName('Target retention: 90%');
    expect(retention).toHaveAccessibleDescription(/How often you want to remember a card/);

    await setNumber(user, 'Kana per day', '30');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByText('Input should be at least 0.7')).toBeInTheDocument();
    expect(retention).toHaveAccessibleDescription(/Input should be at least 0\.7/);
  });

  it('marks the next card and the statistics stale after a save', async () => {
    const user = userEvent.setup();
    serveSettings();
    const { queryClient } = await openSettings();
    await openTab(user, 'Pace');
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

  it('fills the type switches and the kana gate from the saved settings', async () => {
    serveSettings(
      makeSettings({
        type_enabled: { kana: true, kanji: false, vocab: true },
        kana_gate: { kanji: false, vocab: true, threshold: 0.9 },
      }),
    );
    await openSettings();

    expect(screen.getByRole('switch', { name: 'Introduce new kana' })).toBeChecked();
    expect(screen.getByRole('switch', { name: 'Introduce new kanji' })).not.toBeChecked();
    expect(screen.getByRole('switch', { name: 'Introduce new vocabulary' })).toBeChecked();
    expect(
      screen.getByRole('switch', { name: 'Wait for kana before starting kanji' }),
    ).not.toBeChecked();
    expect(
      screen.getByRole('switch', { name: 'Wait for kana before starting vocabulary' }),
    ).toBeChecked();
    expect(screen.getByRole('textbox', { name: 'Kana needed before they start' })).toHaveValue(
      '90%',
    );
  });

  it('disables the daily limit of a type that is switched off and saves the switch', async () => {
    const user = userEvent.setup();
    const puts = serveSettings();
    await openSettings();

    await user.click(screen.getByRole('switch', { name: 'Introduce new kanji' }));
    await openTab(user, 'Pace');
    expect(screen.getByRole('textbox', { name: 'Kanji per day' })).toBeDisabled();
    expect(screen.getByRole('textbox', { name: 'Kana per day' })).toBeEnabled();
    await user.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText('Settings saved')).toBeInTheDocument();
    expect(puts).toEqual([
      makeSettings({ type_enabled: { kana: true, kanji: false, vocab: true } }),
    ]);
  });

  it('shows the gate threshold only while a gate is on and sends it as a fraction', async () => {
    const user = userEvent.setup();
    const puts = serveSettings();
    await openSettings();
    expect(
      screen.queryByRole('textbox', { name: 'Kana needed before they start' }),
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole('switch', { name: 'Wait for kana before starting kanji' }));
    const threshold = await screen.findByRole('textbox', { name: 'Kana needed before they start' });
    expect(threshold).toHaveValue('80%');
    await setNumber(user, 'Kana needed before they start', '90');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText('Settings saved')).toBeInTheDocument();
    expect(puts).toEqual([
      makeSettings({ kana_gate: { kanji: true, vocab: false, threshold: 0.9 } }),
    ]);
  });

  it('will not save a kana gate while kana is switched off, and the message clears once fixed', async () => {
    const user = userEvent.setup();
    const puts = serveSettings(
      makeSettings({ kana_gate: { kanji: true, vocab: false, threshold: 0.8 } }),
    );
    await openSettings();

    await user.click(screen.getByRole('switch', { name: 'Introduce new kana' }));
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByText(KANA_GATE_MESSAGE)).toBeInTheDocument();
    expect(puts).toEqual([]);

    await user.click(screen.getByRole('switch', { name: 'Wait for kana before starting kanji' }));
    expect(screen.queryByText(KANA_GATE_MESSAGE)).not.toBeInTheDocument();
  });

  it('clears the kana gate message when Reset all tabs to recommended values is pressed', async () => {
    const user = userEvent.setup();
    const puts = serveSettings(
      makeSettings({ kana_gate: { kanji: true, vocab: false, threshold: 0.8 } }),
    );
    await openSettings();

    await user.click(screen.getByRole('switch', { name: 'Introduce new kana' }));
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByText(KANA_GATE_MESSAGE)).toBeInTheDocument();
    expect(puts).toEqual([]);

    await user.click(screen.getByRole('button', { name: 'Reset all tabs to recommended values' }));
    expect(screen.queryByText(KANA_GATE_MESSAGE)).not.toBeInTheDocument();
  });

  it('explains the disabled gate switches only while kana is switched off', async () => {
    const user = userEvent.setup();
    serveSettings();
    await openSettings();
    const hint = 'Turn on new kana above to use this.';
    expect(screen.queryByText(hint)).not.toBeInTheDocument();

    await user.click(screen.getByRole('switch', { name: 'Introduce new kana' }));
    expect(screen.getByText(hint)).toBeInTheDocument();

    await user.click(screen.getByRole('switch', { name: 'Introduce new kana' }));
    expect(screen.queryByText(hint)).not.toBeInTheDocument();
  });

  it('keeps a switched-on gate operable after kana is switched off', async () => {
    const user = userEvent.setup();
    serveSettings(makeSettings({ kana_gate: { kanji: true, vocab: false, threshold: 0.8 } }));
    await openSettings();

    await user.click(screen.getByRole('switch', { name: 'Introduce new kana' }));
    expect(
      screen.getByRole('switch', { name: 'Wait for kana before starting kanji' }),
    ).toBeEnabled();
    expect(
      screen.getByRole('switch', { name: 'Wait for kana before starting vocabulary' }),
    ).toBeDisabled();
  });

  it('shows a server 422 on the kana gate group', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('/api/v1/settings', () => HttpResponse.json(makeSettings())),
      http.put('/api/v1/settings', () =>
        HttpResponse.json(
          {
            detail: [
              { loc: ['body', 'kana_gate'], msg: 'Server says no', type: 'kana_gate_needs_kana' },
            ],
          },
          { status: 422 },
        ),
      ),
    );
    await openSettings();

    await user.click(
      screen.getByRole('switch', { name: 'Wait for kana before starting vocabulary' }),
    );
    await user.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText('Server says no')).toBeInTheDocument();
    expect(screen.queryByText("Couldn't save your settings")).not.toBeInTheDocument();
  });

  it('reveals a hidden threshold field that is invalid when Save is pressed', async () => {
    const user = userEvent.setup();
    const puts = serveSettings(
      makeSettings({ kana_gate: { kanji: true, vocab: false, threshold: 0.8 } }),
    );
    await openSettings();

    await setNumber(user, 'Kana needed before they start', '');
    await user.click(screen.getByRole('switch', { name: 'Wait for kana before starting kanji' }));
    expect(
      screen.queryByRole('textbox', { name: 'Kana needed before they start' }),
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByText('Enter a percentage from 0 to 100.')).toBeInTheDocument();
    expect(
      screen.getByRole('textbox', { name: 'Kana needed before they start' }),
    ).toBeInTheDocument();
    expect(puts).toEqual([]);
  });

  it('refills the type switches and the gate with the recommended values on Reset', async () => {
    const user = userEvent.setup();
    serveSettings(
      makeSettings({
        type_enabled: { kana: true, kanji: false, vocab: false },
        kana_gate: { kanji: true, vocab: true, threshold: 0.5 },
      }),
    );
    await openSettings();

    await user.click(screen.getByRole('button', { name: 'Reset all tabs to recommended values' }));
    expect(screen.getByRole('switch', { name: 'Introduce new kanji' })).toBeChecked();
    expect(screen.getByRole('switch', { name: 'Introduce new vocabulary' })).toBeChecked();
    expect(
      screen.getByRole('switch', { name: 'Wait for kana before starting kanji' }),
    ).not.toBeChecked();
  });
});
