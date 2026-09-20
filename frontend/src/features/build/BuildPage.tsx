import {
  Alert,
  Button,
  Group,
  Modal,
  Stack,
  Switch,
  Text,
  Title,
  VisuallyHidden,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { notifications } from '@mantine/notifications';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { endpoints } from '../../api/endpoints';
import { queryKeys, useContentSummary, useLatestBuild } from '../../api/queries';
import { useConnectionState } from '../../realtime/realtimeContext';
import { BuildProgressCard } from './BuildProgressCard';
import { EnvironmentChecks } from './EnvironmentChecks';
import { startFailureMessage } from './startFailure';
import { announcementFor } from './status';

/** Start a content build (or a dry run) and follow it live. */
export function BuildPage() {
  const queryClient = useQueryClient();
  const connection = useConnectionState();
  const summary = useContentSummary();
  const latest = useLatestBuild(connection.kind === 'connected');
  const [dryRun, setDryRun] = useState(false);
  const [confirming, { open: askToConfirm, close: cancelConfirm }] = useDisclosure(false);

  const start = useMutation({
    mutationFn: (dry: boolean) => endpoints.startBuild(dry),
    onSuccess: (task) => {
      queryClient.setQueryData(queryKeys.latestBuild, task);
    },
    onError: (error) => {
      notifications.show({
        color: 'red',
        title: 'Could not start the build',
        message: startFailureMessage(error),
      });
    },
  });

  const running = latest.data?.state === 'running' || start.isPending;
  const alreadyBuilt = summary.data?.built === true;

  const buildLabel = dryRun ? 'Start dry run' : alreadyBuilt ? 'Rebuild content' : 'Build content';

  const onBuild = () => {
    if (alreadyBuilt && !dryRun) {
      askToConfirm();
    } else {
      start.mutate(dryRun);
    }
  };

  return (
    <Stack gap="md">
      <Title order={2}>Content</Title>
      {!alreadyBuilt && summary.isSuccess && (
        <Alert color="blue" title="First run">
          The study content has not been built yet. Build it once from the vocabulary deck; it takes
          about half a minute.
        </Alert>
      )}
      <EnvironmentChecks />
      <Group>
        <Button onClick={onBuild} loading={start.isPending} disabled={running || summary.isPending}>
          {buildLabel}
        </Button>
        <Switch
          label="Dry run (check without writing)"
          checked={dryRun}
          onChange={(event) => {
            setDryRun(event.currentTarget.checked);
          }}
          disabled={running}
        />
      </Group>
      {/* Always mounted, so a screen reader hears the state change (running, finished, failed). */}
      <VisuallyHidden role="status" aria-live="polite" aria-atomic>
        {announcementFor(latest.data)}
      </VisuallyHidden>
      {latest.data ? <BuildProgressCard task={latest.data} /> : null}

      <Modal opened={confirming} onClose={cancelConfirm} title="Rebuild content?" centered>
        <Stack>
          <Text size="sm">
            This replaces the content database with a fresh build from the deck. Your study progress
            is kept.
          </Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={cancelConfirm}>
              Cancel
            </Button>
            <Button
              onClick={() => {
                cancelConfirm();
                start.mutate(false);
              }}
            >
              Rebuild
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
