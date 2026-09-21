import { screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../test/render';
import { ErrorBoundary } from './ErrorBoundary';

function Broken({ fail }: { fail: boolean }) {
  if (fail) throw new Error('secret internal detail');
  return <p>All good</p>;
}

describe('ErrorBoundary', () => {
  beforeEach(() => {
    // React logs a caught render error; keep the test output quiet.
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders its children when nothing is wrong', () => {
    renderWithProviders(
      <ErrorBoundary>
        <Broken fail={false} />
      </ErrorBoundary>,
    );
    expect(screen.getByText('All good')).toBeInTheDocument();
  });

  it('shows a friendly page, never the error itself', () => {
    renderWithProviders(
      <ErrorBoundary>
        <Broken fail />
      </ErrorBoundary>,
    );
    expect(screen.getByRole('heading', { name: 'Something went wrong' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reload the page' })).toBeInTheDocument();
    expect(screen.queryByText(/secret internal detail/)).not.toBeInTheDocument();
  });

  it('logs the details to the console', () => {
    renderWithProviders(
      <ErrorBoundary>
        <Broken fail />
      </ErrorBoundary>,
    );
    expect(console.error).toHaveBeenCalledWith(
      'Rendering failed',
      expect.objectContaining({ message: 'secret internal detail' }),
      expect.any(String),
    );
  });

  it('starts over when it gets a new key (the layout keys it by route)', () => {
    const { rerender } = renderWithProviders(
      <ErrorBoundary key="a">
        <Broken fail />
      </ErrorBoundary>,
    );
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    rerender(
      <ErrorBoundary key="b">
        <Broken fail={false} />
      </ErrorBoundary>,
    );
    expect(screen.getByText('All good')).toBeInTheDocument();
  });
});
