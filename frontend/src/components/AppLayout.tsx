import { AppShell, Burger, Button, Group, NavLink, Stack, Text, Title } from '@mantine/core';
import { useDisclosure, useId } from '@mantine/hooks';
import { Suspense } from 'react';
import { Link, Outlet, useLocation } from 'react-router';

import { useAuth } from '../auth/authContext';
import { ConnectionBadge } from '../realtime/ConnectionBadge';
import { ColorSchemeToggle } from './ColorSchemeToggle';
import { ErrorBoundary } from './ErrorBoundary';
import { PageLoader } from './PageLoader';

const NAVIGATION = [
  { to: '/', label: 'Home' },
  { to: '/review', label: 'Study' },
  { to: '/stats', label: 'Statistics' },
  { to: '/settings', label: 'Settings' },
  { to: '/build', label: 'Build content' },
] as const;

/** The frame around every logged-in page: header, navigation and the page itself. */
export function AppLayout() {
  const [opened, { toggle, close }] = useDisclosure(false);
  const { logout } = useAuth();
  const { pathname } = useLocation();
  const logoutNoteId = useId();

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
          </Group>
        </Group>
      </AppShell.Header>
      <AppShell.Navbar p="md">
        <Stack justify="space-between" h="100%">
          <div>
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
          </div>
          {/* In the navbar (not the header) so the notice is visible text in the burger drawer too. */}
          <Stack gap={4}>
            <Button variant="subtle" onClick={logout} aria-describedby={logoutNoteId}>
              Log out
            </Button>
            <Text id={logoutNoteId} size="xs" c="dimmed">
              Logging out only affects this browser: the server cannot end sessions yet.
            </Text>
          </Stack>
        </Stack>
      </AppShell.Navbar>
      <AppShell.Main>
        <ErrorBoundary key={pathname}>
          <Suspense fallback={<PageLoader />}>
            <Outlet />
          </Suspense>
        </ErrorBoundary>
      </AppShell.Main>
    </AppShell>
  );
}
