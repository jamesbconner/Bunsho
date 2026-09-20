import { nextDelayMs } from './backoff';
import { parseServerMessage, type ServerMessage } from './messages';

export type ConnectionState =
  | { kind: 'connecting' }
  | { kind: 'connected' }
  | { kind: 'retrying'; retryAt: number }
  | { kind: 'disconnected' };

/** The part of the browser WebSocket this class uses (so tests can substitute a fake). */
export interface SocketLike {
  onopen: ((event: Event) => void) | null;
  onmessage: ((event: MessageEvent) => void) | null;
  onclose: ((event: CloseEvent) => void) | null;
  onerror: ((event: Event) => void) | null;
  send: (data: string) => void;
  close: () => void;
}

export interface BuildStreamOptions {
  /** The ws:// or wss:// URL of the task stream. */
  url: string;
  /** A usable access token, refreshed first if needed. Called before every connection attempt. */
  getToken: () => Promise<string>;
  /** Refresh the session after the server closed with 1008. Resolves true when it worked. */
  refreshAuth: () => Promise<boolean>;
  onState: (state: ConnectionState) => void;
  /** Called for every `snapshot` and `event` message (`ready` is handled internally). */
  onMessage: (message: Exclude<ServerMessage, { type: 'ready' }>) => void;
  createSocket?: (url: string) => SocketLike;
  random?: () => number;
  now?: () => number;
}

/** The server closes with this code when the auth message was missing, malformed or rejected. */
const POLICY_VIOLATION = 1008;

/**
 * A reconnecting client of the server's task stream. It authenticates with its first message,
 * reports its connection state, forwards snapshots and events, reconnects with exponential
 * backoff and jitter, and on an authentication failure (close code 1008) refreshes the session and
 * reconnects once before giving up. Framework-free so it can be tested with a fake socket.
 */
export class BuildStream {
  private readonly options: BuildStreamOptions;
  private socket: SocketLike | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private attempt = 0;
  private authRetried = false;
  private stopped = true;
  /** Incremented on every connection attempt and on stop, so stale callbacks can be ignored. */
  private generation = 0;

  constructor(options: BuildStreamOptions) {
    this.options = options;
  }

  start(): void {
    if (!this.stopped) return;
    this.stopped = false;
    this.attempt = 0;
    this.authRetried = false;
    void this.connect();
  }

  stop(): void {
    this.stopped = true;
    this.generation += 1;
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    this.detachSocket();
    this.options.onState({ kind: 'disconnected' });
  }

  private detachSocket(): void {
    const socket = this.socket;
    this.socket = null;
    if (socket === null) return;
    socket.onopen = null;
    socket.onmessage = null;
    socket.onclose = null;
    socket.onerror = null;
    socket.close();
  }

  private async connect(): Promise<void> {
    this.generation += 1;
    const generation = this.generation;
    this.options.onState({ kind: 'connecting' });
    let token: string;
    try {
      token = await this.options.getToken();
    } catch {
      if (!this.stopped && generation === this.generation) this.scheduleRetry();
      return;
    }
    if (this.stopped || generation !== this.generation) return;

    const socket = (this.options.createSocket ?? ((url) => new WebSocket(url)))(this.options.url);
    this.socket = socket;
    socket.onopen = () => {
      socket.send(JSON.stringify({ type: 'auth', token }));
    };
    socket.onmessage = (event) => {
      if (generation === this.generation) this.handleFrame(event.data);
    };
    socket.onclose = (event) => {
      if (generation === this.generation) void this.handleClose(event.code, generation);
    };
    socket.onerror = () => {
      // A close event always follows an error; the reconnect logic lives there.
    };
  }

  private handleFrame(data: unknown): void {
    const message = typeof data === 'string' ? parseServerMessage(data) : null;
    if (message === null) return;
    if (message.type === 'ready') {
      this.attempt = 0;
      this.authRetried = false;
      this.options.onState({ kind: 'connected' });
      return;
    }
    this.options.onMessage(message);
  }

  private async handleClose(code: number, generation: number): Promise<void> {
    this.socket = null;
    if (code !== POLICY_VIOLATION) {
      this.scheduleRetry();
      return;
    }
    if (this.authRetried) {
      this.options.onState({ kind: 'disconnected' });
      return;
    }
    this.authRetried = true;
    const refreshed = await this.options.refreshAuth().catch(() => false);
    if (this.stopped || generation !== this.generation) return;
    if (refreshed) {
      void this.connect();
    } else {
      this.options.onState({ kind: 'disconnected' });
    }
  }

  private scheduleRetry(): void {
    const delay = nextDelayMs(this.attempt, this.options.random);
    this.attempt += 1;
    const now = this.options.now ?? Date.now;
    this.options.onState({ kind: 'retrying', retryAt: now() + delay });
    this.timer = setTimeout(() => {
      this.timer = null;
      void this.connect();
    }, delay);
  }
}
