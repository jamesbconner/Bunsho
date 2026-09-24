import { Group, Input, NativeSelect, NumberInput, Slider, Stack } from '@mantine/core';
import { useId } from 'react';

import { groupAria } from './fieldAria';
import {
  LIMIT_MAX,
  RETENTION_MAX_PERCENT,
  RETENTION_MIN_PERCENT,
  type SettingsFormApi,
} from './settingsForm';
import { SettingsSection } from './SettingsSection';

const HOURS = Array.from({ length: 24 }, (_, hour) => ({
  value: String(hour),
  label: `${hour}:00`,
}));

const SWITCHED_OFF = 'Switched off in Learning path.';

/** How much and how often: daily new-card limits, when the study day starts, target retention. */
export function PaceTab({ form }: { form: SettingsFormApi }) {
  const retentionId = useId();
  const values = form.getValues();
  const retentionError =
    typeof form.errors.target_retention_percent === 'string'
      ? form.errors.target_retention_percent
      : undefined;

  return (
    <Stack gap="lg">
      <SettingsSection
        title="Daily limits"
        hint="The most new cards of each type per day. 0 means no limit."
      >
        <Group grow align="flex-start">
          <NumberInput
            label="Kana per day"
            min={0}
            max={LIMIT_MAX}
            allowDecimal={false}
            disabled={!values.type_enabled.kana}
            description={values.type_enabled.kana ? undefined : SWITCHED_OFF}
            {...form.getInputProps('new_limits.kana')}
          />
          <NumberInput
            label="Kanji per day"
            min={0}
            max={LIMIT_MAX}
            allowDecimal={false}
            disabled={!values.type_enabled.kanji}
            description={values.type_enabled.kanji ? undefined : SWITCHED_OFF}
            {...form.getInputProps('new_limits.kanji')}
          />
          <NumberInput
            label="Vocabulary per day"
            min={0}
            max={LIMIT_MAX}
            allowDecimal={false}
            disabled={!values.type_enabled.vocab}
            description={values.type_enabled.vocab ? undefined : SWITCHED_OFF}
            {...form.getInputProps('new_limits.vocab')}
          />
        </Group>
      </SettingsSection>

      <SettingsSection title="Study day">
        <NativeSelect
          label="A new study day starts at"
          description="In the server's timezone (the TZ setting). Daily limits reset then."
          data={HOURS}
          data-path="rollover_hour"
          value={String(values.rollover_hour)}
          onChange={(event) => {
            form.setFieldValue('rollover_hour', Number(event.currentTarget.value));
          }}
          error={
            typeof form.errors.rollover_hour === 'string' ? form.errors.rollover_hour : undefined
          }
        />
      </SettingsSection>

      <SettingsSection title="Scheduling">
        <Input.Wrapper
          id={retentionId}
          label={`Target retention: ${String(values.target_retention_percent)}%`}
          description="How often you want to remember a card when it comes back. Higher means more reviews."
          error={retentionError}
          {...groupAria(retentionId, retentionError !== undefined)}
        >
          <Slider
            mt="sm"
            mb="lg"
            min={RETENTION_MIN_PERCENT}
            max={RETENTION_MAX_PERCENT}
            step={1}
            value={values.target_retention_percent}
            onChange={(percent) => {
              form.setFieldValue('target_retention_percent', percent);
            }}
            label={(percent) => `${String(percent)}%`}
            thumbLabel="Target retention"
            thumbValueText={`${String(values.target_retention_percent)}%`}
            marks={[
              { value: 70, label: '70%' },
              { value: 80, label: '80%' },
              { value: 90, label: '90%' },
              { value: 99, label: '99%' },
            ]}
          />
        </Input.Wrapper>
      </SettingsSection>
    </Stack>
  );
}
