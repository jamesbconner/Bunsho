import { MantineProvider } from '@mantine/core';
import { Notifications } from '@mantine/notifications';
import { QueryClientProvider } from '@tanstack/react-query';
import { lazy, useState } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router';

import { AuthProvider } from './auth/AuthProvider';
import { RequireAuth } from './auth/RequireAuth';
import { AppLayout } from './components/AppLayout';
import { LoginPage } from './features/login/LoginPage';
import { NotFoundPage } from './features/NotFoundPage';
import { createQueryClient } from './queryClient';
import { RealtimeProvider } from './realtime/RealtimeProvider';
import { theme } from './theme';

import '@mantine/core/styles.css';
import '@mantine/notifications/styles.css';

// The pages load on demand, so the first screen (login) does not carry the study or build code.
const HomePage = lazy(() =>
  import('./features/home/HomePage').then((module) => ({ default: module.HomePage })),
);
const ReviewPage = lazy(() =>
  import('./features/review/ReviewPage').then((module) => ({ default: module.ReviewPage })),
);
const StatsPage = lazy(() =>
  import('./features/stats/StatsPage').then((module) => ({ default: module.StatsPage })),
);
const SettingsPage = lazy(() =>
  import('./features/settings/SettingsPage').then((module) => ({ default: module.SettingsPage })),
);

export function App() {
  const [queryClient] = useState(createQueryClient);

  return (
    <MantineProvider theme={theme} defaultColorScheme="auto">
      <Notifications position="top-right" />
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AuthProvider>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route element={<RequireAuth />}>
                <Route
                  element={
                    <RealtimeProvider>
                      <AppLayout />
                    </RealtimeProvider>
                  }
                >
                  <Route index element={<HomePage />} />
                  <Route path="review" element={<ReviewPage />} />
                  <Route path="stats" element={<StatsPage />} />
                  <Route path="settings" element={<SettingsPage />} />
                  <Route path="build" element={<Navigate to="/settings?tab=system" replace />} />
                  <Route path="*" element={<NotFoundPage />} />
                </Route>
              </Route>
            </Routes>
          </AuthProvider>
        </BrowserRouter>
      </QueryClientProvider>
    </MantineProvider>
  );
}
