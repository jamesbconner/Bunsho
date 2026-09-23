import { Alert, Badge, Group, Paper, Skeleton, Stack, Text, Title } from '@mantine/core';

import { messageFor } from '../../api/errors';
import { useConfigCheck } from '../../api/queries';

const CHECK_LABELS: Record<string, string> = {
  deck_present: 'Vocabulary deck',
  deck_checksum: 'Deck checksum',
  data_dir_writable: 'Data folder',
  jamdict_available: 'Dictionary',
};

/** What a content build needs from its environment, checked by the server. */
export function EnvironmentChecks() {
  const checks = useConfigCheck();

  if (checks.isPending) return <Skeleton height={112} />;
  if (checks.isError) {
    return (
      <Alert color="red" title="Couldn't check the environment">
        {messageFor(checks.error)}
      </Alert>
    );
  }
  return (
    <Paper component="section" aria-label="Environment" withBorder p="md">
      <Title order={3} mb="xs">
        Environment
      </Title>
      <Stack gap={6}>
        {checks.data.checks.map((check) => (
          <Group key={check.name} gap="xs" wrap="nowrap" align="flex-start">
            <Badge color={check.ok ? 'green' : 'red'} variant="light" w={72}>
              {check.ok ? 'OK' : 'Problem'}
            </Badge>
            <Text size="sm" fw={500}>
              {CHECK_LABELS[check.name] ?? check.name}
            </Text>
            <Text size="sm" c="dimmed">
              {check.detail}
            </Text>
          </Group>
        ))}
      </Stack>
    </Paper>
  );
}
