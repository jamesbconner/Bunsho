import { Alert, Stack } from '@mantine/core';

import { useContentSummary } from '../../api/queries';
import { BuildPanel } from '../build/BuildPanel';
import { EnvironmentChecks } from '../build/EnvironmentChecks';
import { ContentStatus } from './ContentStatus';
import { ServerStatus } from './ServerStatus';

/** Shown until the first build: the study content does not exist yet. */
function FirstRunNotice() {
  const summary = useContentSummary();
  if (!summary.isSuccess || summary.data.built) return null;
  return (
    <Alert color="blue" title="First run">
      The study content has not been built yet. Build it once from the vocabulary deck; it takes
      about half a minute.
    </Alert>
  );
}

/** Service status and the content build. Not part of the settings form. */
export function SystemTab() {
  return (
    <Stack gap="lg">
      <FirstRunNotice />
      <ServerStatus />
      <ContentStatus />
      <EnvironmentChecks />
      <BuildPanel />
    </Stack>
  );
}
