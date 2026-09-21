import { onlineManager, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { createTestQueryClient } from '../test/render';
import {
  makeBuildStatus,
  makeKanaCard,
  makeNextCard,
  makeSettings,
  makeStatsSummary,
} from '../test/fixtures';
import { endpoints, type NextCard } from './endpoints';
import { ApiError, NetworkError } from './errors';
import { shouldRetry } from '../queryClient';
import {
  BUILD_POLL_MS,
  buildJustFinished,
  pollInterval,
  queryKeys,
  useAnswerReview,
  useLatestBuild,
  useNextReview,
  useSettings,
  useStatsSummary,
  useUpdateSettings,
} from './queries';

describe('pollInterval', () => {
  it('polls only while a build runs and the live stream is not connected', () => {
    const running = makeBuildStatus({ state: 'running' });
    expect(pollInterval(running, false)).toBe(BUILD_POLL_MS);
    expect(pollInterval(running, true)).toBe(false);
  });

  it('never polls a finished build, no build, or an unknown state', () => {
    expect(pollInterval(makeBuildStatus({ state: 'succeeded' }), false)).toBe(false);
    expect(pollInterval(makeBuildStatus({ state: 'failed' }), false)).toBe(false);
    expect(pollInterval(null, false)).toBe(false);
    expect(pollInterval(undefined, false)).toBe(false);
  });
});

describe('buildJustFinished', () => {
  const running = makeBuildStatus();
  const succeeded = makeBuildStatus({ state: 'succeeded' });

  it('is true when a running build finished, or a newer build finished', () => {
    expect(buildJustFinished(running, succeeded)).toBe(true);
    expect(buildJustFinished(succeeded, makeBuildStatus({ task_id: 'new', state: 'failed' }))).toBe(
      true,
    );
  });

  it('is false for the first load, an unchanged finished build, or a build still running', () => {
    expect(buildJustFinished(undefined, succeeded)).toBe(false);
    expect(buildJustFinished(null, succeeded)).toBe(false);
    expect(buildJustFinished(succeeded, succeeded)).toBe(false);
    expect(buildJustFinished(running, running)).toBe(false);
    expect(buildJustFinished(running, null)).toBe(false);
  });
});

describe('useLatestBuild', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  function setup(queryClient: QueryClient) {
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
    const invalidated = () => invalidate.mock.calls.map((call) => call[0]?.queryKey);
    return { wrapper, invalidated };
  }

  it('refreshes the summary and the checks once when a polled build finished', async () => {
    const queryClient = createTestQueryClient();
    queryClient.setQueryData(queryKeys.latestBuild, makeBuildStatus());
    const latest = vi
      .spyOn(endpoints, 'latestBuild')
      .mockResolvedValue(makeBuildStatus({ state: 'succeeded' }));
    const { wrapper, invalidated } = setup(queryClient);

    const { result } = renderHook(() => useLatestBuild(false), { wrapper });
    await waitFor(() => {
      expect(result.current.data?.state).toBe('succeeded');
    });
    expect(invalidated()).toEqual([queryKeys.contentSummary, queryKeys.configCheck]);

    // Fetching the same finished build again is not a new completion.
    await queryClient.refetchQueries({ queryKey: queryKeys.latestBuild });
    expect(latest).toHaveBeenCalledTimes(2);
    expect(invalidated()).toEqual([queryKeys.contentSummary, queryKeys.configCheck]);
  });

  it('invalidates nothing on the first load of a finished build', async () => {
    const queryClient = createTestQueryClient();
    vi.spyOn(endpoints, 'latestBuild').mockResolvedValue(makeBuildStatus({ state: 'succeeded' }));
    const { wrapper, invalidated } = setup(queryClient);

    const { result } = renderHook(() => useLatestBuild(false), { wrapper });
    await waitFor(() => {
      expect(result.current.data?.state).toBe('succeeded');
    });
    expect(invalidated()).toEqual([]);
  });
});

function wrapperFor(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe('useNextReview', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('loads the next card under the review key', async () => {
    const payload = makeNextCard(makeKanaCard());
    vi.spyOn(endpoints, 'nextReview').mockResolvedValue(payload);
    const queryClient = createTestQueryClient();
    const { result } = renderHook(() => useNextReview(), { wrapper: wrapperFor(queryClient) });
    await waitFor(() => {
      expect(result.current.data).toEqual(payload);
    });
    expect(queryClient.getQueryData(queryKeys.reviewNext)).toEqual(payload);
  });
});

describe('useNextReview retries and refetching', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  // The application's retry policy, with the delay removed so the test stays fast.
  function appLikeClient(): QueryClient {
    return new QueryClient({
      defaultOptions: { queries: { retry: shouldRetry, retryDelay: 0, staleTime: 30_000 } },
    });
  }

  it('asks once when the content is not built (503) instead of retrying', async () => {
    const fetchNext = vi
      .spyOn(endpoints, 'nextReview')
      .mockRejectedValue(new ApiError(503, 'content is not built'));
    const { result } = renderHook(() => useNextReview(), {
      wrapper: wrapperFor(appLikeClient()),
    });
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(fetchNext).toHaveBeenCalledTimes(1);
  });

  it('still retries other server errors and connection failures, twice at most', async () => {
    const fetchNext = vi
      .spyOn(endpoints, 'nextReview')
      .mockRejectedValueOnce(new ApiError(500, 'boom'))
      .mockRejectedValueOnce(new NetworkError())
      .mockRejectedValue(new ApiError(500, 'boom'));
    const { result } = renderHook(() => useNextReview(), {
      wrapper: wrapperFor(appLikeClient()),
    });
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(fetchNext).toHaveBeenCalledTimes(3);
  });

  it('does not refetch when the connection comes back', async () => {
    const fetchNext = vi.spyOn(endpoints, 'nextReview').mockResolvedValue(makeNextCard(null));
    const { result } = renderHook(() => useNextReview(), {
      wrapper: wrapperFor(createTestQueryClient()),
    });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    onlineManager.setOnline(false);
    onlineManager.setOnline(true);
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(fetchNext).toHaveBeenCalledTimes(1);
  });
});

describe('useAnswerReview', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('caches the fresh counts at once and stays pending until the next card arrives', async () => {
    const before = makeNextCard(makeKanaCard());
    const after = makeNextCard(null);
    const counts = { ...before.counts, due: { kana: 5, kanji: 0, vocab: 0 } };
    vi.spyOn(endpoints, 'answerReview').mockResolvedValue(counts);
    const fetchNext = vi.spyOn(endpoints, 'nextReview').mockResolvedValueOnce(before);
    const queryClient = createTestQueryClient();
    const next = renderHook(() => useNextReview(), { wrapper: wrapperFor(queryClient) });
    await waitFor(() => {
      expect(next.result.current.data).toEqual(before);
    });

    // From here the next-card fetch stays in flight until the test lets it settle.
    let settle: (value: NextCard) => void = () => undefined;
    fetchNext.mockClear();
    fetchNext.mockImplementation(
      () =>
        new Promise<NextCard>((resolve) => {
          settle = resolve;
        }),
    );

    const answer = renderHook(() => useAnswerReview(), { wrapper: wrapperFor(queryClient) });
    answer.result.current.mutate({
      item_id: 'kana:あ',
      direction: 'glyph_to_sound',
      grade: 3,
      expected_last_review: null,
    });
    await waitFor(() => {
      expect(fetchNext).toHaveBeenCalledTimes(1);
    });

    // The counts are already in the cache, the old card still is, and the mutation waits.
    const cached = queryClient.getQueryData<NextCard>(queryKeys.reviewNext);
    expect(cached?.counts).toEqual(counts);
    expect(cached?.card).toEqual(before.card);
    expect(answer.result.current.isPending).toBe(true);

    settle(after);
    await waitFor(() => {
      expect(answer.result.current.isSuccess).toBe(true);
    });
    expect(queryClient.getQueryData(queryKeys.reviewNext)).toEqual(after);
  });

  it('does not retry a failed answer', async () => {
    const send = vi.spyOn(endpoints, 'answerReview').mockRejectedValue(new Error('network down'));
    const queryClient = createTestQueryClient();
    const answer = renderHook(() => useAnswerReview(), { wrapper: wrapperFor(queryClient) });
    answer.result.current.mutate({
      item_id: 'kana:あ',
      direction: 'glyph_to_sound',
      grade: 3,
      expected_last_review: null,
    });
    await waitFor(() => {
      expect(answer.result.current.isError).toBe(true);
    });
    expect(send).toHaveBeenCalledTimes(1);
  });
});

describe('useStatsSummary and useSettings', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('load the statistics and the settings under their own keys', async () => {
    vi.spyOn(endpoints, 'statsSummary').mockResolvedValue(makeStatsSummary());
    vi.spyOn(endpoints, 'getSettings').mockResolvedValue(makeSettings());
    const queryClient = createTestQueryClient();
    const stats = renderHook(() => useStatsSummary(), { wrapper: wrapperFor(queryClient) });
    const settings = renderHook(() => useSettings(), { wrapper: wrapperFor(queryClient) });
    await waitFor(() => {
      expect(stats.result.current.data?.reviewed_today).toBe(42);
      expect(settings.result.current.data?.rollover_hour).toBe(4);
    });
    expect(queryClient.getQueryData(queryKeys.statsSummary)).toEqual(makeStatsSummary());
    expect(queryClient.getQueryData(queryKeys.settings)).toEqual(makeSettings());
  });
});

describe('useUpdateSettings', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('caches the saved document and marks the next card and the statistics stale', async () => {
    const saved = makeSettings({ target_retention: 0.95 });
    vi.spyOn(endpoints, 'updateSettings').mockResolvedValue(saved);
    const queryClient = createTestQueryClient();
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
    const { result } = renderHook(() => useUpdateSettings(), { wrapper: wrapperFor(queryClient) });

    result.current.mutate(makeSettings({ target_retention: 0.95 }));
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(queryClient.getQueryData(queryKeys.settings)).toEqual(saved);
    const keys = invalidate.mock.calls.map((call) => call[0]?.queryKey);
    expect(keys).toEqual([queryKeys.reviewNext, queryKeys.statsSummary]);
  });

  it('does not retry a failed save and leaves the cache alone', async () => {
    const send = vi.spyOn(endpoints, 'updateSettings').mockRejectedValue(new Error('down'));
    const queryClient = createTestQueryClient();
    queryClient.setQueryData(queryKeys.settings, makeSettings());
    const { result } = renderHook(() => useUpdateSettings(), { wrapper: wrapperFor(queryClient) });

    result.current.mutate(makeSettings({ rollover_hour: 6 }));
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    expect(send).toHaveBeenCalledTimes(1);
    expect(queryClient.getQueryData(queryKeys.settings)).toEqual(makeSettings());
  });
});
