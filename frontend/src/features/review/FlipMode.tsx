import { Button } from '@mantine/core';
import { useCallback, useEffect, useRef, useState } from 'react';

import { cardFaces } from './cardFaces';
import { GradeBar } from './GradeBar';
import { ReviewCard } from './ReviewCard';
import type { ReviewModeProps } from './reviewMode';
import { useReviewShortcuts } from './useReviewShortcuts';

/** Flip the card, then grade yourself. Mount it with a new `key` for every card. */
export function FlipMode({ card, showFurigana, pending, onReveal, onGrade }: ReviewModeProps) {
  const [revealed, setRevealed] = useState(false);
  const flipRef = useRef<HTMLButtonElement>(null);
  const gradesRef = useRef<HTMLDivElement>(null);

  const flip = useCallback(() => {
    setRevealed(true);
    onReveal();
  }, [onReveal]);

  useReviewShortcuts({ revealed, pending, onFlip: flip, onGrade });

  useEffect(() => {
    flipRef.current?.focus();
  }, []);
  useEffect(() => {
    if (revealed) gradesRef.current?.focus();
  }, [revealed]);

  const faces = cardFaces(card, { showFurigana, revealed });

  return (
    <div data-review-controls>
      <ReviewCard face={faces.front} />
      {revealed ? (
        <>
          <ReviewCard face={faces.back} answer />
          <GradeBar
            intervals={card.intervals}
            disabled={pending}
            onGrade={onGrade}
            groupRef={gradesRef}
          />
        </>
      ) : (
        <Button ref={flipRef} fullWidth size="lg" onClick={flip} aria-keyshortcuts="Space Enter">
          Show answer
        </Button>
      )}
    </div>
  );
}
