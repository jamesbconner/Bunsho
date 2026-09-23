import { request } from './client';
import { ApiError } from './errors';
import type { components } from './schema';

type Schemas = components['schemas'];

export type ContentSummary = Schemas['ContentSummaryResponse'];
export type ConfigCheck = Schemas['ConfigCheckResponse'];
export type BuildStatus = Schemas['BuildStatusResponse'];
export type NextCard = Schemas['NextCard'];
export type CardView = Schemas['CardView'];
export type ReviewCounts = Schemas['ReviewCounts'];
export type AnswerRequest = Schemas['AnswerRequest'];
export type Grade = Schemas['Grade'];
export type ReviewModeName = Schemas['ReviewModeName'];
export type GradeIntervals = Schemas['GradeIntervals'];
export type RubySegment = Schemas['RubySegment'];
export type StatsSummary = Schemas['StatsSummary'];
export type LevelProgress = Schemas['LevelProgress'];
export type ReviewSettings = Schemas['ReviewSettings-Output'];
export type ReviewSettingsInput = Schemas['ReviewSettings-Input'];
export type NewCardPolicyName = Schemas['NewCardPolicyName'];

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

  /** The next card to study (or none), with the counts and the next time something is due. */
  nextReview: () => request<NextCard>('/reviews/next'),

  /** Study statistics: today's counts, the last 30 days, retention, cards by state and level. */
  statsSummary: () => request<StatsSummary>('/stats/summary'),

  getSettings: () => request<ReviewSettings>('/settings'),

  /** Replace the whole settings document (all or nothing: a 422 changes nothing). */
  updateSettings: (settings: ReviewSettingsInput) =>
    request<ReviewSettings>('/settings', { method: 'PUT', body: settings }),

  /** Grade a card; the server answers with the fresh counts. */
  answerReview: (answer: AnswerRequest) =>
    request<ReviewCounts>('/reviews/answer', { method: 'POST', body: answer }),
};
