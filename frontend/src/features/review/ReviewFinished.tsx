import { Alert, Button, Stack, Text, Title } from '@mantine/core';
import { Link } from 'react-router';

import type { NextCard } from '../../api/endpoints';
import { formatDueTime } from './formatInterval';

/**
 * No card to study right now. The API cannot say whether the daily new-card limit is used up or
 * everything unlocked has been introduced, so the message names both.
 */
export function ReviewDone({ data }: { data: NextCard }) {
  return (
    <Stack align="center" gap="sm" py="xl" ta="center">
      <Title order={3}>You&apos;re done for now</Title>
      <Text c="dimmed" maw={460}>
        Nothing is due and no new cards are available today. The daily new-card limit may be used
        up, or every card that is unlocked has been introduced.
      </Text>
      {data.next_due_at !== null && <Text>Next card due {formatDueTime(data.next_due_at)}.</Text>}
      <Button component={Link} to="/" variant="light">
        Back to the dashboard
      </Button>
      <Button component={Link} to="/settings" variant="subtle" size="xs">
        Change your daily limits in Settings
      </Button>
    </Stack>
  );
}

/** The content has not been built yet, so there is nothing to study. */
export function ReviewNotBuilt() {
  return (
    <Alert color="blue" title="Nothing to study yet">
      <Text size="sm">The study content has not been built yet.</Text>
      <Button component={Link} to="/build" mt="sm" size="xs">
        Build your content
      </Button>
    </Alert>
  );
}
