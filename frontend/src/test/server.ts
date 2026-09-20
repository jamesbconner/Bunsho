import { setupServer } from 'msw/node';

/** The shared MSW server. Tests add handlers with `server.use(...)`; each test starts clean. */
export const server = setupServer();
