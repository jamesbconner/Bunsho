import { ApiError, messageFor } from '../../api/errors';

/** What to tell the user when starting a build failed. */
export function startFailureMessage(error: unknown): string {
  // The server's 409 text carries the internal task id; the meaning is all the user needs.
  if (error instanceof ApiError && error.status === 409) return 'A build is already running.';
  return messageFor(error);
}
