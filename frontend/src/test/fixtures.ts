import type { BuildStatus } from '../api/endpoints';

export type BuildReport = NonNullable<BuildStatus['report']>;

export function makeBuildStatus(overrides: Partial<BuildStatus> = {}): BuildStatus {
  return {
    task_id: 'task-1',
    state: 'running',
    dry_run: false,
    started_at: '2026-09-20T12:00:00Z',
    finished_at: null,
    progress: { stage: 'import_deck', current: 0, total: 1 },
    report: null,
    error: null,
    ...overrides,
  };
}

export function makeReport(overrides: Partial<BuildReport> = {}): BuildReport {
  return {
    dry_run: false,
    target: '/data/content.db',
    deck_sha256: 'a'.repeat(64),
    kana_count: 208,
    kanji_count: 3088,
    unleveled_kanji_count: 979,
    vocab_count: 7734,
    sentence_count: 6775,
    vocab_by_level: { N5: 667, N4: 630, N3: 1647, N2: 1737, N1: 3053 },
    kanji_by_level: { N5: 480, N4: 352, N3: 544, N2: 357, N1: 376 },
    kanji_without_details: 12,
    duration_seconds: 31.4,
    ...overrides,
  };
}
