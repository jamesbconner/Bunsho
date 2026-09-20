import { Button, Center, Loader, Stack, Text } from '@mantine/core';
import { Navigate, Outlet, useLocation } from 'react-router';

import { messageFor, NetworkError } from '../api/errors';
import { useAuth } from './authContext';

/** Renders the nested routes for a logged-in user; everybody else waits, retries or logs in. */
export function RequireAuth() {
  const { status, retry } = useAuth();
  const location = useLocation();

  switch (status) {
    case 'checking':
      return (
        <Center h="100vh">
          <Loader aria-label="Checking your session" />
        </Center>
      );
    case 'unreachable':
      return (
        <Center h="100vh">
          <Stack align="center">
            <Text>{messageFor(new NetworkError())}</Text>
            <Button onClick={retry}>Try again</Button>
          </Stack>
        </Center>
      );
    case 'anonymous':
      return <Navigate to="/login" replace state={{ from: location.pathname }} />;
    case 'authenticated':
      return <Outlet />;
  }
}
