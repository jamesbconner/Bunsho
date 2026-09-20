import { FetchError } from 'ofetch';

/** An HTTP error answered by the API. */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;
  /** For 422 responses: the first message per field name. */
  readonly fieldErrors: Readonly<Record<string, string>>;
  /** For 429 responses: seconds to wait, from the Retry-After header. */
  readonly retryAfterSeconds: number | null;

  constructor(
    status: number,
    detail: string,
    fieldErrors: Record<string, string> = {},
    retryAfterSeconds: number | null = null,
  ) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
    this.fieldErrors = fieldErrors;
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

/** The server could not be reached at all (offline, restarting, DNS...). */
export class NetworkError extends Error {
  constructor() {
    super("Can't reach the server");
    this.name = 'NetworkError';
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function fieldErrorsOf(detail: unknown[]): Record<string, string> {
  const result: Record<string, string> = {};
  for (const item of detail) {
    if (!isRecord(item) || !Array.isArray(item.loc) || typeof item.msg !== 'string') continue;
    const location: unknown[] = item.loc;
    const name = location.at(-1);
    if (typeof name === 'string' && !(name in result)) result[name] = item.msg;
  }
  return result;
}

/** Turn an ofetch failure into an ApiError or NetworkError; leave every other error alone. */
export function toClientError(error: unknown): unknown {
  if (!(error instanceof FetchError)) return error;
  if (error.response === undefined) return new NetworkError();
  const data: unknown = error.data;
  const body = isRecord(data) ? data.detail : undefined;
  const retryAfter = Number.parseInt(error.response.headers.get('Retry-After') ?? '', 10);
  return new ApiError(
    error.response.status,
    typeof body === 'string' ? body : 'Request failed',
    Array.isArray(body) ? fieldErrorsOf(body) : {},
    Number.isNaN(retryAfter) ? null : retryAfter,
  );
}

/** A message for the user: never a raw status code or stack. */
export function messageFor(error: unknown): string {
  if (error instanceof NetworkError) {
    return "Can't reach the server. Check that Bunshō is running, then try again.";
  }
  if (error instanceof ApiError) {
    switch (error.status) {
      case 401:
        return 'Your session has expired. Please log in again.';
      case 409:
        return error.detail;
      case 422:
        return 'Some fields are invalid.';
      case 429:
        return error.retryAfterSeconds === null
          ? 'Too many attempts. Please wait a moment and try again.'
          : `Too many attempts. Please wait ${String(error.retryAfterSeconds)} seconds and try again.`;
      case 503:
        return "Content isn't built yet.";
      default:
        return error.status >= 500
          ? 'The server had a problem. Please try again in a moment.'
          : error.detail;
    }
  }
  return 'Something went wrong. Please try again.';
}
