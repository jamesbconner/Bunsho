import { Badge } from '@mantine/core';

import { useSecondsUntil } from '../hooks/useCountdown';
import type { ConnectionState } from './BuildStream';
import { useConnectionState } from './realtimeContext';

function describe(state: ConnectionState, secondsLeft: number): { color: string; label: string } {
  switch (state.kind) {
    case 'connected':
      return { color: 'green', label: 'Live' };
    case 'connecting':
      return { color: 'yellow', label: 'Connecting…' };
    case 'retrying':
      return { color: 'orange', label: `Reconnecting in ${String(secondsLeft)} s` };
    case 'disconnected':
      return { color: 'red', label: 'Offline' };
  }
}

/** The state of the live connection, always visible in the header. */
export function ConnectionBadge() {
  const state = useConnectionState();
  const secondsLeft = useSecondsUntil(state.kind === 'retrying' ? state.retryAt : null);
  const { color, label } = describe(state, secondsLeft);
  return (
    <Badge color={color} variant="dot" role="status" aria-label={`Connection: ${label}`}>
      {label}
    </Badge>
  );
}
