import type {
  NewCardPolicyName,
  ReviewModeName,
  ReviewSettings,
  ReviewSettingsInput,
} from '../../api/endpoints';
import { ApiError } from '../../api/errors';

export const LEVELS = ['N5', 'N4', 'N3', 'N2', 'N1'] as const;
export type Level = (typeof LEVELS)[number];

/**
 * What the form edits. Retention and the mastery threshold are whole percentages here (the API
 * stores fractions); the limits and the threshold are `number | string` because a number input
 * holds an empty string while it is cleared.
 */
export interface SettingsFormValues {
  new_card_policy: NewCardPolicyName;
  new_limits: { kana: number | string; kanji: number | string; vocab: number | string };
  target_retention_percent: number;
  rollover_hour: number;
  active_levels: Level[];
  mastery_threshold_percent: number | string;
  kana_mode: ReviewModeName;
  kanji_mode: ReviewModeName;
  vocab_mode: ReviewModeName;
}

/**
 * The values a fresh install starts with. The API does not expose its defaults, so they are
 * repeated here; a test compares them with the defaults declared in the OpenAPI snapshot.
 */
export const RECOMMENDED_SETTINGS: ReviewSettings = {
  new_card_policy: 'strict_order',
  new_limits: { kana: 20, kanji: 15, vocab: 20 },
  target_retention: 0.9,
  rollover_hour: 4,
  active_levels: ['N5'],
  mastery_threshold: 0.8,
  kana_mode: 'flip',
  kanji_mode: 'flip',
  vocab_mode: 'flip',
};

export const POLICIES: readonly { value: NewCardPolicyName; label: string; description: string }[] =
  [
    {
      value: 'strict_order',
      label: 'Strict order',
      description: 'Finish every card of a level before the next level starts.',
    },
    {
      value: 'mastery_unlock',
      label: 'Mastery unlock',
      description:
        'The next level also waits until enough of the current level is well known (in Review).',
    },
    {
      value: 'pinned_levels',
      label: 'Pinned levels',
      description: 'Only take new cards from the levels you pick below.',
    },
  ];

export const LIMIT_MAX = 10_000;
export const RETENTION_MIN_PERCENT = 70;
export const RETENTION_MAX_PERCENT = 99;

/** 0.905 becomes 90.5: a percentage without floating-point noise. */
function toPercent(fraction: number): number {
  return Number((fraction * 100).toFixed(2));
}

/** 90.5 becomes 0.905. */
function toFraction(percent: number): number {
  return Number((percent / 100).toFixed(4));
}

export function toFormValues(settings: ReviewSettings): SettingsFormValues {
  return {
    new_card_policy: settings.new_card_policy,
    new_limits: { ...settings.new_limits },
    target_retention_percent: toPercent(settings.target_retention),
    rollover_hour: settings.rollover_hour,
    active_levels: LEVELS.filter((level) => settings.active_levels.includes(level)),
    mastery_threshold_percent: toPercent(settings.mastery_threshold),
    kana_mode: settings.kana_mode,
    kanji_mode: settings.kanji_mode,
    vocab_mode: settings.vocab_mode,
  };
}

/** The document to send: numbers as numbers, levels in study order, percentages as fractions. */
export function toRequest(values: SettingsFormValues): ReviewSettingsInput {
  return {
    new_card_policy: values.new_card_policy,
    new_limits: {
      kana: Number(values.new_limits.kana),
      kanji: Number(values.new_limits.kanji),
      vocab: Number(values.new_limits.vocab),
    },
    target_retention: toFraction(values.target_retention_percent),
    rollover_hour: values.rollover_hour,
    active_levels: LEVELS.filter((level) => values.active_levels.includes(level)),
    mastery_threshold: toFraction(Number(values.mastery_threshold_percent)),
    kana_mode: values.kana_mode,
    kanji_mode: values.kanji_mode,
    vocab_mode: values.vocab_mode,
  };
}

/** The form values in a shape that compares equal exactly when the documents they describe match. */
function canonical(values: SettingsFormValues): string {
  return JSON.stringify([
    values.new_card_policy,
    String(values.new_limits.kana),
    String(values.new_limits.kanji),
    String(values.new_limits.vocab),
    values.target_retention_percent,
    values.rollover_hour,
    LEVELS.filter((level) => values.active_levels.includes(level)),
    String(values.mastery_threshold_percent),
  ]);
}

/**
 * Whether `values` differ from `initial`. Mantine's own dirty map goes stale after a reset and
 * remembers the order chips were ticked in, so the comparison is done on canonical forms: an
 * empty field differs from 0, and the order of the levels does not matter.
 */
export function isSettingsDirty(values: SettingsFormValues, initial: SettingsFormValues): boolean {
  return canonical(values) !== canonical(initial);
}

function isWholeNumber(value: number | string, min: number, max: number): boolean {
  if (typeof value === 'string' && value.trim() === '') return false;
  const number = Number(value);
  return Number.isInteger(number) && number >= min && number <= max;
}

const LIMIT_MESSAGE = `Enter a whole number from 0 to ${LIMIT_MAX.toLocaleString('en-US')}.`;

/** The API's rules, checked before anything is sent. Keys are form field paths. */
export function validateSettings(values: SettingsFormValues): Record<string, string> {
  const errors: Record<string, string> = {};
  for (const type of ['kana', 'kanji', 'vocab'] as const) {
    if (!isWholeNumber(values.new_limits[type], 0, LIMIT_MAX)) {
      errors[`new_limits.${type}`] = LIMIT_MESSAGE;
    }
  }
  const retention = values.target_retention_percent;
  if (retention < RETENTION_MIN_PERCENT || retention > RETENTION_MAX_PERCENT) {
    errors.target_retention_percent = `Choose between ${RETENTION_MIN_PERCENT}% and ${RETENTION_MAX_PERCENT}%.`;
  }
  if (
    !Number.isInteger(values.rollover_hour) ||
    values.rollover_hour < 0 ||
    values.rollover_hour > 23
  ) {
    errors.rollover_hour = 'Choose an hour from 0 to 23.';
  }
  if (values.active_levels.length === 0) {
    errors.active_levels = 'Pick at least one level.';
  }
  const threshold = values.mastery_threshold_percent;
  const thresholdNumber = Number(threshold);
  if (
    (typeof threshold === 'string' && threshold.trim() === '') ||
    Number.isNaN(thresholdNumber) ||
    thresholdNumber < 0 ||
    thresholdNumber > 100
  ) {
    errors.mastery_threshold_percent = 'Enter a percentage from 0 to 100.';
  }
  return errors;
}

/** Where the server's field names live in the form. */
const SERVER_FIELDS: Readonly<Record<string, string>> = {
  new_card_policy: 'new_card_policy',
  kana: 'new_limits.kana',
  kanji: 'new_limits.kanji',
  vocab: 'new_limits.vocab',
  target_retention: 'target_retention_percent',
  rollover_hour: 'rollover_hour',
  active_levels: 'active_levels',
  mastery_threshold: 'mastery_threshold_percent',
};

export interface ServerErrors {
  /** Messages for fields the form has, keyed by form field path. */
  fields: Record<string, string>;
  /** Messages for anything the form cannot place, joined for one alert; null when none. */
  general: string | null;
}

/** Spread a 422's per-field messages over the form; whatever does not fit goes to `general`. */
export function placeServerErrors(error: ApiError): ServerErrors {
  const fields: Record<string, string> = {};
  const leftovers: string[] = [];
  for (const [name, message] of Object.entries(error.fieldErrors)) {
    const path = SERVER_FIELDS[name];
    if (path === undefined) leftovers.push(`${name}: ${message}`);
    else fields[path] = message;
  }
  if (Object.keys(fields).length === 0 && leftovers.length === 0) {
    leftovers.push('The server did not accept these settings.');
  }
  return { fields, general: leftovers.length === 0 ? null : leftovers.join(' ') };
}
