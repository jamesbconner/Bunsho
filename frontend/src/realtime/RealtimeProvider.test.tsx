import { screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { BuildStatus } from '../api/endpoints';
import { queryKeys } from '../api/queries';
import { session } from '../auth/session';
import { FakeSocket } from '../test/fakeSocket';
import { makeBuildStatus } from '../test/fixtures';
import { renderWithProviders } from '../test/render';
import { ConnectionBadge } from './ConnectionBadge';
import { RealtimeProvider } from './RealtimeProvider';
import { RealtimeContext, useConnectionState } from './realtimeContext';

const sockets: FakeSocket[] = [];
function createSocket(url: string): FakeSocket {
  const socket = new FakeSocket(url);
  sockets.push(socket);
  return socket;
}

function firstSocket(): FakeSocket {
  const socket = sockets[0];
  if (socket === undefined) throw new Error('no socket was created');
  return socket;
}

function Probe() {
  return <span data-testid="state">{useConnectionState().kind}</span>;
}

describe('RealtimeProvider', () => {
  beforeEach(() => {
    sockets.length = 0;
    session.clear();
    session.setTokens({ access_token: 'a1', refresh_token: 'r1', expires_in: 900 });
  });

  it('connects with the session token and reports the connection state', async () => {
    renderWithProviders(
      <RealtimeProvider createSocket={createSocket}>
        <Probe />
      </RealtimeProvider>,
    );
    await waitFor(() => {
      expect(sockets).toHaveLength(1);
    });
    expect(firstSocket().url).toMatch(/^ws:\/\/.*\/api\/v1\/ws\/tasks$/);
    firstSocket().open();
    expect(JSON.parse(firstSocket().sent[0] ?? 'null')).toEqual({ type: 'auth', token: 'a1' });
    expect(screen.getByTestId('state')).toHaveTextContent('connecting');
    firstSocket().receive({ type: 'ready' });
    await waitFor(() => {
      expect(screen.getByTestId('state')).toHaveTextContent('connected');
    });
  });

  it('folds snapshots and events into the query cache', async () => {
    const { queryClient } = renderWithProviders(
      <RealtimeProvider createSocket={createSocket}>
        <Probe />
      </RealtimeProvider>,
    );
    await waitFor(() => {
      expect(sockets).toHaveLength(1);
    });
    const socket = firstSocket();
    socket.open();
    socket.receive({ type: 'ready' });
    const task = makeBuildStatus();
    socket.receive({ type: 'snapshot', task });
    expect(queryClient.getQueryData(queryKeys.latestBuild)).toEqual(task);
    socket.receive({
      type: 'event',
      event: {
        kind: 'progress',
        task_id: task.task_id,
        state: 'running',
        progress: { stage: 'write', current: 1, total: 2 },
        error: null,
      },
    });
    expect(queryClient.getQueryData<BuildStatus>(queryKeys.latestBuild)?.progress?.stage).toBe(
      'write',
    );
  });

  it('closes the connection when it is unmounted', async () => {
    const { unmount } = renderWithProviders(
      <RealtimeProvider createSocket={createSocket}>
        <Probe />
      </RealtimeProvider>,
    );
    await waitFor(() => {
      expect(sockets).toHaveLength(1);
    });
    unmount();
    expect(firstSocket().closed).toBe(true);
  });
});

describe('ConnectionBadge', () => {
  it.each([
    [{ kind: 'connected' }, 'Live'],
    [{ kind: 'connecting' }, 'Connecting…'],
    [{ kind: 'disconnected' }, 'Offline'],
  ] as const)('shows %j as "%s"', (state, label) => {
    renderWithProviders(
      <RealtimeContext value={state}>
        <ConnectionBadge />
      </RealtimeContext>,
    );
    expect(screen.getByRole('status')).toHaveTextContent(label);
  });

  it('counts down to the next reconnection attempt', () => {
    vi.useFakeTimers();
    vi.setSystemTime(0);
    try {
      renderWithProviders(
        <RealtimeContext value={{ kind: 'retrying', retryAt: 4_000 }}>
          <ConnectionBadge />
        </RealtimeContext>,
      );
      expect(screen.getByRole('status')).toHaveTextContent('Reconnecting in 4 s');
    } finally {
      vi.useRealTimers();
    }
  });
});
