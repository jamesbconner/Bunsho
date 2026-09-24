import { Chip, Group, Input, NumberInput, Stack, Switch, Text, Title } from '@mantine/core';
import { useId } from 'react';

import { groupAria } from './fieldAria';
import { PolicyField } from './PolicyField';
import { LEVELS, type Level, type SettingsFormApi } from './settingsForm';

type SwitchPath =
  | 'type_enabled.kana'
  | 'type_enabled.kanji'
  | 'type_enabled.vocab'
  | 'kana_gate.kanji'
  | 'kana_gate.vocab';

function isLevel(value: string): value is Level {
  return LEVELS.some((level) => level === value);
}

/** What to learn, and in what order: the policy, the type switches, the Kana first gate, levels. */
export function LearningPathTab({ form }: { form: SettingsFormApi }) {
  const levelsId = useId();
  const gateId = useId();
  const values = form.getValues();

  /** Set a switch and drop the kana-gate message, so a fixed problem stops being shown. */
  const setSwitch = (path: SwitchPath, checked: boolean) => {
    form.setFieldValue(path, checked);
    form.clearFieldError('kana_gate');
  };

  const pinned = values.new_card_policy === 'pinned_levels';
  const mastery = values.new_card_policy === 'mastery_unlock';
  const levelsError =
    typeof form.errors.active_levels === 'string' ? form.errors.active_levels : undefined;
  const gate = values.kana_gate;
  const gateError = typeof form.errors.kana_gate === 'string' ? form.errors.kana_gate : undefined;
  const thresholdError =
    typeof form.errors['kana_gate.threshold_percent'] === 'string'
      ? form.errors['kana_gate.threshold_percent']
      : undefined;
  // A hidden threshold that is invalid must still be shown, or Save would fail with no clue why.
  const showThreshold = gate.kanji || gate.vocab || thresholdError !== undefined;
  const kanaOff = !values.type_enabled.kana;

  return (
    <Stack gap="xl">
      <Stack gap="md">
        <Title order={3}>New cards</Title>
        <PolicyField
          value={values.new_card_policy}
          onChange={(policy) => {
            form.setFieldValue('new_card_policy', policy);
          }}
          error={
            typeof form.errors.new_card_policy === 'string'
              ? form.errors.new_card_policy
              : undefined
          }
        />
        <Stack gap="xs">
          <Switch
            label="Introduce new kana"
            checked={values.type_enabled.kana}
            onChange={(event) => {
              setSwitch('type_enabled.kana', event.currentTarget.checked);
            }}
          />
          <Switch
            label="Introduce new kanji"
            checked={values.type_enabled.kanji}
            onChange={(event) => {
              setSwitch('type_enabled.kanji', event.currentTarget.checked);
            }}
          />
          <Switch
            label="Introduce new vocabulary"
            checked={values.type_enabled.vocab}
            onChange={(event) => {
              setSwitch('type_enabled.vocab', event.currentTarget.checked);
            }}
          />
          <Text size="sm" c="dimmed">
            A type that is switched off introduces no new cards. Cards you already started stay due,
            so no progress is lost.
          </Text>
        </Stack>
      </Stack>

      <Stack gap="md">
        <Title order={3}>Kana first</Title>
        <Input.Wrapper
          id={gateId}
          label="Start kanji and vocabulary after kana"
          description="Hold them back until enough kana is learned. Your scheduled reviews are never held back."
          error={gateError}
          {...groupAria(gateId, gateError !== undefined)}
        >
          <Stack gap="xs" mt="xs">
            <Switch
              label="Wait for kana before starting kanji"
              checked={gate.kanji}
              disabled={kanaOff && !gate.kanji}
              onChange={(event) => {
                setSwitch('kana_gate.kanji', event.currentTarget.checked);
              }}
            />
            <Switch
              label="Wait for kana before starting vocabulary"
              checked={gate.vocab}
              disabled={kanaOff && !gate.vocab}
              onChange={(event) => {
                setSwitch('kana_gate.vocab', event.currentTarget.checked);
              }}
            />
            {kanaOff && (
              <Text size="sm" c="dimmed">
                Turn on new kana above to use this.
              </Text>
            )}
          </Stack>
        </Input.Wrapper>
        {showThreshold && (
          <NumberInput
            label="Kana needed before they start"
            description="Share of all kana cards (both directions, hiragana and katakana) that must be well known (in Review). If it drops below this later, new kanji and vocabulary pause until it recovers."
            min={0}
            max={100}
            allowDecimal={false}
            suffix="%"
            {...form.getInputProps('kana_gate.threshold_percent')}
          />
        )}
      </Stack>

      <Stack gap="md">
        <Title order={3}>Levels</Title>
        <Input.Wrapper
          id={levelsId}
          label="Levels to study"
          description={
            pinned ? 'New cards come only from these levels.' : 'Only used by "Pinned levels".'
          }
          error={levelsError}
          {...groupAria(levelsId, levelsError !== undefined)}
        >
          <Chip.Group
            multiple
            value={values.active_levels}
            onChange={(next) => {
              form.setFieldValue('active_levels', next.filter(isLevel));
            }}
          >
            <Group gap="xs" mt="xs">
              {LEVELS.map((level) => (
                <Chip key={level} value={level} disabled={!pinned}>
                  {level}
                </Chip>
              ))}
            </Group>
          </Chip.Group>
        </Input.Wrapper>
        <NumberInput
          label="Mastery needed to unlock the next level"
          description={
            mastery
              ? 'Share of the current level that must be well known (in Review).'
              : 'Only used by "Mastery unlock".'
          }
          min={0}
          max={100}
          allowDecimal={false}
          suffix="%"
          disabled={!mastery}
          {...form.getInputProps('mastery_threshold_percent')}
        />
      </Stack>
    </Stack>
  );
}
