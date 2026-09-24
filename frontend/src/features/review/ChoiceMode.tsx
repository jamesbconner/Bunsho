import { Button, SimpleGrid, Stack, Text } from '@mantine/core';
import { useEffect, useRef, useState } from 'react';

import type { CardView } from '../../api/endpoints';
import { cardFaces } from './cardFaces';
import classes from './review.module.css';
import { ReviewCard } from './ReviewCard';
import type { ReviewModeProps } from './reviewMode';
import { useChoiceShortcuts } from './useChoiceShortcuts';

/** Directions whose answer is Japanese text (a glyph or a reading), so the options are too. */
const JAPANESE_ANSWER_DIRECTIONS: readonly CardView['direction'][] = [
  'sound_to_glyph',
  'kanji_to_reading',
  'meaning_to_kanji',
  'recall',
];

/** Pick the answer from four options. Mount it with a new `key` for every card. */
export function ChoiceMode({
  card,
  showFurigana,
  pending,
  onReveal,
  onGrade,
  onContinue,
}: ReviewModeProps) {
  const [pickedIndex, setPickedIndex] = useState<number | null>(null);
  const continueRef = useRef<HTMLButtonElement>(null);
  const choices = card.choices ?? [];
  const correctChoice = card.accepted_answers?.[0] ?? choices[0];
  const picked = pickedIndex !== null;
  const chosenText = pickedIndex === null ? null : choices[pickedIndex];
  const isCorrect = picked && chosenText === correctChoice;
  const japaneseChoices = JAPANESE_ANSWER_DIRECTIONS.includes(card.direction);

  const pick = (index: number) => {
    if (picked || pending) return;
    setPickedIndex(index);
    onReveal();
    onGrade(choices[index] === correctChoice ? 3 : 1);
  };

  useChoiceShortcuts({
    picked,
    pending,
    count: choices.length,
    onPick: pick,
    onContinue,
  });

  useEffect(() => {
    if (picked) continueRef.current?.focus();
  }, [picked]);

  const faces = cardFaces(card, { showFurigana, revealed: picked });

  return (
    <div data-review-controls>
      <ReviewCard face={faces.front} />
      <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="xs" mt="md">
        {choices.map((choice, index) => (
          <Button
            key={choice}
            size="lg"
            classNames={japaneseChoices ? { root: classes.choiceJapanese } : undefined}
            variant={picked && choice === correctChoice ? 'filled' : 'light'}
            color={picked && index === pickedIndex && !isCorrect ? 'red' : undefined}
            disabled={picked || pending}
            aria-keyshortcuts={String(index + 1)}
            onClick={() => {
              pick(index);
            }}
          >
            <span className={classes.key} aria-hidden="true">
              {index + 1}
            </span>
            <span lang={japaneseChoices ? 'ja' : undefined}>{choice}</span>
          </Button>
        ))}
      </SimpleGrid>
      {picked && (
        <Stack gap="sm" mt="md">
          <Text fw={500} c={isCorrect ? 'teal' : 'red'}>
            {isCorrect ? 'Correct' : 'Not quite'}
          </Text>
          <Button ref={continueRef} fullWidth size="lg" onClick={onContinue} disabled={pending}>
            Continue
          </Button>
        </Stack>
      )}
    </div>
  );
}
