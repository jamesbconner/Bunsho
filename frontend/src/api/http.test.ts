import { describe, expect, it } from 'vitest';

import { apiUrl, wsUrl } from './http';

describe('wsUrl', () => {
  it('turns an http origin into ws, keeps the port and prefixes the API path', () => {
    window.history.replaceState(null, '', '/somewhere');
    const url = new URL(wsUrl('/ws/tasks'));
    expect(url.protocol).toBe('ws:');
    expect(url.host).toBe(window.location.host);
    expect(url.pathname).toBe('/api/v1/ws/tasks');
  });

  it('turns an https origin into wss', () => {
    const previous = window.location;
    Object.defineProperty(window, 'location', {
      value: new URL('https://example.test:8443/app'),
      configurable: true,
    });
    try {
      expect(wsUrl('/ws/tasks')).toBe('wss://example.test:8443/api/v1/ws/tasks');
    } finally {
      Object.defineProperty(window, 'location', { value: previous, configurable: true });
    }
  });

  it('carries no query string, fragment or credentials (the token is sent as a message)', () => {
    const url = new URL(wsUrl('/ws/tasks'));
    expect(url.search).toBe('');
    expect(url.hash).toBe('');
    expect(url.username).toBe('');
    expect(url.password).toBe('');
  });
});

describe('apiUrl', () => {
  it('prefixes the API path onto the current origin', () => {
    expect(apiUrl('/content/summary')).toBe(`${window.location.origin}/api/v1/content/summary`);
  });
});
