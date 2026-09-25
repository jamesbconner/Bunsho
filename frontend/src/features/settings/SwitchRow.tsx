import { Group, Switch, Text, type SwitchProps } from '@mantine/core';
import { useId } from 'react';

type SwitchRowProps = Pick<SwitchProps, 'checked' | 'disabled' | 'onChange'> & {
  label: string;
  description: string;
  'data-path'?: string;
};

/**
 * A settings row: the label and its explanation on the left, the toggle on the right.
 *
 * The description is tied to the switch with `aria-describedby` instead of Mantine's own
 * `description` prop, which sits inside the `<label>` and would become part of the switch's name.
 */
export function SwitchRow({ label, description, disabled, ...switchProps }: SwitchRowProps) {
  const id = useId();
  return (
    <Group justify="space-between" wrap="nowrap" gap="md">
      <div>
        <Text
          component="label"
          htmlFor={id}
          size="sm"
          c={disabled === true ? 'dimmed' : undefined}
          style={{ cursor: disabled === true ? 'not-allowed' : 'pointer' }}
        >
          {label}
        </Text>
        <Text id={`${id}-description`} size="xs" c="dimmed">
          {description}
        </Text>
      </div>
      <Switch id={id} aria-describedby={`${id}-description`} disabled={disabled} {...switchProps} />
    </Group>
  );
}
