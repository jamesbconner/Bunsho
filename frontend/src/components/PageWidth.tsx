import { Container } from '@mantine/core';
import { Suspense } from 'react';
import { Outlet, useLocation } from 'react-router';

import { ErrorBoundary } from './ErrorBoundary';
import { PageLoader } from './PageLoader';
import { PAGE_WIDTHS, type PageWidthName } from './pageWidths';

/**
 * A layout route: centers the routed page in a column of one of the two widths. The loading
 * indicator and the error page render inside the column too, so a page does not change width
 * when its code arrives. `AppShell.Main` already provides the side gutters, hence `px={0}`.
 */
export function PageWidth({ size }: { size: PageWidthName }) {
  const { pathname } = useLocation();
  return (
    <Container size={PAGE_WIDTHS[size]} px={0} data-width={size}>
      <ErrorBoundary key={pathname}>
        <Suspense fallback={<PageLoader />}>
          <Outlet />
        </Suspense>
      </ErrorBoundary>
    </Container>
  );
}
