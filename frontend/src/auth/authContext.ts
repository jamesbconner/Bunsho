import { createContext, useContext } from 'react';

export type AuthStatus = 'checking' | 'authenticated' | 'anonymous' | 'unreachable';

export interface AuthContextValue {
  status: AuthStatus;
  /** True after the server ended the session (or the remembered login had expired). */
  sessionExpired: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  /** Try again after "unreachable". */
  retry: () => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (value === null) throw new Error('useAuth must be used inside <AuthProvider>');
  return value;
}
