import { act, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { lazy } from 'react';
import { Link, Route, Routes } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../test/render';
import { PageWidth } from './PageWidth';
import { PAGE_WIDTHS } from './pageWidths';

let releaseSlowPage: () => void = () => undefined;
const SlowPage = lazy(
  () =>
    new Promise<{ default: () => React.JSX.Element }>((resolve) => {
      releaseSlowPage = () => {
        resolve({ default: () => <p>Slow page loaded</p> });
      };
    }),
);

function Broken(): React.JSX.Element {
  throw new Error('boom');
}

function renderRoutes(initialEntries: string[]) {
  return renderWithProviders(
    <Routes>
      <Route element={<PageWidth size="wide" />}>
        <Route index element={<p>Wide page</p>} />
        <Route path="slow" element={<SlowPage />} />
      </Route>
      <Route element={<PageWidth size="narrow" />}>
        <Route path="narrow" element={<p>Narrow page</p>} />
        <Route path="broken" element={<Broken />} />
      </Route>
    </Routes>,
    { initialEntries },
  );
}

function widthOf(text: string): string | null {
  return screen.getByText(text).closest('[data-width]')?.getAttribute('data-width') ?? null;
}

describe('PageWidth', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('offers a narrow and a wide column, in that order of size', () => {
    expect(PAGE_WIDTHS.narrow).toBe(720);
    expect(PAGE_WIDTHS.wide).toBe(1100);
    expect(PAGE_WIDTHS.narrow).toBeLessThan(PAGE_WIDTHS.wide);
  });

  it('puts each page in the column its layout route asks for', () => {
    renderRoutes(['/']);
    expect(widthOf('Wide page')).toBe('wide');
  });

  it('limits the column to its width', () => {
    renderRoutes(['/narrow']);
    const column = screen.getByText('Narrow page').closest<HTMLElement>('[data-width]');
    // 720 px is 45 rem; Mantine wraps it in a scale factor.
    expect(column?.style.getPropertyValue('--container-size')).toContain('45rem');
  });

  it('shows the loading indicator inside the column, then the page', async () => {
    renderRoutes(['/slow']);
    const loader = screen.getByRole('status', { name: 'Loading page' });
    expect(loader.closest('[data-width="wide"]')).not.toBeNull();
    await act(async () => {
      releaseSlowPage();
      await Promise.resolve();
    });
    expect(await screen.findByText('Slow page loaded')).toBeInTheDocument();
    expect(widthOf('Slow page loaded')).toBe('wide');
    expect(screen.queryByRole('status', { name: 'Loading page' })).not.toBeInTheDocument();
  });

  it('shows a page that fails to render inside the column', () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    renderRoutes(['/broken']);
    const heading = screen.getByRole('heading', { name: 'Something went wrong' });
    expect(heading.closest('[data-width="narrow"]')).not.toBeNull();
  });
});

describe('PageWidth error reset', () => {
  it('leaves the error page behind when the user navigates away', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    renderWithProviders(
      <>
        <Link to="/ok">Go to ok</Link>
        <Routes>
          <Route element={<PageWidth size="narrow" />}>
            <Route path="bad" element={<Broken />} />
            <Route path="ok" element={<p>Fine page</p>} />
          </Route>
        </Routes>
      </>,
      { initialEntries: ['/bad'] },
    );
    expect(screen.getByRole('heading', { name: 'Something went wrong' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('link', { name: 'Go to ok' }));
    expect(screen.getByText('Fine page')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Something went wrong' })).not.toBeInTheDocument();
  });
});
