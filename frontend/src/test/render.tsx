import { MantineProvider } from '@mantine/core';
import { Notifications } from '@mantine/notifications';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, type RenderResult } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter, type InitialEntry } from 'react-router';

import { theme } from '../theme';

/** A query client for tests: no retries, so a failing request fails the test immediately. */
export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

interface RenderOptions {
  initialEntries?: InitialEntry[];
  queryClient?: QueryClient;
}

/** Render `ui` inside the providers every screen needs (theme, query client, router). */
export function renderWithProviders(
  ui: ReactElement,
  { initialEntries = ['/'], queryClient = createTestQueryClient() }: RenderOptions = {},
): RenderResult & { queryClient: QueryClient } {
  const result = render(
    <MantineProvider theme={theme} env="test">
      <Notifications />
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={initialEntries}>{ui}</MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
  return { ...result, queryClient };
}
