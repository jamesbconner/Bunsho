import { Box, Skeleton, Tabs, VisuallyHidden } from '@mantine/core';
import { useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import { lazy, Suspense, useEffect, useRef, useState } from 'react';

import type { ReviewSettings, ReviewSettingsInput } from '../../api/endpoints';
import { ApiError, messageFor } from '../../api/errors';
import { useUpdateSettings } from '../../api/queries';
import { ErrorBoundary } from '../../components/ErrorBoundary';
import { LearningPathTab } from './LearningPathTab';
import { PaceTab } from './PaceTab';
import { ReviewingTab } from './ReviewingTab';
import { SaveBar } from './SaveBar';
import {
  RECOMMENDED_SETTINGS,
  SETTINGS_TABS,
  errorPathsIn,
  firstTabWithErrors,
  isSettingsDirty,
  placeServerErrors,
  tabsWithErrors,
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

  // The errored fields to try, in order, once their tab is the one shown. It is state, and each
  // request a fresh object, so the effect runs again even when the target tab is already the current
  // one; `focused` remembers which request was served, so a later visit to that tab does not steal
  // focus again.
  const [focusRequest, setFocusRequest] = useState<{ tab: string; paths: string[] } | null>(null);
  const focused = useRef<object | null>(null);
  const { getInputNode } = form;

  useEffect(() => {
    if (focusRequest === null || focusRequest.tab !== tab || focused.current === focusRequest)
      return;
    focused.current = focusRequest;
    // Not every control has a node the form can find, or can take focus (a disabled switch, chips, the
    // slider). Focus the first errored field that can; otherwise the selected tab, whose name says
    // "(has errors)", so a keyboard or screen-reader user is told where they are and why.
    for (const path of focusRequest.paths) {
      const node = getInputNode(path);
      node?.focus();
      if (node !== null && node !== undefined && document.activeElement === node) return;
    }
    document.querySelector<HTMLElement>('[role="tab"][aria-selected="true"]')?.focus();
  }, [tab, focusRequest, getInputNode]);

  /** After a failed Save or a placed 422: show the first tab with an error, and focus its field. */
  const showFirstError = (errors: Readonly<Record<string, unknown>>) => {
    const target = firstTabWithErrors(errors);
    if (target === null) return;
    setTab(target);
    setFocusRequest({ tab: target, paths: errorPathsIn(errors, target) });
  };

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
          showFirstError(placed.fields);
          if (placed.general !== null) setGeneral({ message: placed.general, retryable: false });
          return;
        }
        setGeneral({ message: messageFor(error), retryable: true });
      },
    });
  };

  const dirty = isSettingsDirty(form.getValues(), form.getInitialValues());
  const errorTabs = tabsWithErrors(form.errors);

  return (
    <Tabs value={tab} onChange={setTab} keepMounted={false}>
      <Tabs.List aria-label="Settings sections">
        {SETTINGS_TABS.map(({ value, label }) => {
          const failing = value !== 'system' && errorTabs.has(value);
          return (
            <Tabs.Tab
              key={value}
              value={value}
              color={failing ? 'red' : undefined}
              rightSection={
                failing ? (
                  <Box
                    component="span"
                    w={8}
                    h={8}
                    bg="red"
                    style={{ borderRadius: '50%' }}
                    aria-hidden
                  />
                ) : null
              }
            >
              {label}
              {failing && ' '}
              {failing && <VisuallyHidden>(has errors)</VisuallyHidden>}
            </Tabs.Tab>
          );
        })}
      </Tabs.List>

      <form
        onSubmit={form.onSubmit(
          (submitted) => {
            submit(toRequest(submitted));
          },
          (errors) => {
            showFirstError(errors);
          },
        )}
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
        {/* A chunk that fails to load stays in this panel; the form and the other tabs keep working. */}
        <ErrorBoundary>
          <Suspense fallback={<Skeleton height={240} />}>
            <SystemTab />
          </Suspense>
        </ErrorBoundary>
      </Tabs.Panel>
    </Tabs>
  );
}
