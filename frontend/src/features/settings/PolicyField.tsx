import { Group, Radio, Stack, Text } from '@mantine/core';

import type { NewCardPolicyName } from '../../api/endpoints';
import { POLICIES } from './settingsForm';

interface PolicyFieldProps {
  value: NewCardPolicyName;
  onChange: (value: NewCardPolicyName) => void;
  error?: string | undefined;
}

function isPolicy(value: string): value is NewCardPolicyName {
  return POLICIES.some((policy) => policy.value === value);
}

/** The three ways of choosing new cards, as radio cards with a one-line explanation each. */
export function PolicyField({ value, onChange, error }: PolicyFieldProps) {
  return (
    <Radio.Group
      value={value}
      onChange={(next) => {
        if (isPolicy(next)) onChange(next);
      }}
      label="How new cards are chosen"
      error={error}
    >
      <Stack gap="xs" mt="xs">
        {POLICIES.map((policy) => (
          <Radio.Card key={policy.value} value={policy.value} p="md" withBorder>
            <Group wrap="nowrap" align="flex-start">
              <Radio.Indicator />
              <div>
                <Text fw={500}>{policy.label}</Text>
                <Text size="sm" c="dimmed">
                  {policy.description}
                </Text>
              </div>
            </Group>
          </Radio.Card>
        ))}
      </Stack>
    </Radio.Group>
  );
}
