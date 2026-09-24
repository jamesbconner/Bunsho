import { Alert, Button, Paper, SimpleGrid, Skeleton, Stack, Text, Title } from '@mantine/core';
import { Link } from 'react-router';

import { messageFor } from '../../api/errors';
import { useNextReview } from '../../api/queries';
import { formatDueTime } from '../review/formatInterval';

const TYPES = [
  { key: 'kana', label: 'Kana' },
  { key: 'kanji', label: 'Kanji' },
  { key: 'vocab', label: 'Vocabulary' },
] as const;

/** What is waiting to be studied, and the way in. */
export function StudyPanel() {
  const next = useNextReview();

  if (next.isPending) return <Skeleton height={168} />;
  if (next.isError) {
    return (
      <Alert color="red" title="Couldn't load your study queue">
        <Text size="sm">{messageFor(next.error)}</Text>
        <Button
          mt="sm"
          size="xs"
          onClick={() => {
            void next.refetch();
          }}
        >
          Try again
        </Button>
      </Alert>
    );
  }

  const { card, counts, next_due_at: nextDueAt } = next.data;
  return (
    <Stack gap="sm">
      <Title order={2}>Today</Title>
      <SimpleGrid cols={{ base: 1, sm: 3 }}>
        {TYPES.map(({ key, label }) => (
          <Paper key={key} withBorder p="md">
            <Text size="sm" c="dimmed">
              {label}
            </Text>
            <Text fz={28} fw={600}>
              {counts.due[key]} due
            </Text>
            <Text size="xs" c="dimmed">
              {counts.new_remaining[key]} new available
            </Text>
          </Paper>
        ))}
      </SimpleGrid>
      {card !== null ? (
        <Button component={Link} to="/review" size="lg">
          Study now
        </Button>
      ) : (
        <Text c="dimmed">
          Nothing due right now
          {nextDueAt !== null ? `. Next card due ${formatDueTime(nextDueAt)}` : ''}.
        </Text>
      )}
    </Stack>
  );
}
