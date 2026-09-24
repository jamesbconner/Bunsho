import { Alert, Button, Group, Text } from '@mantine/core';

interface SaveBarProps {
  dirty: boolean;
  saving: boolean;
  /** A save problem that belongs to no field; `retryable` shows "Try again". */
  general: { message: string; retryable: boolean } | null;
  onRetry: () => void;
  onReset: () => void;
}

/** Save, Reset and the save problem; shown under the three settings tabs, not under System. */
export function SaveBar({ dirty, saving, general, onRetry, onReset }: SaveBarProps) {
  return (
    <>
      {general !== null && (
        <Alert color="red" title="Couldn't save your settings" mt="xl">
          <Text size="sm">{general.message}</Text>
          {general.retryable && (
            <Button mt="sm" size="xs" disabled={saving} onClick={onRetry}>
              Try again
            </Button>
          )}
        </Alert>
      )}
      <Group mt="xl">
        <Button type="submit" disabled={!dirty} loading={saving}>
          Save
        </Button>
        <Button variant="subtle" onClick={onReset}>
          Reset to recommended values
        </Button>
        {dirty && (
          <Text size="sm" c="dimmed">
            Unsaved changes
          </Text>
        )}
      </Group>
    </>
  );
}
