import type { BuildStatus } from '../../api/endpoints';

const STAGE_LABELS: Record<string, string> = {
  import_deck: 'Reading the vocabulary deck',
  enrich_kanji: 'Looking up kanji details',
  write: 'Writing the content database',
};

/** A friendly name for a build stage; an unknown stage keeps its own name. */
export function stageLabel(stage: string): string {
  return STAGE_LABELS[stage] ?? stage;
}

/**
 * The sentence a screen reader announces when the build state changes. It names the stage but not
 * the running counts, so progress does not chatter, and it carries the failure message so the
 * failure alert does not have to announce it a second time.
 */
export function announcementFor(task: BuildStatus | null | undefined): string {
  if (task == null) return '';
  const what = task.dry_run ? 'Dry run' : 'Build';
  switch (task.state) {
    case 'running':
      return `${what} running: ${task.progress === null ? 'starting' : stageLabel(task.progress.stage)}`;
    case 'succeeded':
      return `${what} finished`;
    case 'failed':
      return `${what} failed: ${task.error ?? 'no details were reported'}`;
  }
}
