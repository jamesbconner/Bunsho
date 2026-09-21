import { describe, expect, it } from 'vitest';

import { ApiError, NetworkError } from './api/errors';
import { createQueryClient, shouldRetry } from './queryClient';

describe('shouldRetry', () => {
  it('retries connection failures and server errors, twice at most', () => {
    expect(shouldRetry(0, new NetworkError())).toBe(true);
    expect(shouldRetry(1, new ApiError(503, 'busy'))).toBe(true);
    expect(shouldRetry(2, new NetworkError())).toBe(false);
  });

  it('never retries client errors or unknown errors', () => {
    expect(shouldRetry(0, new ApiError(401, 'no'))).toBe(false);
    expect(shouldRetry(0, new ApiError(404, 'no'))).toBe(false);
    expect(shouldRetry(0, new ApiError(422, 'no'))).toBe(false);
    expect(shouldRetry(0, new Error('bug'))).toBe(false);
  });
});

describe('createQueryClient', () => {
  it('uses the retry policy for queries and never retries mutations', () => {
    const defaults = createQueryClient().getDefaultOptions();
    expect(defaults.queries?.retry).toBe(shouldRetry);
    expect(defaults.mutations?.retry).toBe(false);
  });
});
