import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { FakeSocket } from '../test/fakeSocket';
import { nextDelayMs } from './backoff';
import { BuildStream, type BuildStreamOptions, type ConnectionState } from './BuildStream';
import { parseServerMessage } from './messages';

const URL = 'ws://localhost/api/v1/ws/tasks';

function harness(overrides: Partial<BuildStreamOptions> = {}) {
  const sockets: FakeSocket[] = [];
  const states: ConnectionState[] = [];
  const messages: unknown[] = [];
  const refreshAuth = vi.fn(() => Promise.resolve(true));
  let tokenCalls = 0;
  const stream = new BuildStream({
    url: URL,
    getToken: () => {
      tokenCalls += 1;
      return Promise.resolve(`token-${String(tokenCalls)}`);
    },
    refreshAuth,
    onState: (state) => states.push(state),
    onMessage: (message) => messages.push(message),
    createSocket: (url) => {
      const socket = new FakeSocket(url);
      sockets.push(socket);
      return socket;
    },
    random: () => 1, // the longest jitter draw: delays equal the exponential ceiling
    ...overrides,
  });
  return { stream, sockets, states, messages, refreshAuth, tokenCalls: () => tokenCalls };
}

function last(sockets: FakeSocket[]): FakeSocket {
  const socket = sockets.at(-1);
  if (socket === undefined) throw new Error('no socket was created');
  return socket;
}

function lastState(states: ConnectionState[]): ConnectionState {
  const state = states.at(-1);
  if (state === undefined) throw new Error('no state was reported');
  return state;
}

const flush = () => vi.advanceTimersByTimeAsync(0);
const READY = { type: 'ready' };

describe('BuildStream', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(0);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('authenticates with its first message, then reports connected on ready', async () => {
    const { stream, sockets, states } = harness();
    stream.start();
    await flush();
    expect(lastState(states)).toEqual({ kind: 'connecting' });
    const socket = last(sockets);
    expect(socket.url).toBe(URL);
    expect(socket.sent).toEqual([]); // nothing is sent before the connection opens
    socket.open();
    expect(JSON.parse(socket.sent[0] ?? 'null')).toEqual({ type: 'auth', token: 'token-1' });
    socket.receive(READY);
    expect(lastState(states)).toEqual({ kind: 'connected' });
  });

  it('forwards snapshots and events and ignores anything else', async () => {
    const { stream, sockets, messages } = harness();
    stream.start();
    await flush();
    const socket = last(sockets);
    socket.open();
    socket.receive(READY);
    const task = { task_id: 't1', state: 'running' };
    const event = {
      kind: 'progress',
      task_id: 't1',
      state: 'running',
      progress: null,
      error: null,
    };
    socket.receive({ type: 'snapshot', task });
    socket.receive({ type: 'event', event });
    socket.receive('not json at all');
    socket.receive({ type: 'mystery' });
    socket.receive({ type: 'snapshot' }); // malformed: no task
    expect(messages).toEqual([
      { type: 'snapshot', task },
      { type: 'event', event },
    ]);
  });

  it('reconnects with exponentially growing delays and reports when it will retry', async () => {
    const { stream, sockets, states } = harness();
    stream.start();
    await flush();
    for (const delay of [1_000, 2_000, 4_000, 8_000]) {
      const before = Date.now();
      last(sockets).serverClose(1006);
      expect(lastState(states)).toEqual({ kind: 'retrying', retryAt: before + delay });
      await vi.advanceTimersByTimeAsync(delay - 1);
      const count = sockets.length;
      await vi.advanceTimersByTimeAsync(1);
      expect(sockets).toHaveLength(count + 1);
    }
  });

  it('starts the backoff over once a connection became ready', async () => {
    const { stream, sockets, states } = harness();
    stream.start();
    await flush();
    last(sockets).serverClose(1006);
    await vi.advanceTimersByTimeAsync(1_000);
    last(sockets).serverClose(1006);
    await vi.advanceTimersByTimeAsync(2_000);
    const socket = last(sockets);
    socket.open();
    socket.receive(READY);
    const before = Date.now();
    socket.serverClose(1006);
    expect(lastState(states)).toEqual({ kind: 'retrying', retryAt: before + 1_000 });
  });

  it('refreshes the session and reconnects once when the server closes with 1008', async () => {
    const { stream, sockets, states, refreshAuth, tokenCalls } = harness();
    stream.start();
    await flush();
    last(sockets).serverClose(1008);
    await flush();
    expect(refreshAuth).toHaveBeenCalledTimes(1);
    expect(sockets).toHaveLength(2); // reconnected at once, without a backoff delay
    expect(tokenCalls()).toBe(2);
    // The second attempt is rejected as well: no more refreshes, no more sockets.
    last(sockets).serverClose(1008);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(refreshAuth).toHaveBeenCalledTimes(1);
    expect(sockets).toHaveLength(2);
    expect(lastState(states)).toEqual({ kind: 'disconnected' });
  });

  it('gives up when the session cannot be refreshed', async () => {
    const refreshAuth = vi.fn(() => Promise.resolve(false));
    const { stream, sockets, states } = harness({ refreshAuth });
    stream.start();
    await flush();
    last(sockets).serverClose(1008);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(refreshAuth).toHaveBeenCalledTimes(1);
    expect(sockets).toHaveLength(1);
    expect(lastState(states)).toEqual({ kind: 'disconnected' });
  });

  it('retries when no access token can be obtained', async () => {
    let calls = 0;
    const { stream, sockets, states } = harness({
      getToken: () => {
        calls += 1;
        return calls === 1 ? Promise.reject(new Error('offline')) : Promise.resolve('token');
      },
    });
    stream.start();
    await flush();
    expect(sockets).toHaveLength(0);
    expect(lastState(states)).toEqual({ kind: 'retrying', retryAt: 1_000 });
    await vi.advanceTimersByTimeAsync(1_000);
    expect(sockets).toHaveLength(1);
  });

  it('stop closes the socket, cancels a pending retry and ignores late events', async () => {
    const { stream, sockets, states } = harness();
    stream.start();
    await flush();
    const socket = last(sockets);
    socket.open();
    socket.receive(READY);
    stream.stop();
    expect(socket.closed).toBe(true);
    expect(lastState(states)).toEqual({ kind: 'disconnected' });
    socket.serverClose(1006); // a late close event from the abandoned socket
    await vi.advanceTimersByTimeAsync(60_000);
    expect(sockets).toHaveLength(1);

    stream.start();
    await flush();
    last(sockets).serverClose(1006); // now waiting to retry
    stream.stop();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(sockets).toHaveLength(2);
  });

  it('start is idempotent while running', async () => {
    const { stream, sockets } = harness();
    stream.start();
    stream.start();
    await flush();
    expect(sockets).toHaveLength(1);
  });
});

describe('nextDelayMs', () => {
  it('grows exponentially from one second and is capped at thirty', () => {
    const delays = [0, 1, 2, 3, 4, 5, 6, 10].map((attempt) => nextDelayMs(attempt, () => 1));
    expect(delays).toEqual([1_000, 2_000, 4_000, 8_000, 16_000, 30_000, 30_000, 30_000]);
  });

  it('applies full jitter but never waits less than a quarter second', () => {
    expect(nextDelayMs(3, () => 0.5)).toBe(4_000);
    expect(nextDelayMs(3, () => 0)).toBe(250);
  });
});

describe('parseServerMessage', () => {
  it('accepts the three server message types', () => {
    expect(parseServerMessage('{"type":"ready"}')).toEqual({ type: 'ready' });
    const task = { task_id: 't', state: 'running' };
    expect(parseServerMessage(JSON.stringify({ type: 'snapshot', task }))).toEqual({
      type: 'snapshot',
      task,
    });
    const event = { kind: 'state', task_id: 't', state: 'failed' };
    expect(parseServerMessage(JSON.stringify({ type: 'event', event }))).toEqual({
      type: 'event',
      event,
    });
  });

  it('rejects malformed input', () => {
    for (const text of [
      '',
      'null',
      '[]',
      '{"type":"event","event":{"kind":"other","task_id":"t","state":"x"}}',
      '{"type":"snapshot","task":{"task_id":1,"state":"x"}}',
    ]) {
      expect(parseServerMessage(text)).toBeNull();
    }
  });
});
