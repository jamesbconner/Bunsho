import { Button, Center, Stack, Text, Title } from '@mantine/core';
import { Link } from 'react-router';

export function NotFoundPage() {
  return (
    <Center mih={320}>
      <Stack align="center" gap="xs">
        <Title order={2}>Page not found</Title>
        <Text c="dimmed">There is nothing at this address.</Text>
        <Button component={Link} to="/">
          Back to Home
        </Button>
      </Stack>
    </Center>
  );
}
