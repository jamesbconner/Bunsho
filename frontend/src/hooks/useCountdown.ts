import { useCallback, useState, useSyncExternalStore } from 'react';

/** Whole seconds left until `deadline` (a Date.now() timestamp); re-renders twice a second. */
export function useSecondsUntil(deadline: number | null): number {
  const subscribe = useCallback(
    (onChange: () => void) => {
      if (deadline === null) return () => {};
      const timer = setInterval(onChange, 500);
      return () => {
        clearInterval(timer);
      };
    },
    [deadline],
  );
  return useSyncExternalStore(subscribe, () =>
    deadline === null ? 0 : Math.max(0, Math.ceil((deadline - Date.now()) / 1000)),
  );
}

/** A countdown started on demand: `remaining` is 0 until `start(seconds)` is called. */
export function useCountdown(): { remaining: number; start: (seconds: number) => void } {
  const [deadline, setDeadline] = useState<number | null>(null);
  const remaining = useSecondsUntil(deadline);
  const start = useCallback((seconds: number) => {
    setDeadline(Date.now() + seconds * 1000);
  }, []);
  return { remaining, start };
}
