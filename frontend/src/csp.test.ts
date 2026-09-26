import { afterEach, describe, expect, it } from 'vitest';

import { CSP_NONCE_PLACEHOLDER, readCspNonce } from './csp';

function setMeta(content: string | null) {
  const meta = document.createElement('meta');
  meta.setAttribute('name', 'csp-nonce');
  if (content !== null) meta.setAttribute('content', content);
  document.head.appendChild(meta);
}

describe('readCspNonce', () => {
  afterEach(() => {
    document.head.querySelectorAll('meta[name="csp-nonce"]').forEach((node) => {
      node.remove();
    });
  });

  it('uses the same placeholder the server replaces', () => {
    expect(CSP_NONCE_PLACEHOLDER).toBe('__CSP_NONCE__');
  });

  it('returns the nonce the server put in the page', () => {
    setMeta('abc123+/==');
    expect(readCspNonce()).toBe('abc123+/==');
  });

  it('returns undefined without the tag', () => {
    expect(readCspNonce()).toBeUndefined();
  });

  it('returns undefined for a tag without content', () => {
    setMeta(null);
    expect(readCspNonce()).toBeUndefined();
  });

  it('returns undefined for an empty or blank value', () => {
    setMeta('   ');
    expect(readCspNonce()).toBeUndefined();
  });

  it('returns undefined while the placeholder is still there (npm run dev)', () => {
    setMeta(CSP_NONCE_PLACEHOLDER);
    expect(readCspNonce()).toBeUndefined();
  });
});
