import { createContext, useContext } from 'react';

import type { ConnectionState } from './BuildStream';

export const RealtimeContext = createContext<ConnectionState>({ kind: 'disconnected' });

/** The state of the live connection to the server (for the badge and the polling fallback). */
export function useConnectionState(): ConnectionState {
  return useContext(RealtimeContext);
}
