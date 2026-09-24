import { Button, Stack, Text, TextInput } from '@mantine/core';
import { useRef, useState } from 'react';
import type { FormEvent } from 'react';

import { cardFaces } from './cardFaces';
import { matches } from './matchAnswer';
import { ReviewCard } from './ReviewCard';
import type { ReviewModeProps } from './reviewMode';

interface Outcome {
  correct: boolean;
  typed: string;
  correctAnswer: string;
}

/** Type the answer, then see whether it was right. Mount it with a new `key` for every card. */
export function TypedMode({
  card,
  showFurigana,
  pending,
  onReveal,
  onGrade,
  onContinue,
}: ReviewModeProps) {
  const [value, setValue] = useState('');
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const continueRef = useRef<HTMLButtonElement>(null);
  const accepted = card.accepted_answers ?? [];

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (outcome !== null || pending) return;
    const correct = matches(value, accepted);
    setOutcome({ correct, typed: value, correctAnswer: accepted[0] ?? '' });
    onReveal();
    onGrade(correct ? 3 : 1);
    // Focus moves to Continue once it renders; a microtask keeps this after that render.
    queueMicrotask(() => {
      continueRef.current?.focus();
    });
  };

  const faces = cardFaces(card, { showFurigana, revealed: outcome !== null });

  return (
    <div data-review-controls>
      <ReviewCard face={faces.front} />
      <form onSubmit={submit}>
        <Stack gap="sm" mt="md">
          <TextInput
            label="Your answer"
            value={value}
            onChange={(event) => {
              setValue(event.currentTarget.value);
            }}
            disabled={outcome !== null || pending}
            autoFocus
            autoComplete="off"
          />
          {outcome === null && (
            <Button type="submit" fullWidth size="lg" disabled={pending}>
              Submit
            </Button>
          )}
        </Stack>
      </form>
      {outcome !== null && (
        <Stack gap="sm" mt="md">
          <Text fw={500} c={outcome.correct ? 'teal' : 'red'}>
            {outcome.correct ? 'Correct' : 'Not quite'}
          </Text>
          {!outcome.correct && (
            <Text size="sm">
              You typed: {outcome.typed || '(nothing)'} — Correct:{' '}
              <Text span fw={600}>
                {outcome.correctAnswer}
              </Text>
            </Text>
          )}
          <Button ref={continueRef} fullWidth size="lg" onClick={onContinue} disabled={pending}>
            Continue
          </Button>
        </Stack>
      )}
    </div>
  );
}
