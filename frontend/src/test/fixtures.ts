import type {
  BuildStatus,
  CardView,
  NextCard,
  ReviewSettings,
  RubySegment,
  StatsSummary,
} from '../api/endpoints';

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

/** A ruby segment: text with an optional reading, optionally highlighted. */
export function segment(
  base: string,
  reading: string | null = null,
  highlighted = false,
): RubySegment {
  return { base, reading, highlighted };
}

const INTERVALS = { again: 60, hard: 600, good: 86_400, easy: 345_600 };
const ZERO = { kana: 0, kanji: 0, vocab: 0 };

/** A new kana card (あ, glyph to sound). */
export function makeKanaCard(overrides: Partial<CardView> = {}): CardView {
  return {
    item_id: 'kana:あ',
    direction: 'glyph_to_sound',
    item_type: 'kana',
    is_new: true,
    state: 0,
    expected_last_review: null,
    intervals: INTERVALS,
    kana: { id: 'kana:あ', char: 'あ', romaji: 'a', script: 'hira', kind: 'basic', group: 'a' },
    kanji: null,
    vocab: null,
    ...overrides,
  };
}

/** A kanji card (日, kanji to meaning). */
export function makeKanjiCard(overrides: Partial<CardView> = {}): CardView {
  return {
    item_id: 'kanji:日',
    direction: 'kanji_to_meaning',
    item_type: 'kanji',
    is_new: false,
    state: 2,
    expected_last_review: '2026-09-19T08:00:00Z',
    intervals: INTERVALS,
    kana: null,
    kanji: {
      id: 'kanji:日',
      char: '日',
      level: 5,
      meanings: ['day', 'sun'],
      on_readings: ['ニチ', 'ジツ'],
      kun_readings: ['ひ', 'か'],
    },
    vocab: null,
    ...overrides,
  };
}

/** A vocabulary card (食べる, recognition) with an example sentence. */
export function makeVocabCard(overrides: Partial<CardView> = {}): CardView {
  return {
    item_id: 'vocab:食べる:たべる',
    direction: 'recognition',
    item_type: 'vocab',
    is_new: false,
    state: 2,
    expected_last_review: '2026-09-19T09:30:00Z',
    intervals: INTERVALS,
    kana: null,
    kanji: null,
    vocab: {
      id: 'vocab:食べる:たべる',
      expression: '食べる',
      reading: 'たべる',
      meaning: 'to eat',
      level: 5,
      part_of_speech: ['verb', 'ichidan'],
      additional_definitions: '',
      tags: [],
      reading_segments: [segment('食', 'た'), segment('べる')],
      sentence: {
        english: 'I eat breakfast every day.',
        segments: [
          segment('毎日', 'まいにち'),
          segment('朝ご飯', 'あさごはん'),
          segment('を'),
          segment('食べる', null, true),
          segment('。'),
        ],
      },
    },
    ...overrides,
  };
}

/** The `GET /reviews/next` payload around `card` (a card, or null for nothing to study). */
export function makeNextCard(card: CardView | null, overrides: Partial<NextCard> = {}): NextCard {
  return {
    card,
    counts: {
      due: card === null ? ZERO : { ...ZERO, [card.item_type]: 1 },
      new_remaining: ZERO,
    },
    next_due_at: null,
    ...overrides,
  };
}

/** The settings a fresh install starts with (the backend's defaults). */
export function makeSettings(overrides: Partial<ReviewSettings> = {}): ReviewSettings {
  return {
    new_card_policy: 'strict_order',
    new_limits: { kana: 20, kanji: 15, vocab: 20 },
    target_retention: 0.9,
    rollover_hour: 4,
    active_levels: ['N5'],
    mastery_threshold: 0.8,
    ...overrides,
  };
}

/** 30 study days ending on 2026-09-20, with reviews on some of them. */
export function makeDailyReviews(): StatsSummary['daily_reviews'] {
  return Array.from({ length: 30 }, (_, index) => {
    const day = new Date(Date.UTC(2026, 7, 22 + index)).toISOString().slice(0, 10);
    return { day, reviews: index % 3 === 0 ? 0 : index * 2 };
  });
}

/** A statistics summary for someone a few weeks into studying. */
export function makeStatsSummary(overrides: Partial<StatsSummary> = {}): StatsSummary {
  return {
    reviewed_today: 42,
    introduced_today: { kana: 5, kanji: 3, vocab: 8 },
    retention_30d: 0.8765,
    daily_reviews: makeDailyReviews(),
    by_type: {
      kana: { total: 416, learning: 10, review: 120, relearning: 2 },
      kanji: { total: 2109, learning: 30, review: 200, relearning: 5 },
      vocab: { total: 15468, learning: 60, review: 900, relearning: 12 },
    },
    by_level: [
      { item_type: 'kanji', level: 'N5', total: 960, introduced: 300, review: 180 },
      { item_type: 'kanji', level: 'N4', total: 704, introduced: 20, review: 5 },
      { item_type: 'kanji', level: 'N3', total: 0, introduced: 0, review: 0 },
      { item_type: 'vocab', level: 'N5', total: 1334, introduced: 700, review: 500 },
      { item_type: 'vocab', level: 'N4', total: 1260, introduced: 100, review: 20 },
    ],
    ...overrides,
  };
}
