import { useEffect } from 'react';

import { isForReview } from './useReviewShortcuts';

interface ChoiceShortcuts {
  /** An option has already been picked (feedback is showing). */
  picked: boolean;
  pending: boolean;
  count: number;
  onPick: (index: number) => void;
  onContinue: () => void;
}

/**
 * Before a pick, digit keys 1 through `count` choose an option. After a pick, Space or Enter
 * continues. Same guards as `useReviewShortcuts`: modifier keys, auto-repeated keydowns, IME
 * composition, and input outside the review controls are all ignored, as is any input while
 * pending.
 */
export function useChoiceShortcuts({
  picked,
  pending,
  count,
  onPick,
  onContinue,
}: ChoiceShortcuts): void {
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.repeat || event.isComposing) return;
      if (event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
      if (event.defaultPrevented || pending || !isForReview(event.target)) return;

      if (!picked) {
        const index = Number(event.key) - 1;
        if (Number.isInteger(index) && index >= 0 && index < count) {
          event.preventDefault();
          onPick(index);
        }
        return;
      }
      if (event.key === ' ' || event.key === 'Enter') {
        event.preventDefault();
        onContinue();
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [picked, pending, count, onPick, onContinue]);
}
