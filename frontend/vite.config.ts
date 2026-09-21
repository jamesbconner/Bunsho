import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// Development proxy: the browser talks to the Vite server, which forwards the API (and its
// WebSocket) to the backend, so the dev setup needs no CORS. Override the target with
// VITE_API_TARGET when the backend is not on the default port.
const apiTarget = process.env.VITE_API_TARGET ?? 'http://127.0.0.1:8192';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: apiTarget, ws: true },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/api/schema.d.ts', 'src/test/**', 'src/main.tsx', 'src/**/*.test.{ts,tsx}'],
      thresholds: { lines: 80, functions: 80, branches: 80, statements: 80 },
    },
  },
});
