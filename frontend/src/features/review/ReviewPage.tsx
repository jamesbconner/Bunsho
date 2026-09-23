import {
  Alert,
  Button,
  Group,
  Skeleton,
  Stack,
  Switch,
  Text,
  Title,
  VisuallyHidden,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useCallback, useEffect, useRef, useState } from 'react';

import type { AnswerRequest, CardView, Grade, ReviewCounts } from '../../api/endpoints';
import { ApiError, messageFor } from '../../api/errors';
import { useAnswerReview, useNextReview } from '../../api/queries';
import { ChoiceMode } from './ChoiceMode';
import { FlipMode } from './FlipMode';
import { useFuriganaPreference } from './useFuriganaPreference';
import { ReviewDone, ReviewNotBuilt } from './ReviewFinished';
import { TypedMode } from './TypedMode';

/** The API accepts a duration up to one hour. */
const MAX_DURATION_MS = 3_600_000;

/** A different card, or the same card after another review: a new key remounts the mode. */
function cardKey(card: CardView): string {
  return `${card.item_id}|${card.direction}|${card.expected_last_review ?? 'new'}`;
}

const MODE_COMPONENTS = {
  flip: FlipMode,
  typed: TypedMode,
  multiple_choice: ChoiceMode,
} as const;

function isStale(error: unknown): boolean {
  return error instanceof ApiError && error.status === 409;
}

function isNotBuilt(error: unknown): boolean {
  return error instanceof ApiError && error.status === 503;
}

function total(counts: ReviewCounts['due']): number {
  return counts.kana + counts.kanji + counts.vocab;
}

/**
 * The sentence a screen reader hears. Static text only: nothing here changes while it is read.
 * Empty while a failed save shows its alert.
 */
function announcement(state: {
  hasData: boolean;
  card: CardView | null;
  saving: boolean;
  failed: boolean;
  revealed: boolean;
}): string {
  if (!state.hasData) return '';
  if (state.card === null) return 'Nothing due right now';
  if (state.saving) return 'Saving answer';
  // A failed save is announced by its own alert; "Answer shown" would read like success.
  if (state.failed) return '';
  return state.revealed ? 'Answer shown' : 'Card shown';
}

/** The study session: one card at a time, flip, grade, next. */
export function ReviewPage() {
  const next = useNextReview();
  const answer = useAnswerReview();
  const [showFurigana, setShowFurigana] = useFuriganaPreference();
  const [revealedKey, setRevealedKey] = useState<string | null>(null);
  const shownAt = useRef(0);

  const { refetch } = next;
  const { mutate: sendAnswer, reset: resetAnswer } = answer;

  const data = next.data;
  const freshCard = data?.card ?? null;
  const [heldCard, setHeldCard] = useState<CardView | null>(null);
  const card = heldCard ?? freshCard;
  const key = card === null ? null : cardKey(card);

  // The clock for `duration_ms` starts when a card is put on screen.
  useEffect(() => {
    shownAt.current = Date.now();
  }, [key]);

  const reveal = useCallback(() => {
    setRevealedKey(key);
  }, [key]);

  // One send path for the first grade and the resend, so both handle a 409 the same way.
  const submit = useCallback(
    (variables: AnswerRequest) => {
      sendAnswer(variables, {
        onError: (error) => {
          if (!isStale(error)) return;
          // The card changed elsewhere (another tab or device): drop it and load what is next.
          notifications.show({ message: 'That card changed elsewhere: loading the next one.' });
          void refetch().finally(resetAnswer);
        },
      });
    },
    [sendAnswer, refetch, resetAnswer],
  );

  const grade = useCallback(
    (value: Grade) => {
      if (freshCard === null) return;
      const duration = Math.min(Math.max(Date.now() - shownAt.current, 0), MAX_DURATION_MS);
      if (freshCard.mode !== 'flip') setHeldCard(freshCard);
      submit({
        item_id: freshCard.item_id,
        direction: freshCard.direction,
        grade: value,
        expected_last_review: freshCard.expected_last_review,
        duration_ms: duration,
      });
    },
    [freshCard, submit],
  );

  const continueToNext = useCallback(() => {
    setHeldCard(null);
  }, []);

  const busy = answer.isPending || next.isFetching;
  const answerFailed = answer.isError && !isStale(answer.error);

  let body;
  if (next.isPending) {
    body = <Skeleton height={240} />;
  } else if (next.isError) {
    body = isNotBuilt(next.error) ? (
      <ReviewNotBuilt />
    ) : (
      <Alert color="red" title="Couldn't load the next card">
        <Text size="sm">{messageFor(next.error)}</Text>
        <Button
          mt="sm"
          size="xs"
          onClick={() => {
            void refetch();
          }}
        >
          Try again
        </Button>
      </Alert>
    );
  } else if (card === null) {
    body = <ReviewDone data={next.data} />;
  } else {
    const effectiveMode =
      (card.mode === 'typed' && card.accepted_answers === null) ||
      (card.mode === 'multiple_choice' && card.choices === null)
        ? 'flip'
        : card.mode;
    const Mode = MODE_COMPONENTS[effectiveMode];
    body = (
      <Stack gap="md">
        <Mode
          key={key}
          card={card}
          showFurigana={showFurigana}
          pending={busy}
          onReveal={reveal}
          onGrade={grade}
          onContinue={continueToNext}
        />
        {answerFailed && (
          <Alert color="red" title="Couldn't save your answer">
            <Text size="sm">{messageFor(answer.error)}</Text>
            <Button
              mt="sm"
              size="xs"
              disabled={busy}
              onClick={() => {
                if (answer.variables !== undefined) submit(answer.variables);
              }}
            >
              Try again
            </Button>
          </Alert>
        )}
      </Stack>
    );
  }

  return (
    <Stack gap="md" maw={720} mx="auto">
      <Group justify="space-between" align="center">
        <Title order={2}>Study</Title>
        <Switch
          label="Show furigana"
          checked={showFurigana}
          onChange={(event) => {
            setShowFurigana(event.currentTarget.checked);
          }}
        />
      </Group>
      {data !== undefined && (
        <Text size="sm" c="dimmed">
          {total(data.counts.due)} due · {total(data.counts.new_remaining)} new available
        </Text>
      )}
      <VisuallyHidden role="status" aria-live="polite" aria-atomic>
        {announcement({
          hasData: data !== undefined && !next.isError,
          card,
          saving: answer.isPending,
          failed: answerFailed,
          revealed: key !== null && revealedKey === key,
        })}
      </VisuallyHidden>
      {body}
    </Stack>
  );
}
