import { useCallback, useState } from 'react';

/** Where the "show furigana on the front" choice is remembered: this browser only. */
export const FURIGANA_KEY = 'bunsho.show_furigana';

function read(): boolean {
  try {
    return window.localStorage.getItem(FURIGANA_KEY) === 'true';
  } catch {
    return false;
  }
}

/** The furigana switch and its setter. Blocked storage means "not remembered", never an error. */
export function useFuriganaPreference(): [boolean, (value: boolean) => void] {
  const [value, setValue] = useState(read);
  const update = useCallback((next: boolean) => {
    setValue(next);
    try {
      window.localStorage.setItem(FURIGANA_KEY, String(next));
    } catch {
      // Not remembered; the switch still works for this visit.
    }
  }, []);
  return [value, update];
}
