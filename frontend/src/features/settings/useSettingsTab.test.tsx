import { act, renderHook } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter, useLocation, useNavigationType } from 'react-router';
import { describe, expect, it } from 'vitest';

import { useSettingsTab } from './useSettingsTab';

function setup(initial: string) {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <MemoryRouter initialEntries={[initial]}>{children}</MemoryRouter>
  );
  return renderHook(
    () => ({
      tab: useSettingsTab(),
      location: useLocation(),
      navigationType: useNavigationType(),
    }),
    { wrapper },
  );
}

describe('useSettingsTab', () => {
  it.each([
    ['/settings', 'learning'],
    ['/settings?tab=pace', 'pace'],
    ['/settings?tab=system', 'system'],
    ['/settings?tab=', 'learning'],
    ['/settings?tab=admin', 'learning'],
    ['/settings?tab=PACE', 'learning'],
    ['/settings?tab=pace&tab=system', 'pace'],
    ['/settings?other=1', 'learning'],
  ])('reads %s as the %s tab', (url, expected) => {
    const { result } = setup(url);
    expect(result.current.tab[0]).toBe(expected);
  });

  it('writes the tab to the URL, replacing the history entry', () => {
    const { result } = setup('/settings');
    act(() => {
      result.current.tab[1]('reviewing');
    });
    expect(result.current.tab[0]).toBe('reviewing');
    expect(result.current.location.search).toBe('?tab=reviewing');
    expect(result.current.navigationType).toBe('REPLACE');
  });

  it('ignores a value that is not a tab', () => {
    const { result } = setup('/settings?tab=pace');
    act(() => {
      result.current.tab[1]('nonsense');
      result.current.tab[1](null);
    });
    expect(result.current.tab[0]).toBe('pace');
    expect(result.current.location.search).toBe('?tab=pace');
  });
});
