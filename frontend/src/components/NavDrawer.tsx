import { Button, Divider, Drawer, NavLink, Stack, Text } from '@mantine/core';
import { useId } from '@mantine/hooks';
import { Link, useLocation } from 'react-router';

import { useAuth } from '../auth/authContext';
import { ColorSchemeToggle } from './ColorSchemeToggle';
import { isCurrentPage, LOGOUT_NOTE, NAVIGATION } from './navigation';

interface NavDrawerProps {
  opened: boolean;
  onClose: () => void;
}

/** The navigation on a phone: opened by the header's burger; unmounted while closed. */
export function NavDrawer({ opened, onClose }: NavDrawerProps) {
  const { logout } = useAuth();
  const { pathname } = useLocation();
  const noteId = useId();

  return (
    <Drawer opened={opened} onClose={onClose} title="Menu" size="xs" hiddenFrom="sm">
      <Stack gap="md">
        <nav aria-label="Pages">
          {NAVIGATION.map((item) => (
            <NavLink
              key={item.to}
              component={Link}
              to={item.to}
              label={item.label}
              active={isCurrentPage(pathname, item.to)}
              aria-current={isCurrentPage(pathname, item.to) ? 'page' : undefined}
              onClick={onClose}
            />
          ))}
        </nav>
        <Divider />
        <ColorSchemeToggle />
        <Divider />
        <Stack gap={4}>
          <Button variant="subtle" onClick={logout} aria-describedby={noteId}>
            Log out
          </Button>
          <Text id={noteId} size="xs" c="dimmed">
            {LOGOUT_NOTE}
          </Text>
        </Stack>
      </Stack>
    </Drawer>
  );
}
