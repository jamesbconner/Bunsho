import { describe, expect, it } from 'vitest';

import { ApiError } from '../../api/errors';
import openapi from '../../../openapi.json?raw';
import { makeSettings } from '../../test/fixtures';
import {
  RECOMMENDED_SETTINGS,
  placeServerErrors,
  toFormValues,
  toRequest,
  validateSettings,
  type SettingsFormValues,
} from './settingsForm';

const VALID = toFormValues(makeSettings());

function withValues(overrides: Partial<SettingsFormValues>): SettingsFormValues {
  return { ...VALID, ...overrides };
}

describe('toFormValues and toRequest', () => {
  it('turns fractions into whole percentages and back without noise', () => {
    const values = toFormValues(makeSettings({ target_retention: 0.9, mastery_threshold: 0.8 }));
    expect(values.target_retention_percent).toBe(90);
    expect(values.mastery_threshold_percent).toBe(80);
    const request = toRequest(values);
    expect(request.target_retention).toBe(0.9);
    expect(request.mastery_threshold).toBe(0.8);
  });

  it('keeps a retention that is not a whole percent as it was', () => {
    const settings = makeSettings({ target_retention: 0.905 });
    expect(toFormValues(settings).target_retention_percent).toBe(90.5);
    expect(toRequest(toFormValues(settings)).target_retention).toBe(0.905);
  });

  it('round-trips a whole document unchanged', () => {
    const settings = makeSettings({
      new_card_policy: 'pinned_levels',
      new_limits: { kana: 0, kanji: 7, vocab: 10_000 },
      rollover_hour: 23,
      active_levels: ['N5', 'N3'],
    });
    expect(toRequest(toFormValues(settings))).toEqual(settings);
  });

  it('sends numbers as numbers and levels in study order', () => {
    const request = toRequest(
      withValues({
        new_limits: { kana: '25', kanji: 15, vocab: '0' },
        active_levels: ['N1', 'N5', 'N3'],
        mastery_threshold_percent: '65',
      }),
    );
    expect(request.new_limits).toEqual({ kana: 25, kanji: 15, vocab: 0 });
    expect(request.active_levels).toEqual(['N5', 'N3', 'N1']);
    expect(request.mastery_threshold).toBe(0.65);
  });
});

describe('validateSettings', () => {
  it('accepts the recommended values and the edges of every range', () => {
    expect(validateSettings(VALID)).toEqual({});
    expect(
      validateSettings(
        withValues({
          new_limits: { kana: 0, kanji: 10_000, vocab: '0' },
          target_retention_percent: 70,
          rollover_hour: 23,
          mastery_threshold_percent: 100,
        }),
      ),
    ).toEqual({});
    expect(
      validateSettings(withValues({ target_retention_percent: 99, rollover_hour: 0 })),
    ).toEqual({});
  });

  const invalid: [string, Partial<SettingsFormValues>, string][] = [
    ['a cleared limit', { new_limits: { kana: '', kanji: 15, vocab: 20 } }, 'new_limits.kana'],
    ['a negative limit', { new_limits: { kana: 20, kanji: -1, vocab: 20 } }, 'new_limits.kanji'],
    [
      'a limit over 10,000',
      { new_limits: { kana: 20, kanji: 15, vocab: 10_001 } },
      'new_limits.vocab',
    ],
    ['a fractional limit', { new_limits: { kana: 2.5, kanji: 15, vocab: 20 } }, 'new_limits.kana'],
    ['retention below 70%', { target_retention_percent: 69 }, 'target_retention_percent'],
    ['retention above 99%', { target_retention_percent: 100 }, 'target_retention_percent'],
    ['a rollover hour of 24', { rollover_hour: 24 }, 'rollover_hour'],
    ['no levels', { active_levels: [] }, 'active_levels'],
    ['a cleared threshold', { mastery_threshold_percent: '' }, 'mastery_threshold_percent'],
    ['a threshold over 100%', { mastery_threshold_percent: 101 }, 'mastery_threshold_percent'],
  ];

  it.each(invalid)('rejects %s', (_name, overrides, field) => {
    const errors = validateSettings(withValues(overrides));
    expect(Object.keys(errors)).toEqual([field]);
  });

  it('reports every problem at once', () => {
    const errors = validateSettings(
      withValues({ new_limits: { kana: '', kanji: '', vocab: 20 }, active_levels: [] }),
    );
    expect(Object.keys(errors).sort()).toEqual([
      'active_levels',
      'new_limits.kana',
      'new_limits.kanji',
    ]);
  });
});

describe('placeServerErrors', () => {
  it('puts the server messages on the matching fields', () => {
    const placed = placeServerErrors(
      new ApiError(422, 'Request failed', {
        kana: 'Input should be less than or equal to 10000',
        target_retention: 'Input should be greater than or equal to 0.7',
        mastery_threshold: 'Input should be less than or equal to 1',
        rollover_hour: 'Input should be less than or equal to 23',
        active_levels: 'List should have at least 1 item',
        new_card_policy: 'Input should be a valid policy',
        kanji: 'bad',
        vocab: 'bad',
      }),
    );
    expect(placed.fields).toEqual({
      'new_limits.kana': 'Input should be less than or equal to 10000',
      target_retention_percent: 'Input should be greater than or equal to 0.7',
      mastery_threshold_percent: 'Input should be less than or equal to 1',
      rollover_hour: 'Input should be less than or equal to 23',
      active_levels: 'List should have at least 1 item',
      new_card_policy: 'Input should be a valid policy',
      'new_limits.kanji': 'bad',
      'new_limits.vocab': 'bad',
    });
    expect(placed.general).toBeNull();
  });

  it('keeps messages for unknown fields for the general alert', () => {
    const placed = placeServerErrors(
      new ApiError(422, 'Request failed', { kana: 'too big', surprise: 'unexpected field' }),
    );
    expect(placed.fields).toEqual({ 'new_limits.kana': 'too big' });
    expect(placed.general).toBe('surprise: unexpected field');
  });

  it('says something when a 422 carries no field messages at all', () => {
    const placed = placeServerErrors(new ApiError(422, 'Request failed'));
    expect(placed.fields).toEqual({});
    expect(placed.general).toBe('The server did not accept these settings.');
  });
});

interface Schema {
  properties: Record<string, { default?: unknown; enum?: unknown[] }>;
}

describe('RECOMMENDED_SETTINGS', () => {
  const schemas = (JSON.parse(openapi) as { components: { schemas: Record<string, Schema> } })
    .components.schemas;
  const settings = schemas['ReviewSettings-Input']?.properties ?? {};
  const limits = schemas['NewLimits-Input']?.properties ?? {};

  it('matches the defaults the API declares', () => {
    expect(RECOMMENDED_SETTINGS.new_card_policy).toBe(settings.new_card_policy?.default);
    expect(RECOMMENDED_SETTINGS.target_retention).toBe(settings.target_retention?.default);
    expect(RECOMMENDED_SETTINGS.rollover_hour).toBe(settings.rollover_hour?.default);
    expect(RECOMMENDED_SETTINGS.mastery_threshold).toBe(settings.mastery_threshold?.default);
    expect(RECOMMENDED_SETTINGS.new_limits.kana).toBe(limits.kana?.default);
    expect(RECOMMENDED_SETTINGS.new_limits.kanji).toBe(limits.kanji?.default);
    expect(RECOMMENDED_SETTINGS.new_limits.vocab).toBe(limits.vocab?.default);
  });

  it('is a document the API would accept', () => {
    expect(validateSettings(toFormValues(RECOMMENDED_SETTINGS))).toEqual({});
    expect(RECOMMENDED_SETTINGS.active_levels).toEqual(['N5']);
  });
});
