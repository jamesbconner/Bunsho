/** The places in the header (and the phone drawer), in order. */
export const NAVIGATION = [
  { to: '/', label: 'Home' },
  { to: '/review', label: 'Study' },
  { to: '/stats', label: 'Statistics' },
  { to: '/settings', label: 'Settings' },
] as const;

/** The current page is the link whose address is exactly the path (no prefix matching). */
export function isCurrentPage(pathname: string, to: string): boolean {
  return pathname === to;
}

/** The wording beside every Log out control; the accessible description points at it. */
export const LOGOUT_NOTE = 'Logging out also ends this session on the server.';
