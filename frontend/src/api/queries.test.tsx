import { QueryClientProvider, type QueryClient } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { createTestQueryClient } from '../test/render';
import { makeBuildStatus } from '../test/fixtures';
import { endpoints } from './endpoints';
import {
  BUILD_POLL_MS,
  buildJustFinished,
  pollInterval,
  queryKeys,
  useLatestBuild,
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
