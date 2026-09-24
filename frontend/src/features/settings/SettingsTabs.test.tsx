import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { useLocation } from 'react-router';
import { beforeEach, describe, expect, it } from 'vitest';

import { session } from '../../auth/session';
import { makeBuildStatus, makeSettings } from '../../test/fixtures';
import { renderWithProviders } from '../../test/render';
import { server } from '../../test/server';
import { SettingsPage } from './SettingsPage';
import { openSettings, openTab, serveSettings, setNumber } from './settingsTestUtils';

function tabNamed(name: string | RegExp) {
  return screen.getByRole('tab', { name });
}

/** Serve the System tab's reads and count how often each is asked. */
function serveSystem(latest: unknown = null) {
  const calls = { health: 0, summary: 0, checks: 0, build: 0 };
  server.use(
    http.get('/api/v1/health', () => {
      calls.health += 1;
      return HttpResponse.json({ status: 'ok', version: '1.2.0', components: {} });
    }),
    http.get('/api/v1/content/summary', () => {
      calls.summary += 1;
      return HttpResponse.json({
        built: true,
        kana: 1,
        kanji: 1,
        vocab: 1,
        unleveled_kanji: 0,
        kanji_by_level: {},
        vocab_by_level: {},
        meta: {},
      });
    }),
    http.get('/api/v1/admin/config-check', () => {
      calls.checks += 1;
      return HttpResponse.json({ ok: true, checks: [] });
    }),
    http.get('/api/v1/admin/content/build', () => {
      calls.build += 1;
      return latest === null
        ? HttpResponse.json({ detail: 'no build has run yet' }, { status: 404 })
        : HttpResponse.json(latest);
    }),
  );
  return calls;
}

function LocationProbe() {
  return <output data-testid="location">{useLocation().search}</output>;
}

describe('Settings tabs', () => {
  beforeEach(() => {
    session.clear();
    session.setTokens({ access_token: 'a1', refresh_token: 'r1', expires_in: 900 });
  });

  it('shows four tabs with Learning path selected by default', async () => {
    serveSettings();
    await openSettings();
    expect(screen.getAllByRole('tab').map((tab) => tab.textContent)).toEqual([
      'Learning path',
      'Pace',
      'Reviewing',
      'System',
    ]);
    expect(tabNamed('Learning path')).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tablist', { name: 'Settings sections' })).toBeInTheDocument();
  });

  it('selects the tab named in the URL, and falls back on an unknown one', async () => {
    serveSettings();
    await openSettings(['/settings?tab=pace']);
    expect(tabNamed('Pace')).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('textbox', { name: 'Kana per day' })).toBeInTheDocument();
  });

  it('opens Learning path for a tab name it does not know', async () => {
    serveSettings();
    await openSettings(['/settings?tab=admin']);
    expect(tabNamed('Learning path')).toHaveAttribute('aria-selected', 'true');
  });

  it('writes the chosen tab to the URL', async () => {
    const user = userEvent.setup();
    serveSettings();
    renderWithProviders(
      <>
        <SettingsPage />
        <LocationProbe />
      </>,
      { initialEntries: ['/settings'] },
    );
    await screen.findByRole('button', { name: 'Save' });
    await openTab(user, 'Reviewing');
    expect(screen.getByTestId('location')).toHaveTextContent('?tab=reviewing');
  });

  it('keeps an edit when the person switches tabs and back', async () => {
    const user = userEvent.setup();
    serveSettings();
    await openSettings();
    await openTab(user, 'Pace');
    await setNumber(user, 'Kana per day', '30');
    await openTab(user, 'Reviewing');
    await openTab(user, 'Pace');
    expect(screen.getByRole('textbox', { name: 'Kana per day' })).toHaveValue('30');
    expect(screen.getByText('Unsaved changes')).toBeInTheDocument();
  });

  it('saves the edits of every tab in one request', async () => {
    const user = userEvent.setup();
    const puts = serveSettings();
    await openSettings();
    await openTab(user, 'Pace');
    await setNumber(user, 'Kana per day', '30');
    await openTab(user, 'Reviewing');
    await user.selectOptions(screen.getByLabelText('Kana review mode'), 'Typed answer');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    await screen.findByText('Settings saved');
    expect(puts).toEqual([
      makeSettings({ new_limits: { kana: 30, kanji: 15, vocab: 20 }, kana_mode: 'typed' }),
    ]);
  });

  it('has no Save or Reset on the System tab, and its button cannot submit the form', async () => {
    const user = userEvent.setup();
    const puts = serveSettings();
    serveSystem();
    await openSettings();
    await openTab(user, 'System');
    await screen.findByRole('region', { name: 'Server' });
    expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /Reset all tabs to recommended values/ }),
    ).not.toBeInTheDocument();
    // Content is built, so the button reads "Rebuild content" and opens a confirmation; either way
    // it must not submit the settings form.
    await user.click(await screen.findByRole('button', { name: 'Rebuild content' }));
    expect(await screen.findByText('Rebuild content?')).toBeInTheDocument();
    expect(puts).toEqual([]);
  });

  it('does not ask the System endpoints until the System tab is opened', async () => {
    const user = userEvent.setup();
    serveSettings();
    const calls = serveSystem();
    await openSettings();
    await openTab(user, 'Pace');
    expect(calls).toEqual({ health: 0, summary: 0, checks: 0, build: 0 });
    await openTab(user, 'System');
    await screen.findByRole('region', { name: 'Server' });
    expect(calls.health).toBeGreaterThan(0);
    expect(calls.summary).toBeGreaterThan(0);
  });

  it('shows a running build again after leaving the System tab and coming back', async () => {
    const user = userEvent.setup();
    serveSettings();
    serveSystem(makeBuildStatus());
    await openSettings();
    await openTab(user, 'System');
    expect(await screen.findByText('Reading the vocabulary deck')).toBeInTheDocument();
    await openTab(user, 'Pace');
    expect(screen.queryByText('Reading the vocabulary deck')).not.toBeInTheDocument();
    await openTab(user, 'System');
    expect(await screen.findByText('Reading the vocabulary deck')).toBeInTheDocument();
  });

  it('says why a daily limit is greyed out, pointing at the tab that holds the switch', async () => {
    const user = userEvent.setup();
    serveSettings();
    await openSettings();
    await user.click(screen.getByRole('switch', { name: 'Introduce new kanji' }));
    await openTab(user, 'Pace');
    expect(screen.getByRole('textbox', { name: 'Kanji per day' })).toBeDisabled();
    expect(screen.getAllByText('Switched off in Learning path.')).toHaveLength(1);
  });
});

describe('Settings tabs: errors on another tab', () => {
  beforeEach(() => {
    session.clear();
    session.setTokens({ access_token: 'a1', refresh_token: 'r1', expires_in: 900 });
  });

  it('marks the tab, jumps to it and focuses the field when Save finds a bad value', async () => {
    const user = userEvent.setup();
    const puts = serveSettings();
    await openSettings();
    await openTab(user, 'Pace');
    await setNumber(user, 'Kana per day', '');
    await openTab(user, 'Learning path');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      expect(tabNamed(/^Pace/)).toHaveAttribute('aria-selected', 'true');
    });
    expect(tabNamed('Pace (has errors)')).toBeInTheDocument();
    expect(tabNamed('Learning path')).not.toHaveAccessibleName(/has errors/);
    await waitFor(() => {
      expect(screen.getByRole('textbox', { name: 'Kana per day' })).toHaveFocus();
    });
    expect(puts).toEqual([]);
  });

  it('focuses the invalid field when Save is pressed on the tab that holds it', async () => {
    const user = userEvent.setup();
    const puts = serveSettings();
    await openSettings();
    await openTab(user, 'Pace');
    await setNumber(user, 'Kana per day', '');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText(/^Enter/)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole('textbox', { name: 'Kana per day' })).toHaveFocus();
    });
    expect(tabNamed('Pace (has errors)')).toHaveAttribute('aria-selected', 'true');
    expect(puts).toEqual([]);
  });

  it('marks a tab while the person is on another one, and clears the mark once fixed', async () => {
    const user = userEvent.setup();
    serveSettings();
    await openSettings();
    await openTab(user, 'Pace');
    await setNumber(user, 'Kana per day', '');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    await openTab(user, 'Reviewing');
    expect(tabNamed('Pace (has errors)')).toBeInTheDocument();

    await openTab(user, 'Pace');
    await setNumber(user, 'Kana per day', '5');
    expect(tabNamed('Pace')).toBeInTheDocument();
  });

  it('jumps to the first errored tab in tab order when several have errors', async () => {
    const user = userEvent.setup();
    serveSettings();
    await openSettings();
    // Gate on first (its switch is disabled once kana is off), then kana off: the Learning-path error.
    await user.click(screen.getByRole('switch', { name: 'Wait for kana before starting kanji' }));
    await user.click(screen.getByRole('switch', { name: 'Introduce new kana' }));
    // Add a Pace error too; Learning path must still win.
    await openTab(user, 'Pace');
    await setNumber(user, 'Kanji per day', '');
    await openTab(user, 'Reviewing');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => {
      expect(tabNamed(/^Learning path/)).toHaveAttribute('aria-selected', 'true');
    });
    expect(tabNamed('Learning path (has errors)')).toBeInTheDocument();
    expect(tabNamed('Pace (has errors)')).toBeInTheDocument();
  });

  it('shows the message of a server 422 on a review-mode field and jumps to its tab', async () => {
    const user = userEvent.setup();
    serveSettings();
    server.use(
      http.put('/api/v1/settings', () =>
        HttpResponse.json(
          {
            detail: [
              { loc: ['body', 'kana_mode'], msg: 'Not an allowed mode', type: 'value_error' },
            ],
          },
          { status: 422 },
        ),
      ),
    );
    await openSettings();
    await openTab(user, 'Reviewing');
    await user.selectOptions(screen.getByLabelText('Kana review mode'), 'Typed answer');
    await openTab(user, 'Learning path');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      expect(tabNamed(/^Reviewing/)).toHaveAttribute('aria-selected', 'true');
    });
    expect(tabNamed('Reviewing (has errors)')).toBeInTheDocument();
    expect(screen.getByText('Not an allowed mode')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByLabelText('Kana review mode')).toHaveFocus();
    });
  });

  it('focuses the study-day select when the server rejects the rollover hour', async () => {
    const user = userEvent.setup();
    serveSettings();
    server.use(
      http.put('/api/v1/settings', () =>
        HttpResponse.json(
          {
            detail: [{ loc: ['body', 'rollover_hour'], msg: 'Not an hour', type: 'value_error' }],
          },
          { status: 422 },
        ),
      ),
    );
    await openSettings();
    await openTab(user, 'Pace');
    await user.selectOptions(screen.getByLabelText('A new study day starts at'), '6:00');
    await openTab(user, 'Reviewing');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      expect(tabNamed(/^Pace/)).toHaveAttribute('aria-selected', 'true');
    });
    expect(await screen.findByText('Not an hour')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByLabelText('A new study day starts at')).toHaveFocus();
    });
  });

  it('focuses the first Kana-first switch when the gate error is on Learning path', async () => {
    const user = userEvent.setup();
    serveSettings();
    await openSettings();
    await user.click(screen.getByRole('switch', { name: 'Wait for kana before starting kanji' }));
    await user.click(screen.getByRole('switch', { name: 'Introduce new kana' }));
    await openTab(user, 'Reviewing');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      expect(tabNamed(/^Learning path/)).toHaveAttribute('aria-selected', 'true');
    });
    await waitFor(() => {
      expect(
        screen.getByRole('switch', { name: 'Wait for kana before starting kanji' }),
      ).toHaveFocus();
    });
  });

  it('focuses the selected tab when the only Kana-first switch that is on is not the first', async () => {
    const user = userEvent.setup();
    serveSettings();
    await openSettings();
    await user.click(
      screen.getByRole('switch', { name: 'Wait for kana before starting vocabulary' }),
    );
    await user.click(screen.getByRole('switch', { name: 'Introduce new kana' }));
    // The kanji switch is now greyed out, so it cannot take focus.
    expect(
      screen.getByRole('switch', { name: 'Wait for kana before starting kanji' }),
    ).toBeDisabled();
    await openTab(user, 'Reviewing');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      expect(tabNamed('Learning path (has errors)')).toHaveFocus();
    });
    expect(tabNamed('Learning path (has errors)')).toHaveAttribute('aria-selected', 'true');
  });

  it('focuses the selected tab when the error is on a control that cannot take focus', async () => {
    const user = userEvent.setup();
    serveSettings(makeSettings({ new_card_policy: 'pinned_levels' }));
    await openSettings();
    await user.click(screen.getByRole('checkbox', { name: 'N5' }));
    await openTab(user, 'Reviewing');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      expect(tabNamed('Learning path (has errors)')).toHaveFocus();
    });
    expect(screen.getByText('Pick at least one level.')).toBeInTheDocument();
  });

  it('focuses the first errored field that can take focus, not just the first recorded error', async () => {
    const user = userEvent.setup();
    serveSettings(makeSettings({ new_card_policy: 'pinned_levels' }));
    await openSettings();
    // active_levels is recorded before the mastery threshold, but only the threshold is an input.
    await user.click(screen.getByRole('checkbox', { name: 'N5' }));
    await user.click(screen.getByRole('radio', { name: /Mastery unlock/ }));
    await setNumber(user, 'Mastery needed to unlock the next level', '');
    await openTab(user, 'Reviewing');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      expect(screen.getByRole('textbox', { name: /Mastery needed/ })).toHaveFocus();
    });
    expect(screen.getByText('Pick at least one level.')).toBeInTheDocument();
  });

  it('clears the mark of a single tab when Reset refills the form', async () => {
    const user = userEvent.setup();
    serveSettings();
    await openSettings();
    await openTab(user, 'Pace');
    await setNumber(user, 'Kana per day', '');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(tabNamed('Pace (has errors)')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Reset all tabs to recommended values' }));
    expect(tabNamed('Pace')).toBeInTheDocument();
    expect(within(screen.getByRole('tablist')).queryByText(/has errors/)).not.toBeInTheDocument();
  });

  it('clears every tab mark and refills every tab when Reset is pressed on a third tab', async () => {
    const user = userEvent.setup();
    serveSettings();
    await openSettings();
    // The Pace error first: turning kana off disables the Kana per day field.
    await openTab(user, 'Pace');
    await setNumber(user, 'Kana per day', '');
    // Gate on first (its switch is disabled once kana is off), then kana off: the Learning-path error.
    await openTab(user, 'Learning path');
    await user.click(screen.getByRole('switch', { name: 'Wait for kana before starting kanji' }));
    await user.click(screen.getByRole('switch', { name: 'Introduce new kana' }));
    await openTab(user, 'Reviewing');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => {
      expect(tabNamed(/^Learning path/)).toHaveAttribute('aria-selected', 'true');
    });
    expect(tabNamed('Learning path (has errors)')).toBeInTheDocument();
    expect(tabNamed('Pace (has errors)')).toBeInTheDocument();

    await openTab(user, 'Reviewing');
    await user.click(screen.getByRole('button', { name: 'Reset all tabs to recommended values' }));

    expect(tabNamed('Learning path')).toBeInTheDocument();
    expect(tabNamed('Pace')).toBeInTheDocument();
    expect(within(screen.getByRole('tablist')).queryByText(/has errors/)).not.toBeInTheDocument();
    await openTab(user, 'Pace');
    expect(screen.getByRole('textbox', { name: 'Kana per day' })).toHaveValue('20');
    await openTab(user, 'Learning path');
    expect(screen.getByRole('switch', { name: 'Introduce new kana' })).toBeChecked();
    expect(
      screen.getByRole('switch', { name: 'Wait for kana before starting kanji' }),
    ).not.toBeChecked();
  });
});
