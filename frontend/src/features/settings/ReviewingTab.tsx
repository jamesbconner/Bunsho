import { NativeSelect, Stack, Title } from '@mantine/core';

import { REVIEW_MODES, type SettingsFormApi, type SettingsFormValues } from './settingsForm';

const REVIEW_MODE_OPTIONS = REVIEW_MODES.map((mode) => ({ value: mode.value, label: mode.label }));

/** How you answer: the review mode of each card type. */
export function ReviewingTab({ form }: { form: SettingsFormApi }) {
  const values = form.getValues();
  const select = (field: 'kana_mode' | 'kanji_mode' | 'vocab_mode', label: string) => (
    <NativeSelect
      label={label}
      data-path={field}
      data={REVIEW_MODE_OPTIONS}
      value={values[field]}
      error={typeof form.errors[field] === 'string' ? form.errors[field] : undefined}
      onChange={(event) => {
        form.setFieldValue(field, event.currentTarget.value as SettingsFormValues[typeof field]);
      }}
    />
  );

  return (
    <Stack gap="md">
      <Title order={3}>How you answer</Title>
      {select('kana_mode', 'Kana review mode')}
      {select('kanji_mode', 'Kanji review mode')}
      {select('vocab_mode', 'Vocabulary review mode')}
    </Stack>
  );
}
