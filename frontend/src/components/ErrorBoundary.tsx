import { Button, Center, Stack, Text, Title } from '@mantine/core';
import { Component, type ErrorInfo, type ReactNode } from 'react';

interface ErrorBoundaryState {
  failed: boolean;
}

/**
 * Catches rendering errors below it and shows a friendly page instead of a blank screen. It never
 * shows the error itself (no stack traces); the details go to the browser console. Give it a
 * `key` that changes on navigation so leaving the broken page resets it.
 */
export class ErrorBoundary extends Component<{ children: ReactNode }, ErrorBoundaryState> {
  state: ErrorBoundaryState = { failed: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('Rendering failed', error, info.componentStack);
  }

  render(): ReactNode {
    if (!this.state.failed) return this.props.children;
    return (
      <Center mih={320}>
        <Stack align="center" gap="xs">
          <Title order={3}>Something went wrong</Title>
          <Text c="dimmed">This page could not be shown. Reloading usually fixes it.</Text>
          <Button
            onClick={() => {
              window.location.reload();
            }}
          >
            Reload the page
          </Button>
        </Stack>
      </Center>
    );
  }
}
