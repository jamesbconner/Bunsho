import { useCallback, useEffect, useRef } from 'react';

/**
 * Give focus back to the field that had it once `locked` ends.
 *
 * A locked form is disabled, and a disabled field loses focus. Call the returned function when the
 * lock starts (it remembers the focused element); when `locked` turns false the element gets focus
 * again, unless something else has taken it in the meantime.
 */
export function useRestoreFocus(locked: boolean): () => void {
  const remembered = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (locked) return;
    const target = remembered.current;
    remembered.current = null;
    if (target?.isConnected === true && document.activeElement === document.body) target.focus();
  }, [locked]);

  return useCallback(() => {
    remembered.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
  }, []);
}
