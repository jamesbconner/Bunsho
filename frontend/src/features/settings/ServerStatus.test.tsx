import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { renderWithProviders } from '../../test/render';
import { server } from '../../test/server';
import { ServerStatus } from './ServerStatus';

const REPORT = {
  status: 'degraded',
  version: '1.2.0',
  components: {
    database: { status: 'ok', detail: 'progress.db reachable', latency_ms: 1.2 },
    content: { status: 'degraded', detail: 'content.db is older than the deck', latency_ms: 0.4 },
  },
};

describe('ServerStatus', () => {
  it('shows the version, the overall state and every component', async () => {
    server.use(http.get('/api/v1/health', () => HttpResponse.json(REPORT)));
    renderWithProviders(<ServerStatus />);
    const region = await screen.findByRole('region', { name: 'Server' });
    expect(await within(region).findByText('Version 1.2.0')).toBeInTheDocument();
    expect(within(region).getAllByText('Degraded')).toHaveLength(2); // overall + the content component
    expect(within(region).getByText('progress.db reachable')).toBeInTheDocument();
    expect(within(region).getByText('content.db is older than the deck')).toBeInTheDocument();
  });

  it('shows a failing component from a 503 report instead of hiding it', async () => {
    const report = {
      ...REPORT,
      status: 'error',
      components: { content: { status: 'error', detail: 'content.db is missing', latency_ms: 0 } },
    };
    server.use(http.get('/api/v1/health', () => HttpResponse.json(report, { status: 503 })));
    renderWithProviders(<ServerStatus />);
    expect(await screen.findByText('content.db is missing')).toBeInTheDocument();
    expect(screen.getAllByText('Problem')).toHaveLength(2); // overall + the content component
  });

  it('explains a failed check and can try again', async () => {
    let calls = 0;
    server.use(
      http.get('/api/v1/health', () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.text('<html>bad gateway</html>', { status: 503 })
          : HttpResponse.json(REPORT);
      }),
    );
    renderWithProviders(<ServerStatus />);
    expect(await screen.findByText("Couldn't check the server")).toBeInTheDocument();
    expect(
      screen.getByText('The server answered, but not with a health report.'),
    ).toBeInTheDocument();
    expect(screen.queryByText(/isn't built/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('Version 1.2.0')).toBeInTheDocument();
  });
});
