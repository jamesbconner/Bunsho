import type { QueryClient } from '@tanstack/react-query';

import type { BuildStatus } from '../api/endpoints';
import {
  buildJustFinished,
  invalidateBuildDependents,
  isFinished,
  queryKeys,
} from '../api/queries';
import type { ServerMessage } from './messages';

/**
 * Fold one live message into the query cache.
 *
 * A snapshot replaces the latest build; when it shows a build that finished since the cached one
 * (the server sends the last build after every reconnect), what depends on the content is
 * refreshed too. An event updates the latest build when it is about the same build, otherwise (a
 * build this browser has not seen) the latest build is fetched. A build that ended also refreshes
 * everything that depends on the content: the final status carries the report.
 */
export function applyMessage(
  queryClient: QueryClient,
  message: Exclude<ServerMessage, { type: 'ready' }>,
): void {
  const current = queryClient.getQueryData<BuildStatus | null>(queryKeys.latestBuild);
  if (message.type === 'snapshot') {
    queryClient.setQueryData(queryKeys.latestBuild, message.task);
    if (buildJustFinished(current, message.task)) {
      void queryClient.invalidateQueries({ queryKey: queryKeys.latestBuild });
      invalidateBuildDependents(queryClient);
    }
    return;
  }
  const { event } = message;
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
  const alreadyFinished = current?.task_id === event.task_id && isFinished(current);
  if (event.state !== 'running' && !alreadyFinished) {
    void queryClient.invalidateQueries({ queryKey: queryKeys.latestBuild });
    invalidateBuildDependents(queryClient);
  }
}
