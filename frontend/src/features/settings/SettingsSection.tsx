import { Paper, Stack, Text, Title } from '@mantine/core';
import type { ReactNode } from 'react';

interface SettingsSectionProps {
  title: string;
  /** One dimmed line under the title. */
  hint?: string;
  children: ReactNode;
}

/** A titled, bordered group of related settings; the same card the System tab uses. */
export function SettingsSection({ title, hint, children }: SettingsSectionProps) {
  return (
    <Paper component="section" aria-label={title} withBorder p="md" radius="md">
      <Stack gap="md">
        <div>
          <Title order={3}>{title}</Title>
          {hint !== undefined && (
            <Text size="sm" c="dimmed">
              {hint}
            </Text>
          )}
        </div>
        {children}
      </Stack>
    </Paper>
  );
}
