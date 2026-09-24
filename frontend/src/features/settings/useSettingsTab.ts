import { useCallback } from 'react';
import { useSearchParams } from 'react-router';

import { DEFAULT_TAB, isSettingsTab, type SettingsTab } from './settingsForm';

/**
 * The selected Settings tab, kept in the `?tab=` search parameter so it survives a reload and can
 * be linked to. A missing or unknown value is the default tab. The setter takes Mantine's
 * `string | null` and ignores anything that is not a tab; it replaces the history entry so Back
 * leaves Settings instead of stepping through tabs.
 */
export function useSettingsTab(): readonly [SettingsTab, (tab: string | null) => void] {
  const [params, setParams] = useSearchParams();
  const raw = params.get('tab');
  const tab = isSettingsTab(raw) ? raw : DEFAULT_TAB;
  const setTab = useCallback(
    (next: string | null) => {
      if (isSettingsTab(next)) setParams({ tab: next }, { replace: true });
    },
    [setParams],
  );
  return [tab, setTab] as const;
}
