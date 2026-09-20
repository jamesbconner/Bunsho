import { useQuery } from '@tanstack/react-query';

import { endpoints, type BuildStatus } from './endpoints';

/** Query keys, shared by the hooks and by the code that updates the cache from the live stream. */
export const queryKeys = {
  contentSummary: ['content', 'summary'] as const,
  configCheck: ['admin', 'config-check'] as const,
  latestBuild: ['build', 'latest'] as const,
};

/** While a build runs and the live stream is down, ask the server this often. */
export const BUILD_POLL_MS = 2_000;

export function pollInterval(
  build: BuildStatus | null | undefined,
  streamConnected: boolean,
): number | false {
  return build?.state === 'running' && !streamConnected ? BUILD_POLL_MS : false;
}

export function useContentSummary() {
  return useQuery({ queryKey: queryKeys.contentSummary, queryFn: endpoints.contentSummary });
}

export function useConfigCheck() {
  return useQuery({ queryKey: queryKeys.configCheck, queryFn: endpoints.configCheck });
}

/** The latest build (null when none ran yet). Polls only while the live stream cannot be trusted. */
export function useLatestBuild(streamConnected: boolean) {
  return useQuery({
    queryKey: queryKeys.latestBuild,
    queryFn: endpoints.latestBuild,
    refetchInterval: (query) => pollInterval(query.state.data, streamConnected),
  });
}
