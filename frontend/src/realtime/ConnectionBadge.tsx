import { Badge } from '@mantine/core';

import { useSecondsUntil } from '../hooks/useCountdown';
import type { ConnectionState } from './BuildStream';
import { useConnectionState } from './realtimeContext';

function describe(state: ConnectionState): { color: string; label: string } {
  switch (state.kind) {
    case 'connected':
      return { color: 'green', label: 'Live' };
    case 'connecting':
      return { color: 'yellow', label: 'Connecting…' };
    case 'retrying':
      return { color: 'orange', label: 'Reconnecting…' };
    case 'disconnected':
      return { color: 'red', label: 'Offline' };
  }
}

/** The state of the live connection, always visible in the header. */
export function ConnectionBadge() {
  const state = useConnectionState();
  const secondsLeft = useSecondsUntil(state.kind === 'retrying' ? state.retryAt : null);
  const { color, label } = describe(state);
  return (
    <Badge color={color} variant="dot" role="status" aria-label={`Connection: ${label}`}>
      {label}
      {/* The countdown is visual only: a ticking live region would be announced every second. */}
      {state.kind === 'retrying' && <span aria-hidden="true"> in {String(secondsLeft)} s</span>}
    </Badge>
  );
}
