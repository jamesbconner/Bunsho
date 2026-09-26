import {
  AppShell,
  Box,
  Burger,
  Button,
  Container,
  Group,
  Title,
  useMantineTheme,
} from '@mantine/core';
import { useDisclosure, useMediaQuery } from '@mantine/hooks';
import { Link, Outlet, useLocation } from 'react-router';

import { ConnectionBadge } from '../realtime/ConnectionBadge';
import { AccountMenu } from './AccountMenu';
import { ColorSchemeToggle } from './ColorSchemeToggle';
import { NavDrawer } from './NavDrawer';
import { isCurrentPage, NAVIGATION } from './navigation';
import { PAGE_WIDTHS } from './pageWidths';

/**
 * The frame around every logged-in page: the header (title, page links, connection state, theme,
 * account) and the routed page. The page's own width comes from the `PageWidth` layout route
 * around it.
 */
export function AppLayout() {
  const [drawerOpened, { toggle, close }] = useDisclosure(false);
  const { pathname } = useLocation();
  const theme = useMantineTheme();
  const isWide = useMediaQuery(`(min-width: ${theme.breakpoints.sm})`);
  // The drawer is for phones only. Past `sm` the burger is hidden, so an open drawer would be left
  // invisible with the page's scroll still locked; derive "shown" instead of trusting the state.
  const drawerShown = drawerOpened && !isWide;

  return (
    <AppShell header={{ height: 56 }} padding="md">
      <AppShell.Header>
        {/* The outer padding + a px={0} container line the header up with the page columns below. */}
        <Box h="100%" px="md">
          <Container size={PAGE_WIDTHS.wide} px={0} h="100%">
            <Group h="100%" justify="space-between" wrap="nowrap">
              <Group gap="lg" wrap="nowrap">
                <Group gap="sm" wrap="nowrap">
                  <Burger
                    opened={drawerShown}
                    onClick={toggle}
                    hiddenFrom="sm"
                    size="sm"
                    aria-label="Toggle navigation"
                    aria-expanded={drawerShown}
                  />
                  <Title order={3} style={{ whiteSpace: 'nowrap' }}>
                    Bunshō <span lang="ja">文章</span>
                  </Title>
                </Group>
                <Box component="nav" aria-label="Main" visibleFrom="sm">
                  <Group gap={4} wrap="nowrap">
                    {NAVIGATION.map((item) => {
                      const current = isCurrentPage(pathname, item.to);
                      return (
                        <Button
                          key={item.to}
                          component={Link}
                          to={item.to}
                          variant={current ? 'light' : 'subtle'}
                          color={current ? undefined : 'gray'}
                          aria-current={current ? 'page' : undefined}
                        >
                          {item.label}
                        </Button>
                      );
                    })}
                  </Group>
                </Box>
              </Group>
              <Group gap="xs" wrap="nowrap">
                <ConnectionBadge />
                {/* On a phone the theme toggle lives in the drawer; the bar has no room for it. */}
                <Box visibleFrom="sm">
                  <ColorSchemeToggle />
                </Box>
                <Box visibleFrom="sm">
                  <AccountMenu />
                </Box>
              </Group>
            </Group>
          </Container>
        </Box>
      </AppShell.Header>
      <NavDrawer opened={drawerShown} onClose={close} />
      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}
