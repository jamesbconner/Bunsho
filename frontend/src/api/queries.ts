import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';

import { endpoints, type BuildStatus, type NextCard } from './endpoints';

/** Query keys, shared by the hooks and by the code that updates the cache from the live stream. */
export const queryKeys = {
  contentSummary: ['content', 'summary'] as const,
  configCheck: ['admin', 'config-check'] as const,
  latestBuild: ['build', 'latest'] as const,
  reviewNext: ['review', 'next'] as const,
};

/** While a build runs and the live stream is down, ask the server this often. */
export const BUILD_POLL_MS = 2_000;

export function pollInterval(
  build: BuildStatus | null | undefined,
  streamConnected: boolean,
): number | false {
  return build?.state === 'running' && !streamConnected ? BUILD_POLL_MS : false;
}

/** Whether a build has ended (succeeded or failed) rather than still running. */
export function isFinished(build: BuildStatus): boolean {
  return build.state !== 'running';
}

/**
 * Whether `next` reports a build that finished since `previous` was cached: it was running, or it
 * is a different (newer) build. Nothing cached yet is not a transition (the first load), and an
 * already finished build seen again is not either, so each completion is reported once.
 */
export function buildJustFinished(
  previous: BuildStatus | null | undefined,
  next: BuildStatus | null | undefined,
): boolean {
  if (previous == null || next == null || !isFinished(next)) return false;
  return previous.task_id !== next.task_id || !isFinished(previous);
}

/** A finished build changes the content and the environment checks: refetch what shows them. */
export function invalidateBuildDependents(queryClient: QueryClient): void {
  void queryClient.invalidateQueries({ queryKey: queryKeys.contentSummary });
  void queryClient.invalidateQueries({ queryKey: queryKeys.configCheck });
}

export function useContentSummary() {
  return useQuery({ queryKey: queryKeys.contentSummary, queryFn: endpoints.contentSummary });
}

export function useConfigCheck() {
  return useQuery({ queryKey: queryKeys.configCheck, queryFn: endpoints.configCheck });
}

/**
 * The latest build (null when none ran yet). Polls only while the live stream cannot be trusted.
 * A fetched build that finished since the cached one also refreshes what depends on the content
 * (a build can finish while the stream is down).
 */
export function useLatestBuild(streamConnected: boolean) {
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: queryKeys.latestBuild,
    queryFn: async () => {
      const previous = queryClient.getQueryData<BuildStatus | null>(queryKeys.latestBuild);
      const next = await endpoints.latestBuild();
      if (buildJustFinished(previous, next)) invalidateBuildDependents(queryClient);

      return next;
    },
    refetchInterval: (query) => pollInterval(query.state.data, streamConnected),
  });
}

/**
 * The next card to study, with the counts. What is due changes with the clock, so opening a screen
 * always asks the server (`staleTime: 0`); switching windows does not, so a card never changes
 * under the learner's hands.
 */
export function useNextReview() {
  return useQuery({
    queryKey: queryKeys.reviewNext,
    queryFn: endpoints.nextReview,
    staleTime: 0,
    refetchOnWindowFocus: false,
  });
}

/**
 * Grade a card. On success the fresh counts go into the cache at once and the next card is
 * fetched; the mutation stays pending until that fetch settles, so the screen never shows the card
 * that was just graded. It never retries by itself: a repeated POST would count the review twice.
 */
export function useAnswerReview() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: endpoints.answerReview,
    onSuccess: async (counts) => {
      queryClient.setQueryData<NextCard>(
        queryKeys.reviewNext,
        (previous) => previous && { ...previous, counts },
      );
      await queryClient.invalidateQueries({ queryKey: queryKeys.reviewNext });
    },
  });
}
