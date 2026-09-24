import { Alert, Button, Skeleton, Stack, Text, Title } from '@mantine/core';

import { messageFor } from '../../api/errors';
import { useSettings } from '../../api/queries';
import { SettingsTabs } from './SettingsTabs';

/** How new cards are chosen and gated, how many, how you answer, and the service's status. */
export function SettingsPage() {
  const settings = useSettings();

  return (
    <Stack gap="lg" maw={720}>
      <Title order={2}>Settings</Title>
      {settings.isPending && <Skeleton height={320} />}
      {settings.isError && settings.data === undefined && (
        <Alert color="red" title="Couldn't load your settings">
          <Text size="sm">{messageFor(settings.error)}</Text>
          <Button
            mt="sm"
            size="xs"
            onClick={() => {
              void settings.refetch();
            }}
          >
            Try again
          </Button>
        </Alert>
      )}
      {settings.data !== undefined && <SettingsTabs initial={settings.data} />}
    </Stack>
  );
}
