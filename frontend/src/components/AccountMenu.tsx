import { Button, Menu } from '@mantine/core';
import { useId } from '@mantine/hooks';

import { useAuth } from '../auth/authContext';
import { LOGOUT_NOTE } from './navigation';

/** The header's Account menu (desktop): Log out, with what it does written under it. */
export function AccountMenu() {
  const { logout } = useAuth();
  const noteId = useId();

  return (
    <Menu position="bottom-end" width={260}>
      <Menu.Target>
        <Button variant="subtle" size="xs">
          Account
        </Button>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Item onClick={logout} aria-describedby={noteId}>
          Log out
        </Menu.Item>
        <Menu.Label id={noteId}>{LOGOUT_NOTE}</Menu.Label>
      </Menu.Dropdown>
    </Menu>
  );
}
