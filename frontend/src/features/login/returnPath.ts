function isSameSitePath(path: string): boolean {
  if (!path.startsWith('/') || path.startsWith('//')) return false;
  for (const char of path) {
    const code = char.codePointAt(0) ?? 0;
    // A backslash reads as a slash and control characters are stripped from a URL by browsers,
    // so `/\evil.example` and `/<tab>/evil.example` would both turn into `//evil.example`.
    if (char === '\\' || code < 0x20 || code === 0x7f) return false;
  }
  return true;
}

/** Where to go after logging in: the page the visitor was heading for, else the home page. */
export function returnPath(state: unknown): string {
  if (typeof state === 'object' && state !== null && 'from' in state) {
    const from = state.from;
    if (typeof from === 'string' && isSameSitePath(from)) return from;
  }
  return '/';
}
