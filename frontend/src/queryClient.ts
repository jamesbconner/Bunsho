import { QueryClient } from '@tanstack/react-query';

import { ApiError, NetworkError } from './api/errors';

const MAX_RETRIES = 2;

/** Retry only what can succeed later: connection failures and server errors, never a 4xx. */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (failureCount >= MAX_RETRIES) return false;
  return error instanceof NetworkError || (error instanceof ApiError && error.status >= 500);
}

/** The application's query client (tests use `createTestQueryClient`, which never retries). */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: shouldRetry, staleTime: 30_000 },
      mutations: { retry: false },
    },
  });
}
