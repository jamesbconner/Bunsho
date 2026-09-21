import {
  Alert,
  Button,
  Chip,
  Group,
  Input,
  NativeSelect,
  NumberInput,
  Skeleton,
  Slider,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import { useId, useState } from 'react';

import type { ReviewSettings, ReviewSettingsInput } from '../../api/endpoints';
import { ApiError, messageFor } from '../../api/errors';
import { useSettings, useUpdateSettings } from '../../api/queries';
import { PolicyField } from './PolicyField';
import {
  LEVELS,
  LIMIT_MAX,
  RECOMMENDED_SETTINGS,
  isSettingsDirty,
  RETENTION_MAX_PERCENT,
  RETENTION_MIN_PERCENT,
  placeServerErrors,
  toFormValues,
  toRequest,
  validateSettings,
  type Level,
  type SettingsFormValues,
} from './settingsForm';

const HOURS = Array.from({ length: 24 }, (_, hour) => ({
  value: String(hour),
  label: `${hour}:00`,
}));

/** The ids of a `Input.Wrapper`'s label, description and (when shown) error, for a group's aria. */
function groupAria(id: string, hasError: boolean) {
  return {
    role: 'group',
    'aria-labelledby': `${id}-label`,
    'aria-describedby': hasError ? `${id}-error ${id}-description` : `${id}-description`,
  };
}

function isLevel(value: string): value is Level {
  return LEVELS.some((level) => level === value);
}

/** The form, seeded once from `initial`: a background refetch must never replace what is typed. */
function SettingsForm({ initial }: { initial: ReviewSettings }) {
  const save = useUpdateSettings();
  const levelsId = useId();
  const retentionId = useId();
  const [general, setGeneral] = useState<{ message: string; retryable: boolean } | null>(null);
  const form = useForm<SettingsFormValues>({
    mode: 'controlled',
    initialValues: toFormValues(initial),
    validate: validateSettings,
  });
  const { mutate: sendSettings } = save;

  const submit = (request: ReviewSettingsInput) => {
    setGeneral(null);
    sendSettings(request, {
      onSuccess: (saved) => {
        const values = toFormValues(saved);
        form.setValues(values);
        form.setInitialValues(values);
        notifications.show({ message: 'Settings saved' });
      },
      onError: (error) => {
        if (error instanceof ApiError && error.status === 422) {
          const placed = placeServerErrors(error);
          form.setErrors(placed.fields);
          if (placed.general !== null) setGeneral({ message: placed.general, retryable: false });
          return;
        }
        setGeneral({ message: messageFor(error), retryable: true });
      },
    });
  };

  const values = form.getValues();
  const dirty = isSettingsDirty(values, form.getInitialValues());
  const pinned = values.new_card_policy === 'pinned_levels';
  const mastery = values.new_card_policy === 'mastery_unlock';
  const levelsError =
    typeof form.errors.active_levels === 'string' ? form.errors.active_levels : undefined;
  const retentionError =
    typeof form.errors.target_retention_percent === 'string'
      ? form.errors.target_retention_percent
      : undefined;

  return (
    <form
      onSubmit={form.onSubmit((submitted) => {
        submit(toRequest(submitted));
      })}
      noValidate
    >
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
          <Group grow align="flex-start">
            <NumberInput
              label="Kana per day"
              min={0}
              max={LIMIT_MAX}
              allowDecimal={false}
              {...form.getInputProps('new_limits.kana')}
            />
            <NumberInput
              label="Kanji per day"
              min={0}
              max={LIMIT_MAX}
              allowDecimal={false}
              {...form.getInputProps('new_limits.kanji')}
            />
            <NumberInput
              label="Vocabulary per day"
              min={0}
              max={LIMIT_MAX}
              allowDecimal={false}
              {...form.getInputProps('new_limits.vocab')}
            />
          </Group>
          <Text size="sm" c="dimmed">
            The most new cards of each type per day. 0 means no limit.
          </Text>
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

        <Stack gap="md">
          <Title order={3}>Scheduling</Title>
          <Input.Wrapper
            id={retentionId}
            label={`Target retention: ${String(values.target_retention_percent)}%`}
            description="How often you want to remember a card when it comes back. Higher means more reviews."
            error={retentionError}
            {...groupAria(retentionId, retentionError !== undefined)}
          >
            <Slider
              mt="sm"
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
        </Stack>

        <Stack gap="md">
          <Title order={3}>Study day</Title>
          <NativeSelect
            label="A new study day starts at"
            description="In the server's timezone (the TZ setting). Daily limits reset then."
            data={HOURS}
            value={String(values.rollover_hour)}
            onChange={(event) => {
              form.setFieldValue('rollover_hour', Number(event.currentTarget.value));
            }}
            error={
              typeof form.errors.rollover_hour === 'string' ? form.errors.rollover_hour : undefined
            }
          />
        </Stack>

        {general !== null && (
          <Alert color="red" title="Couldn't save your settings">
            <Text size="sm">{general.message}</Text>
            {general.retryable && save.variables !== undefined && (
              <Button
                mt="sm"
                size="xs"
                disabled={save.isPending}
                onClick={() => {
                  if (save.variables !== undefined) submit(save.variables);
                }}
              >
                Try again
              </Button>
            )}
          </Alert>
        )}

        <Group>
          <Button type="submit" disabled={!dirty} loading={save.isPending}>
            Save
          </Button>
          <Button
            variant="subtle"
            onClick={() => {
              form.setValues(toFormValues(RECOMMENDED_SETTINGS));
            }}
          >
            Reset to recommended values
          </Button>
          {dirty && (
            <Text size="sm" c="dimmed">
              Unsaved changes
            </Text>
          )}
        </Group>
      </Stack>
    </form>
  );
}

/** How new cards are chosen, how many, and how sharp your memory should stay. */
export function SettingsPage() {
  const settings = useSettings();

  return (
    <Stack gap="lg" maw={720}>
      <Title order={2}>Settings</Title>
      {settings.isPending && <Skeleton height={320} />}
      {settings.isError && settings.data === undefined && (
        <Alert color="red" title="Couldn't load your settings">
          <Text size="sm">{messageFor(settings.error)}</Text>
          <Button
            mt="sm"
            size="xs"
            onClick={() => {
              void settings.refetch();
            }}
          >
            Try again
          </Button>
        </Alert>
      )}
      {settings.data !== undefined && <SettingsForm initial={settings.data} />}
    </Stack>
  );
}
