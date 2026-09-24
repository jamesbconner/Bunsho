import { Alert, Badge, Button, Group, Paper, Skeleton, Stack, Text, Title } from '@mantine/core';

import { ApiError, messageFor } from '../../api/errors';
import { useHealth } from '../../api/queries';

const STATUS_COLOR = { ok: 'green', degraded: 'yellow', error: 'red' } as const;
const STATUS_LABEL = { ok: 'OK', degraded: 'Degraded', error: 'Problem' } as const;

/** `messageFor` reads a 503 as "content isn't built", which is wrong for the health check. */
function healthFailureMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 503) {
    return 'The server answered, but not with a health report.';
  }
  return messageFor(error);
}

/** The service's version and what its own health check says about each dependency. */
export function ServerStatus() {
  const health = useHealth();

  if (health.isPending) return <Skeleton height={112} />;
  if (health.isError) {
    return (
      <Alert color="red" title="Couldn't check the server">
        <Text size="sm">{healthFailureMessage(health.error)}</Text>
        <Button
          mt="sm"
          size="xs"
          onClick={() => {
            void health.refetch();
          }}
        >
          Try again
        </Button>
      </Alert>
    );
  }

  const { status, version, components } = health.data;
  return (
    <Paper component="section" aria-label="Server" withBorder p="md">
      <Group justify="space-between" mb="xs">
        <Title order={3}>Server</Title>
        <Group gap="xs">
          <Text size="sm" c="dimmed">
            Version {version}
          </Text>
          <Badge color={STATUS_COLOR[status]} variant="light">
            {STATUS_LABEL[status]}
          </Badge>
        </Group>
      </Group>
      <Stack gap={6}>
        {Object.entries(components).map(([name, component]) => (
          <Group key={name} gap="xs" wrap="nowrap" align="flex-start">
            <Badge color={STATUS_COLOR[component.status]} variant="light" w={88}>
              {STATUS_LABEL[component.status]}
            </Badge>
            <Text size="sm" fw={500}>
              {name}
            </Text>
            <Text size="sm" c="dimmed">
              {component.detail}
            </Text>
          </Group>
        ))}
      </Stack>
    </Paper>
  );
}
