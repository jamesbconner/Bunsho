import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { renderWithProviders } from '../test/render';
import { ColorSchemeToggle } from './ColorSchemeToggle';

describe('ColorSchemeToggle', () => {
  it('offers light, dark and auto, and switches between them', async () => {
    renderWithProviders(<ColorSchemeToggle />);
    const user = userEvent.setup();
    // The test provider starts on Mantine's default scheme (light); the app itself starts on auto.
    expect(screen.getByRole('radio', { name: 'Light' })).toBeChecked();
    await user.click(screen.getByText('Dark'));
    expect(screen.getByRole('radio', { name: 'Dark' })).toBeChecked();
    await user.click(screen.getByText('Auto'));
    expect(screen.getByRole('radio', { name: 'Auto' })).toBeChecked();
  });
});
