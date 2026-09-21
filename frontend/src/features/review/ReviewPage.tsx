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

import type { CardView, Grade, ReviewCounts } from '../../api/endpoints';
import { ApiError, messageFor } from '../../api/errors';
import { useAnswerReview, useNextReview } from '../../api/queries';
import { FlipMode } from './FlipMode';
import { useFuriganaPreference } from './useFuriganaPreference';
import { ReviewDone, ReviewNotBuilt } from './ReviewFinished';

/** The API accepts a duration up to one hour. */
const MAX_DURATION_MS = 3_600_000;

/** A different card, or the same card after another review: a new key remounts the mode. */
function cardKey(card: CardView): string {
  return `${card.item_id}|${card.direction}|${card.expected_last_review ?? 'new'}`;
}

function isStale(error: unknown): boolean {
  return error instanceof ApiError && error.status === 409;
}

function isNotBuilt(error: unknown): boolean {
  return error instanceof ApiError && error.status === 503;
}

function total(counts: ReviewCounts['due']): number {
  return counts.kana + counts.kanji + counts.vocab;
}

/** The sentence a screen reader hears. Static text only: nothing here changes while it is read. */
function announcement(state: {
  hasData: boolean;
  card: CardView | null;
  saving: boolean;
  revealed: boolean;
}): string {
  if (!state.hasData) return '';
  if (state.card === null) return 'Nothing due right now';
  if (state.saving) return 'Saving answer';
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
  const card = data?.card ?? null;
  const key = card === null ? null : cardKey(card);

  // The clock for `duration_ms` starts when a card is put on screen.
  useEffect(() => {
    shownAt.current = Date.now();
  }, [key]);

  const reveal = useCallback(() => {
    setRevealedKey(key);
  }, [key]);

  const grade = useCallback(
    (value: Grade) => {
      if (card === null) return;
      const duration = Math.min(Math.max(Date.now() - shownAt.current, 0), MAX_DURATION_MS);
      sendAnswer(
        {
          item_id: card.item_id,
          direction: card.direction,
          grade: value,
          expected_last_review: card.expected_last_review,
          duration_ms: duration,
        },
        {
          onError: (error) => {
            if (!isStale(error)) return;
            // The card changed elsewhere (another tab or device): drop it and load what is next.
            notifications.show({ message: 'That card changed elsewhere: loading the next one.' });
            void refetch().finally(resetAnswer);
          },
        },
      );
    },
    [card, sendAnswer, refetch, resetAnswer],
  );

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
    body = (
      <Stack gap="md">
        <FlipMode
          key={key}
          card={card}
          showFurigana={showFurigana}
          pending={busy}
          onReveal={reveal}
          onGrade={grade}
        />
        {answerFailed && (
          <Alert color="red" title="Couldn't save your answer">
            <Text size="sm">{messageFor(answer.error)}</Text>
            <Button
              mt="sm"
              size="xs"
              disabled={busy}
              onClick={() => {
                if (answer.variables !== undefined) sendAnswer(answer.variables);
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
          revealed: key !== null && revealedKey === key,
        })}
      </VisuallyHidden>
      {body}
    </Stack>
  );
}
