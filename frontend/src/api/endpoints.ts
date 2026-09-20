import { request } from './client';
import { ApiError } from './errors';
import type { components } from './schema';

type Schemas = components['schemas'];

export type ContentSummary = Schemas['ContentSummaryResponse'];
export type ConfigCheck = Schemas['ConfigCheckResponse'];
export type BuildStatus = Schemas['BuildStatusResponse'];

/** Every authenticated API call the screens make, typed from the generated schema. */
export const endpoints = {
  contentSummary: () => request<ContentSummary>('/content/summary'),

  configCheck: () => request<ConfigCheck>('/admin/config-check'),

  startBuild: (dryRun: boolean) =>
    request<BuildStatus>('/admin/content/build', { method: 'POST', body: { dry_run: dryRun } }),

  /** The most recent build, or null when none has run yet (the server answers 404). */
  latestBuild: async (): Promise<BuildStatus | null> => {
    try {
      return await request<BuildStatus>('/admin/content/build');
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null;
      throw error;
    }
  },

  getBuild: (taskId: string) =>
    request<BuildStatus>(`/admin/content/build/${encodeURIComponent(taskId)}`),
};
