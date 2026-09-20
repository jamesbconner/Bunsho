import { describe, expect, it } from 'vitest';

import { makeBuildStatus } from '../test/fixtures';
import { BUILD_POLL_MS, pollInterval } from './queries';

describe('pollInterval', () => {
  it('polls only while a build runs and the live stream is not connected', () => {
    const running = makeBuildStatus({ state: 'running' });
    expect(pollInterval(running, false)).toBe(BUILD_POLL_MS);
    expect(pollInterval(running, true)).toBe(false);
  });

  it('never polls a finished build, no build, or an unknown state', () => {
    expect(pollInterval(makeBuildStatus({ state: 'succeeded' }), false)).toBe(false);
    expect(pollInterval(makeBuildStatus({ state: 'failed' }), false)).toBe(false);
    expect(pollInterval(null, false)).toBe(false);
    expect(pollInterval(undefined, false)).toBe(false);
  });
});
