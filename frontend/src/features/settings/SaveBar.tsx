import { Alert, Badge, Button, Group, Paper, Stack, Text } from '@mantine/core';

interface SaveBarProps {
  dirty: boolean;
  saving: boolean;
  /** A save problem that belongs to no field; `retryable` shows "Try again". */
  general: { message: string; retryable: boolean } | null;
  onRetry: () => void;
  /** Put every field back to what was last saved. */
  onDiscard: () => void;
  /** Refill the form with the recommended values (nothing is saved). */
  onReset: () => void;
}

/**
 * Save, Discard, Reset and the save problem; shown under the three settings tabs, not under
 * System. It sticks to the bottom of the window, so Save is in reach however long the tab is.
 */
export function SaveBar({ dirty, saving, general, onRetry, onDiscard, onReset }: SaveBarProps) {
  return (
    <Paper
      withBorder
      shadow="md"
      radius="md"
      p="sm"
      mt="xl"
      style={{ position: 'sticky', bottom: 12, zIndex: 10 }}
    >
      <Stack gap="sm">
        {general !== null && (
          <Alert color="red" title="Couldn't save your settings">
            <Text size="sm">{general.message}</Text>
            {general.retryable && (
              <Button mt="sm" size="xs" disabled={saving} onClick={onRetry}>
                Try again
              </Button>
            )}
          </Alert>
        )}
        <Group justify="space-between" gap="xs">
          {dirty ? (
            <Badge color="yellow" variant="light" size="lg">
              Unsaved changes
            </Badge>
          ) : (
            <Text size="sm" c="dimmed">
              All changes saved
            </Text>
          )}
          <Group gap="xs">
            <Button variant="subtle" color="gray" disabled={saving} onClick={onReset}>
              Reset all tabs to recommended values
            </Button>
            <Button variant="default" disabled={!dirty || saving} onClick={onDiscard}>
              Discard changes
            </Button>
            <Button type="submit" disabled={!dirty} loading={saving}>
              Save
            </Button>
          </Group>
        </Group>
      </Stack>
    </Paper>
  );
}
