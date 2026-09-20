import { MantineProvider } from '@mantine/core';
import { Notifications } from '@mantine/notifications';
import { QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router';

import { AuthProvider } from './auth/AuthProvider';
import { RequireAuth } from './auth/RequireAuth';
import { AppLayout } from './components/AppLayout';
import { BuildPage } from './features/build/BuildPage';
import { HomePage } from './features/home/HomePage';
import { LoginPage } from './features/login/LoginPage';
import { NotFoundPage } from './features/NotFoundPage';
import { createQueryClient } from './queryClient';
import { RealtimeProvider } from './realtime/RealtimeProvider';
import { theme } from './theme';

import '@mantine/core/styles.css';
import '@mantine/notifications/styles.css';

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
                  <Route path="build" element={<BuildPage />} />
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
