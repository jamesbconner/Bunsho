import { QueryClientProvider, type QueryClient } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { createTestQueryClient } from '../test/render';
import { makeBuildStatus, makeKanaCard, makeNextCard } from '../test/fixtures';
import { endpoints } from './endpoints';
import {
  BUILD_POLL_MS,
  buildJustFinished,
  pollInterval,
  queryKeys,
  useAnswerReview,
  useLatestBuild,
  useNextReview,
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

describe('useAnswerReview', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('writes the fresh counts into the cache and refetches the next card', async () => {
    const before = makeNextCard(makeKanaCard());
    const after = makeNextCard(null);
    const counts = { ...after.counts, due: { kana: 5, kanji: 0, vocab: 0 } };
    vi.spyOn(endpoints, 'answerReview').mockResolvedValue(counts);
    const fetchNext = vi.spyOn(endpoints, 'nextReview').mockResolvedValue(after);
    const queryClient = createTestQueryClient();
    queryClient.setQueryData(queryKeys.reviewNext, before);
    const next = renderHook(() => useNextReview(), { wrapper: wrapperFor(queryClient) });
    await waitFor(() => {
      expect(next.result.current.data).toEqual(after);
    });
    fetchNext.mockClear();
    const answer = renderHook(() => useAnswerReview(), { wrapper: wrapperFor(queryClient) });
    answer.result.current.mutate({
      item_id: 'kana:あ',
      direction: 'glyph_to_sound',
      grade: 3,
      expected_last_review: null,
    });
    await waitFor(() => {
      expect(answer.result.current.isSuccess).toBe(true);
    });
    expect(fetchNext).toHaveBeenCalledTimes(1);
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
