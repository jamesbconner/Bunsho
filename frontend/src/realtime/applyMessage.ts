import type { QueryClient } from '@tanstack/react-query';

import type { BuildStatus } from '../api/endpoints';
import { queryKeys } from '../api/queries';
import type { ServerMessage } from './messages';

/**
 * Fold one live message into the query cache.
 *
 * A snapshot replaces the latest build. An event updates it when it is about the same build,
 * otherwise (a build this browser has not seen) the latest build is fetched. A build that ended
 * also refreshes everything that depends on the content: the final status carries the report.
 */
export function applyMessage(
  queryClient: QueryClient,
  message: Exclude<ServerMessage, { type: 'ready' }>,
): void {
  if (message.type === 'snapshot') {
    queryClient.setQueryData(queryKeys.latestBuild, message.task);
    return;
  }
  const { event } = message;
  const current = queryClient.getQueryData<BuildStatus | null>(queryKeys.latestBuild);
  if (current?.task_id === event.task_id) {
    const updated: BuildStatus = {
      ...current,
      state: event.state,
      progress: event.progress ?? current.progress,
      error: event.error ?? current.error,
    };
    queryClient.setQueryData(queryKeys.latestBuild, updated);
  } else {
    void queryClient.invalidateQueries({ queryKey: queryKeys.latestBuild });
  }
  if (event.state !== 'running') {
    void queryClient.invalidateQueries({ queryKey: queryKeys.latestBuild });
    void queryClient.invalidateQueries({ queryKey: queryKeys.contentSummary });
    void queryClient.invalidateQueries({ queryKey: queryKeys.configCheck });
  }
}
