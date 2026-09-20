import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useState, type ReactNode } from 'react';

import { ensureAccessToken, refreshSession } from '../api/client';
import { wsUrl } from '../api/http';
import { applyMessage } from './applyMessage';
import { BuildStream, type ConnectionState, type SocketLike } from './BuildStream';
import { RealtimeContext } from './realtimeContext';

interface RealtimeProviderProps {
  children: ReactNode;
  /** Test seam: replaces the browser WebSocket. Must be a stable reference. */
  createSocket?: (url: string) => SocketLike;
}

/** Keeps one connection to the server's task stream open while the user is logged in. */
export function RealtimeProvider({ children, createSocket }: RealtimeProviderProps) {
  const queryClient = useQueryClient();
  const [state, setState] = useState<ConnectionState>({ kind: 'connecting' });

  useEffect(() => {
    const stream = new BuildStream({
      url: wsUrl('/ws/tasks'),
      getToken: ensureAccessToken,
      refreshAuth: async () => {
        try {
          await refreshSession(); // a rejected refresh token ends the session (AuthProvider)
          return true;
        } catch {
          return false;
        }
      },
      onState: setState,
      onMessage: (message) => {
        applyMessage(queryClient, message);
      },
      createSocket,
    });
    stream.start();
    return () => {
      stream.stop();
    };
  }, [queryClient, createSocket]);

  return <RealtimeContext value={state}>{children}</RealtimeContext>;
}
