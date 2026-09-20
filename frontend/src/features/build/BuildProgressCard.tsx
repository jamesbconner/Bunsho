import { Alert, Badge, Group, Paper, Progress, Stack, Text, Title } from '@mantine/core';

import type { BuildStatus } from '../../api/endpoints';
import { BuildReportTable } from './BuildReportTable';
import { formatCount } from './format';

const STAGE_LABELS: Record<string, string> = {
  import_deck: 'Reading the vocabulary deck',
  enrich_kanji: 'Looking up kanji details',
  write: 'Writing the content database',
};

const STATE_BADGES: Record<BuildStatus['state'], { color: string; label: string }> = {
  running: { color: 'blue', label: 'Running' },
  succeeded: { color: 'green', label: 'Finished' },
  failed: { color: 'red', label: 'Failed' },
};

/** The state of one build: live progress while it runs, then the report or the error. */
export function BuildProgressCard({ task }: { task: BuildStatus }) {
  const { progress } = task;
  const badge = STATE_BADGES[task.state];
  const percent =
    progress !== null && progress.total > 0
      ? Math.round((progress.current / progress.total) * 100)
      : 0;
  const stage = progress === null ? 'Starting' : (STAGE_LABELS[progress.stage] ?? progress.stage);

  return (
    <Paper withBorder p="md">
      <Group justify="space-between" mb="sm">
        <Title order={4}>{task.dry_run ? 'Dry run' : 'Content build'}</Title>
        <Badge color={badge.color}>{badge.label}</Badge>
      </Group>
      {task.state === 'running' && (
        <Stack gap="xs" role="status" aria-live="polite">
          <Text size="sm">
            {stage}
            {progress !== null && progress.total > 1
              ? ` (${formatCount(progress.current)} of ${formatCount(progress.total)})`
              : ''}
          </Text>
          <Progress value={percent} animated aria-label="Build progress" />
        </Stack>
      )}
      {task.state === 'failed' && (
        <Alert color="red" title="The build failed">
          {task.error ?? 'No details were reported.'}
        </Alert>
      )}
      {task.state === 'succeeded' && task.report !== null && (
        <BuildReportTable report={task.report} />
      )}
    </Paper>
  );
}
