import { Skeleton, Tabs } from '@mantine/core';
import { useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import { lazy, Suspense, useState } from 'react';

import type { ReviewSettings, ReviewSettingsInput } from '../../api/endpoints';
import { ApiError, messageFor } from '../../api/errors';
import { useUpdateSettings } from '../../api/queries';
import { LearningPathTab } from './LearningPathTab';
import { PaceTab } from './PaceTab';
import { ReviewingTab } from './ReviewingTab';
import { SaveBar } from './SaveBar';
import {
  RECOMMENDED_SETTINGS,
  SETTINGS_TABS,
  isSettingsDirty,
  placeServerErrors,
  toFormValues,
  toRequest,
  validateSettings,
  type SettingsFormValues,
} from './settingsForm';
import { useSettingsTab } from './useSettingsTab';

// The System tab carries the build UI; load it only when somebody opens it.
const SystemTab = lazy(() =>
  import('./SystemTab').then((module) => ({ default: module.SystemTab })),
);

/** The tabs and the one settings form, seeded once from `initial`: a refetch never replaces edits. */
export function SettingsTabs({ initial }: { initial: ReviewSettings }) {
  const save = useUpdateSettings();
  const [tab, setTab] = useSettingsTab();
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

  const dirty = isSettingsDirty(form.getValues(), form.getInitialValues());

  return (
    <Tabs value={tab} onChange={setTab} keepMounted={false}>
      <Tabs.List aria-label="Settings sections">
        {SETTINGS_TABS.map(({ value, label }) => (
          <Tabs.Tab key={value} value={value}>
            {label}
          </Tabs.Tab>
        ))}
      </Tabs.List>

      <form
        onSubmit={form.onSubmit((submitted) => {
          submit(toRequest(submitted));
        })}
        noValidate
      >
        <Tabs.Panel value="learning" pt="md" keepMounted>
          <LearningPathTab form={form} />
        </Tabs.Panel>
        <Tabs.Panel value="pace" pt="md" keepMounted>
          <PaceTab form={form} />
        </Tabs.Panel>
        <Tabs.Panel value="reviewing" pt="md" keepMounted>
          <ReviewingTab form={form} />
        </Tabs.Panel>
        {tab !== 'system' && (
          <SaveBar
            dirty={dirty}
            saving={save.isPending}
            general={general}
            onRetry={() => {
              if (save.variables !== undefined) submit(save.variables);
            }}
            onReset={() => {
              form.setValues(toFormValues(RECOMMENDED_SETTINGS));
            }}
          />
        )}
      </form>

      <Tabs.Panel value="system" pt="md">
        <Suspense fallback={<Skeleton height={240} />}>
          <SystemTab />
        </Suspense>
      </Tabs.Panel>
    </Tabs>
  );
}
