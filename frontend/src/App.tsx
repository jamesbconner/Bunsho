import { Container, MantineProvider, Text, Title } from '@mantine/core';
import { Notifications } from '@mantine/notifications';

import { theme } from './theme';

import '@mantine/core/styles.css';
import '@mantine/notifications/styles.css';

export function App() {
  return (
    <MantineProvider theme={theme} defaultColorScheme="auto">
      <Notifications />
      <Container py="xl">
        <Title order={1}>
          Bunshō{' '}
          <span lang="ja" data-testid="wordmark-ja">
            文章
          </span>
        </Title>
        <Text c="dimmed">Hello from the frontend skeleton.</Text>
      </Container>
    </MantineProvider>
  );
}
