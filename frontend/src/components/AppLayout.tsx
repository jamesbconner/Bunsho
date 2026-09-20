import { AppShell, Burger, Button, Group, NavLink, Title } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { Link, Outlet, useLocation } from 'react-router';

import { useAuth } from '../auth/authContext';
import { ConnectionBadge } from '../realtime/ConnectionBadge';
import { ColorSchemeToggle } from './ColorSchemeToggle';
import { ErrorBoundary } from './ErrorBoundary';

const NAVIGATION = [
  { to: '/', label: 'Home' },
  { to: '/build', label: 'Build content' },
] as const;

/** The frame around every logged-in page: header, navigation and the page itself. */
export function AppLayout() {
  const [opened, { toggle, close }] = useDisclosure(false);
  const { logout } = useAuth();
  const { pathname } = useLocation();

  return (
    <AppShell
      header={{ height: 56 }}
      navbar={{ width: 220, breakpoint: 'sm', collapsed: { mobile: !opened } }}
      padding="md"
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Burger
              opened={opened}
              onClick={toggle}
              hiddenFrom="sm"
              size="sm"
              aria-label="Toggle navigation"
            />
            <Title order={3}>
              Bunshō <span lang="ja">文章</span>
            </Title>
          </Group>
          <Group gap="xs" wrap="nowrap">
            <ConnectionBadge />
            <ColorSchemeToggle />
            <Button
              variant="subtle"
              onClick={logout}
              title="Logs out this browser only; the server cannot end sessions yet"
            >
              Log out
            </Button>
          </Group>
        </Group>
      </AppShell.Header>
      <AppShell.Navbar p="md">
        {NAVIGATION.map((item) => (
          <NavLink
            key={item.to}
            component={Link}
            to={item.to}
            label={item.label}
            active={pathname === item.to}
            onClick={close}
          />
        ))}
      </AppShell.Navbar>
      <AppShell.Main>
        <ErrorBoundary key={pathname}>
          <Outlet />
        </ErrorBoundary>
      </AppShell.Main>
    </AppShell>
  );
}
