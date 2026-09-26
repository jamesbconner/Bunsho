/** The literal the server replaces with a fresh nonce on every page load (see frontend/index.html). */
export const CSP_NONCE_PLACEHOLDER = '__CSP_NONCE__';

/**
 * The Content-Security-Policy nonce the server put in the page, for Mantine's runtime `<style>`
 * elements. Undefined when there is none: no tag, no content, or the placeholder still in place
 * (the Vite dev server serves the file as is, and needs no CSP).
 */
export function readCspNonce(): string | undefined {
  const content = document.querySelector('meta[name="csp-nonce"]')?.getAttribute('content')?.trim();
  if (content === undefined || content === '' || content === CSP_NONCE_PLACEHOLDER)
    return undefined;
  return content;
}

/**
 * Read the nonce (see readCspNonce) and also publish it as `__webpack_nonce__`, the global that
 * `get-nonce` reads on behalf of react-style-singleton, which builds the `<style>` tag behind
 * Mantine's scroll lock (Modal and friends). MantineProvider's getStyleNonce does not reach it.
 * Idempotent; leaves the global alone when there is no nonce (development).
 */
export function installCspNonce(): string | undefined {
  const nonce = readCspNonce();
  if (nonce !== undefined) (globalThis as { __webpack_nonce__?: string }).__webpack_nonce__ = nonce;
  return nonce;
}
