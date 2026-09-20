import { QueryClient } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi, type MockInstance } from 'vitest';

import type { BuildStatus } from '../api/endpoints';
import { queryKeys } from '../api/queries';
import { makeBuildStatus } from '../test/fixtures';
import { applyMessage } from './applyMessage';

let queryClient: QueryClient;
let invalidate: MockInstance<QueryClient['invalidateQueries']>;

function event(overrides: Record<string, unknown> = {}) {
  return {
    type: 'event' as const,
    event: {
      kind: 'progress' as const,
      task_id: 'task-1',
      state: 'running' as const,
      progress: { stage: 'enrich_kanji', current: 5, total: 10 },
      error: null,
      ...overrides,
    },
  };
}

function invalidatedKeys(): unknown[] {
  return invalidate.mock.calls.map((call) => call[0]?.queryKey);
}

describe('applyMessage', () => {
  beforeEach(() => {
    queryClient = new QueryClient();
    invalidate = vi.spyOn(queryClient, 'invalidateQueries');
  });

  it('a snapshot replaces the latest build', () => {
    const task = makeBuildStatus({ task_id: 'task-9', state: 'succeeded' });
    applyMessage(queryClient, { type: 'snapshot', task });
    expect(queryClient.getQueryData(queryKeys.latestBuild)).toEqual(task);
    expect(invalidate).not.toHaveBeenCalled();
  });

  it('a progress event updates the build it belongs to', () => {
    queryClient.setQueryData(queryKeys.latestBuild, makeBuildStatus());
    applyMessage(queryClient, event());
    const cached = queryClient.getQueryData<BuildStatus>(queryKeys.latestBuild);
    expect(cached?.progress).toEqual({ stage: 'enrich_kanji', current: 5, total: 10 });
    expect(cached?.state).toBe('running');
    expect(invalidate).not.toHaveBeenCalled();
  });

  it('keeps the previous progress and error when an event carries none', () => {
    queryClient.setQueryData(
      queryKeys.latestBuild,
      makeBuildStatus({ progress: { stage: 'write', current: 1, total: 2 } }),
    );
    applyMessage(queryClient, event({ progress: null }));
    expect(queryClient.getQueryData<BuildStatus>(queryKeys.latestBuild)?.progress).toEqual({
      stage: 'write',
      current: 1,
      total: 2,
    });
  });

  it('fetches the latest build when the event is about a build we have not seen', () => {
    queryClient.setQueryData(queryKeys.latestBuild, makeBuildStatus({ task_id: 'older' }));
    applyMessage(queryClient, event());
    expect(invalidatedKeys()).toEqual([queryKeys.latestBuild]);
    queryClient.clear();
    invalidate.mockClear();
    applyMessage(queryClient, event()); // nothing cached at all
    expect(invalidatedKeys()).toEqual([queryKeys.latestBuild]);
  });

  it('a build that ended refreshes the build, the content summary and the checks', () => {
    queryClient.setQueryData(queryKeys.latestBuild, makeBuildStatus());
    applyMessage(queryClient, event({ kind: 'state', state: 'succeeded', progress: null }));
    expect(queryClient.getQueryData<BuildStatus>(queryKeys.latestBuild)?.state).toBe('succeeded');
    expect(invalidatedKeys()).toEqual([
      queryKeys.latestBuild,
      queryKeys.contentSummary,
      queryKeys.configCheck,
    ]);
  });

  it('a failed build carries its error message into the cache', () => {
    queryClient.setQueryData(queryKeys.latestBuild, makeBuildStatus());
    applyMessage(
      queryClient,
      event({ kind: 'state', state: 'failed', progress: null, error: 'the deck is missing' }),
    );
    const cached = queryClient.getQueryData<BuildStatus>(queryKeys.latestBuild);
    expect(cached?.state).toBe('failed');
    expect(cached?.error).toBe('the deck is missing');
  });
});
