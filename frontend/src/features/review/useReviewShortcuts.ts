import { useEffect } from 'react';

import type { Grade } from '../../api/endpoints';

const GRADE_KEYS: Readonly<Record<string, Grade>> = { '1': 1, '2': 2, '3': 3, '4': 4 };

/**
 * Whether a key press belongs to the review: it happened on the page itself or inside the review
 * controls, not in a text field, a link, or the header switch (which keep their own keys).
 */
export function isForReview(target: EventTarget | null): boolean {
  if (target === document.body || target === document.documentElement) return true;
  return target instanceof Element && target.closest('[data-review-controls]') !== null;
}

interface Shortcuts {
  revealed: boolean;
  pending: boolean;
  onFlip: () => void;
  onGrade: (grade: Grade) => void;
}

/**
 * Space or Enter flips the card; 1 to 4 grade it once it is flipped. Ignored with a modifier key,
 * while an input method is composing, for auto-repeated keys (holding a key must not grade
 * several cards) and while an answer is being saved.
 */
export function useReviewShortcuts({ revealed, pending, onFlip, onGrade }: Shortcuts): void {
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.repeat || event.isComposing) return;
      if (event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
      if (event.defaultPrevented || pending || !isForReview(event.target)) return;

      if (event.key === ' ' || event.key === 'Enter') {
        if (!revealed) {
          event.preventDefault();
          onFlip();
        }
        return;
      }
      const grade = GRADE_KEYS[event.key];
      if (grade !== undefined && revealed) {
        event.preventDefault();
        onGrade(grade);
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [revealed, pending, onFlip, onGrade]);
}
