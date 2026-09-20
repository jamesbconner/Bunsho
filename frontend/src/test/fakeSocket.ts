import type { SocketLike } from '../realtime/BuildStream';

/** A scriptable stand-in for the browser WebSocket. */
export class FakeSocket implements SocketLike {
  readonly url: string;
  readonly sent: string[] = [];
  closed = false;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;

  constructor(url: string) {
    this.url = url;
  }

  send(data: string): void {
    this.sent.push(data);
  }

  close(): void {
    this.closed = true;
  }

  /** The connection was established (the client will send its auth message). */
  open(): void {
    this.onopen?.(new Event('open'));
  }

  /** The server sent a frame: an object is sent as JSON, a string as is. */
  receive(payload: unknown): void {
    const data = typeof payload === 'string' ? payload : JSON.stringify(payload);
    this.onmessage?.(new MessageEvent('message', { data }));
  }

  /** The server (or the network) closed the connection. */
  serverClose(code: number): void {
    this.onclose?.(new CloseEvent('close', { code }));
  }
}
