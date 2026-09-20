import type { components } from '../api/schema';

type Schemas = components['schemas'];

export type BuildStatus = Schemas['BuildStatusResponse'];
export type BuildEvent = Schemas['BuildEventModel'];

/** What the server sends on `/ws/tasks` after the client authenticated. */
export type ServerMessage =
  | { type: 'ready' }
  | { type: 'snapshot'; task: BuildStatus }
  | { type: 'event'; event: BuildEvent };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

/** Parse one text frame. Anything that is not a well-formed server message returns null. */
export function parseServerMessage(text: string): ServerMessage | null {
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    return null;
  }
  if (!isRecord(value)) return null;
  switch (value.type) {
    case 'ready':
      return { type: 'ready' };
    case 'snapshot':
      return isRecord(value.task) &&
        typeof value.task.task_id === 'string' &&
        typeof value.task.state === 'string'
        ? { type: 'snapshot', task: value.task as BuildStatus }
        : null;
    case 'event':
      return isRecord(value.event) &&
        typeof value.event.task_id === 'string' &&
        typeof value.event.state === 'string' &&
        (value.event.kind === 'progress' || value.event.kind === 'state')
        ? { type: 'event', event: value.event as BuildEvent }
        : null;
    default:
      return null;
  }
}
