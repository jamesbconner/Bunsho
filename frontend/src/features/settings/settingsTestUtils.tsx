import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import type { InitialEntry } from 'react-router';

import type { ReviewSettings } from '../../api/endpoints';
import { makeSettings } from '../../test/fixtures';
import { renderWithProviders } from '../../test/render';
import { server } from '../../test/server';
import { SettingsPage } from './SettingsPage';

export type User = ReturnType<typeof userEvent.setup>;

/** Serve the settings and record every PUT body; the server echoes the document it was sent. */
export function serveSettings(initial: ReviewSettings = makeSettings()) {
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

export async function openSettings(initialEntries: InitialEntry[] = ['/settings']) {
  const view = renderWithProviders(<SettingsPage />, { initialEntries });
  await screen.findByRole('button', { name: 'Save' });
  return view;
}

/** Click the named tab ("Pace"); the accessible name may gain " (has errors)". */
export async function openTab(user: User, name: string) {
  await user.click(screen.getByRole('tab', { name: new RegExp(`^${name}`) }));
}

export async function setNumber(user: User, name: string, value: string) {
  const input = screen.getByRole('textbox', { name });
  await user.clear(input);
  if (value !== '') await user.type(input, value);
}
