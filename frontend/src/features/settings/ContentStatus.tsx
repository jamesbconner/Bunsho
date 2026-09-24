import { Alert, Badge, Button, Group, Paper, Skeleton, Stack, Text, Title } from '@mantine/core';

import { messageFor } from '../../api/errors';
import { useContentSummary } from '../../api/queries';
import { formatCount } from '../build/format';

/** Whether the study content is built, and how much of each kind there is. */
export function ContentStatus() {
  const summary = useContentSummary();

  if (summary.isPending) return <Skeleton height={80} />;
  if (summary.isError) {
    return (
      <Alert color="red" title="Couldn't load the content status">
        <Text size="sm">{messageFor(summary.error)}</Text>
        <Button
          mt="sm"
          size="xs"
          onClick={() => {
            void summary.refetch();
          }}
        >
          Try again
        </Button>
      </Alert>
    );
  }

  const { built, kana, kanji, vocab } = summary.data;
  return (
    <Paper component="section" aria-label="Content" withBorder p="md">
      <Group justify="space-between" mb={built ? 'xs' : 0}>
        <Title order={3}>Content</Title>
        <Badge color={built ? 'green' : 'gray'} variant="light">
          {built ? 'Built' : 'Not built'}
        </Badge>
      </Group>
      {built && (
        <Group gap="xl">
          {[
            ['Kana', kana],
            ['Kanji', kanji],
            ['Vocabulary', vocab],
          ].map(([label, count]) => (
            <Stack key={label} gap={0}>
              <Text size="xs" c="dimmed">
                {label}
              </Text>
              <Text fw={600}>{formatCount(Number(count))}</Text>
            </Stack>
          ))}
        </Group>
      )}
    </Paper>
  );
}
