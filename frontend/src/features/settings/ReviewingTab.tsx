import { Input, SegmentedControl, Stack, Text } from '@mantine/core';
import { useId } from 'react';

import { REVIEW_MODES, type SettingsFormApi, type SettingsFormValues } from './settingsForm';
import { SettingsSection } from './SettingsSection';

const REVIEW_MODE_OPTIONS = REVIEW_MODES.map((mode) => ({ value: mode.value, label: mode.label }));

type ModeField = 'kana_mode' | 'kanji_mode' | 'vocab_mode';

function isMode(value: string): value is SettingsFormValues[ModeField] {
  return REVIEW_MODES.some((mode) => mode.value === value);
}

/** How you answer: the review mode of each card type. */
export function ReviewingTab({ form }: { form: SettingsFormApi }) {
  const baseId = useId();
  const values = form.getValues();

  const picker = (field: ModeField, label: string) => {
    const id = `${baseId}-${field}`;
    const error = typeof form.errors[field] === 'string' ? form.errors[field] : undefined;
    const help = REVIEW_MODES.find((mode) => mode.value === values[field])?.description;
    return (
      <Input.Wrapper key={field} id={id} label={label} labelElement="div" error={error}>
        <SegmentedControl
          fullWidth
          mt={4}
          // A group cannot take focus by default; this lets a failed Save move focus to it.
          tabIndex={-1}
          data-path={field}
          aria-labelledby={`${id}-label`}
          aria-describedby={error === undefined ? `${id}-help` : `${id}-error ${id}-help`}
          data={REVIEW_MODE_OPTIONS}
          value={values[field]}
          onChange={(next) => {
            if (isMode(next)) form.setFieldValue(field, next);
          }}
        />
        <Text id={`${id}-help`} size="sm" c="dimmed" mt={6}>
          {help}
        </Text>
      </Input.Wrapper>
    );
  };

  return (
    <SettingsSection title="How you answer" hint="Choose how each type of card is answered.">
      <Stack gap="lg">
        {picker('kana_mode', 'Kana review mode')}
        {picker('kanji_mode', 'Kanji review mode')}
        {picker('vocab_mode', 'Vocabulary review mode')}
      </Stack>
    </SettingsSection>
  );
}
