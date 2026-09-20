import { notifications } from '@mantine/notifications';
import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';

import { refreshSession } from '../api/client';
import { ApiError } from '../api/errors';
import { rawRequest } from '../api/http';
import type { components } from '../api/schema';
import { AuthContext, type AuthContextValue, type AuthStatus } from './authContext';
import { REFRESH_TOKEN_KEY, session } from './session';

type TokenResponse = components['schemas']['TokenResponse'];

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<AuthStatus>(() =>
    session.getRefreshToken() === null ? 'anonymous' : 'checking',
  );
  const [sessionExpired, setSessionExpired] = useState(false);

  const restore = useCallback(async () => {
    try {
      await refreshSession();
      setStatus('authenticated');
    } catch (error) {
      // Only a rejected refresh token means "logged out". A network error or a 5xx keeps the
      // remembered login: a server restart must never log anybody out.
      setStatus(error instanceof ApiError && error.status === 401 ? 'anonymous' : 'unreachable');
    }
  }, []);

  useEffect(() => {
    if (session.getRefreshToken() !== null) {
      // A one-off synchronisation with the server on mount: restore the remembered login.
      // eslint-disable-next-line react-hooks/set-state-in-effect -- setState runs after an await
      void restore();
    }
  }, [restore]);

  useEffect(
    () =>
      session.onExpired(() => {
        queryClient.clear();
        setSessionExpired(true);
        // The login page shows the lasting "Signed out" alert; this toast is the moment-of-expiry
        // cue (also on another page), worded differently so the two never repeat each other.
        notifications.show({
          color: 'yellow',
          title: 'Session ended',
          message: 'Log in again to continue.',
        });
        setStatus('anonymous');
      }),
    [queryClient],
  );

  // Another tab logged out: this one follows.
  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key === REFRESH_TOKEN_KEY && event.newValue === null) {
        session.clear();
        queryClient.clear();
        setStatus('anonymous');
      }
    };
    window.addEventListener('storage', onStorage);
    return () => {
      window.removeEventListener('storage', onStorage);
    };
  }, [queryClient]);

  const login = useCallback(async (username: string, password: string) => {
    const pair = await rawRequest<TokenResponse>('/auth/login', {
      method: 'POST',
      body: { username, password },
    });
    session.setTokens(pair);
    setSessionExpired(false);
    setStatus('authenticated');
  }, []);

  const logout = useCallback(() => {
    session.clear();
    queryClient.clear();
    setSessionExpired(false);
    setStatus('anonymous');
  }, [queryClient]);

  const retry = useCallback(() => {
    setStatus('checking');
    void restore();
  }, [restore]);

  const value = useMemo<AuthContextValue>(
    () => ({ status, sessionExpired, login, logout, retry }),
    [status, sessionExpired, login, logout, retry],
  );
  return <AuthContext value={value}>{children}</AuthContext>;
}
