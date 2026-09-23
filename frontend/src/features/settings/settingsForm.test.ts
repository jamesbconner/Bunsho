import { describe, expect, it } from 'vitest';

import type { ReviewSettings } from '../../api/endpoints';
import { ApiError } from '../../api/errors';
import openapi from '../../../openapi.json?raw';
import { makeSettings } from '../../test/fixtures';
import {
  DEFAULT_TAB,
  KANA_GATE_MESSAGE,
  RECOMMENDED_SETTINGS,
  SETTINGS_TABS,
  TAB_OF_FIELD,
  firstErrorPathIn,
  firstTabWithErrors,
  isSettingsDirty,
  isSettingsTab,
  placeServerErrors,
  tabOfField,
  tabsWithErrors,
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
      type_enabled: { kana: true, kanji: false, vocab: true },
      kana_gate: { kanji: false, vocab: true, threshold: 0.9 },
    });
    expect(toRequest(toFormValues(settings))).toEqual(settings);
  });

  it('shows the kana gate threshold as a whole percentage and sends it back as a fraction', () => {
    const values = toFormValues(
      makeSettings({ kana_gate: { kanji: true, vocab: false, threshold: 0.85 } }),
    );
    expect(values.kana_gate.threshold_percent).toBe(85);
    expect(values.type_enabled).toEqual({ kana: true, kanji: true, vocab: true });
    const request = toRequest({
      ...values,
      kana_gate: { ...values.kana_gate, threshold_percent: '65' },
    });
    expect(request.kana_gate).toEqual({ kanji: true, vocab: false, threshold: 0.65 });
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

  it('round-trips the three review modes through the form', () => {
    const settings: ReviewSettings = {
      ...RECOMMENDED_SETTINGS,
      kana_mode: 'typed',
      kanji_mode: 'multiple_choice',
      vocab_mode: 'flip',
    };
    const values = toFormValues(settings);
    expect(values.kana_mode).toBe('typed');
    expect(values.kanji_mode).toBe('multiple_choice');
    expect(toRequest(values).kana_mode).toBe('typed');
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

  it('asks for kana to be on when a gate is on', () => {
    const errors = validateSettings(
      withValues({
        type_enabled: { kana: false, kanji: true, vocab: true },
        kana_gate: { kanji: true, vocab: false, threshold_percent: 80 },
      }),
    );
    expect(errors).toEqual({ kana_gate: KANA_GATE_MESSAGE });
  });

  it('allows kana off with no gate, and every type off', () => {
    expect(
      validateSettings(withValues({ type_enabled: { kana: false, kanji: true, vocab: true } })),
    ).toEqual({});
    expect(
      validateSettings(withValues({ type_enabled: { kana: false, kanji: false, vocab: false } })),
    ).toEqual({});
  });

  it('accepts the edges of the gate threshold and rejects anything else', () => {
    for (const threshold of [0, 100, 80.5, '65']) {
      expect(
        validateSettings(
          withValues({ kana_gate: { ...VALID.kana_gate, threshold_percent: threshold } }),
        ),
      ).toEqual({});
    }
    for (const threshold of ['', ' ', -1, 101, 'abc']) {
      expect(
        validateSettings(
          withValues({ kana_gate: { ...VALID.kana_gate, threshold_percent: threshold } }),
        ),
      ).toEqual({ 'kana_gate.threshold_percent': 'Enter a percentage from 0 to 100.' });
    }
  });
});

describe('isSettingsDirty', () => {
  it('is false for identical values', () => {
    expect(isSettingsDirty(withValues({}), VALID)).toBe(false);
  });

  const changes: [string, Partial<SettingsFormValues>][] = [
    ['the policy', { new_card_policy: 'pinned_levels' }],
    ['the kana limit', { new_limits: { ...VALID.new_limits, kana: 21 } }],
    ['the kanji limit', { new_limits: { ...VALID.new_limits, kanji: 16 } }],
    ['the vocabulary limit', { new_limits: { ...VALID.new_limits, vocab: 21 } }],
    ['the retention', { target_retention_percent: 91 }],
    ['the rollover hour', { rollover_hour: 5 }],
    ['the levels (added)', { active_levels: ['N5', 'N4'] }],
    ['the levels (removed)', { active_levels: [] }],
    ['the mastery threshold', { mastery_threshold_percent: 81 }],
  ];

  it.each(changes)('is true when %s changed', (_name, overrides) => {
    expect(isSettingsDirty(withValues(overrides), VALID)).toBe(true);
  });

  it('tells a cleared field from 0, and a typed string from the same number', () => {
    const zero = toFormValues(makeSettings({ new_limits: { kana: 0, kanji: 15, vocab: 20 } }));
    expect(isSettingsDirty({ ...zero, new_limits: { ...zero.new_limits, kana: '' } }, zero)).toBe(
      true,
    );
    expect(isSettingsDirty({ ...zero, new_limits: { ...zero.new_limits, kana: '0' } }, zero)).toBe(
      false,
    );
    expect(isSettingsDirty(withValues({ mastery_threshold_percent: '80' }), VALID)).toBe(false);
    expect(isSettingsDirty(withValues({ mastery_threshold_percent: '' }), VALID)).toBe(true);
  });

  it('ignores the order the levels were ticked in', () => {
    const saved = toFormValues(makeSettings({ active_levels: ['N5', 'N4'] }));
    expect(isSettingsDirty({ ...saved, active_levels: ['N4', 'N5'] }, saved)).toBe(false);
  });

  it('treats a changed type switch or gate field as dirty', () => {
    expect(
      isSettingsDirty(
        withValues({ type_enabled: { kana: true, kanji: false, vocab: true } }),
        VALID,
      ),
    ).toBe(true);
    expect(
      isSettingsDirty(withValues({ kana_gate: { ...VALID.kana_gate, kanji: true } }), VALID),
    ).toBe(true);
    expect(
      isSettingsDirty(
        withValues({ kana_gate: { ...VALID.kana_gate, threshold_percent: '' } }),
        VALID,
      ),
    ).toBe(true);
  });

  it('treats a changed review mode as dirty', () => {
    const initial = toFormValues(RECOMMENDED_SETTINGS);
    const changed = { ...initial, kana_mode: 'typed' as const };
    expect(isSettingsDirty(changed, initial)).toBe(true);
  });
});

describe('placeServerErrors', () => {
  it('puts the server messages on the matching fields', () => {
    const placed = placeServerErrors(
      new ApiError(422, 'Request failed', {
        'new_limits.kana': 'Input should be less than or equal to 10000',
        target_retention: 'Input should be greater than or equal to 0.7',
        mastery_threshold: 'Input should be less than or equal to 1',
        rollover_hour: 'Input should be less than or equal to 23',
        active_levels: 'List should have at least 1 item',
        new_card_policy: 'Input should be a valid policy',
        'new_limits.kanji': 'bad',
        'new_limits.vocab': 'bad',
        kana_gate: 'Turn kana on',
        'kana_gate.threshold': 'Input should be less than or equal to 1',
        'kana_gate.kanji': 'not a boolean',
        'type_enabled.kana': 'not a boolean either',
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
      kana_gate: 'Turn kana on',
      'kana_gate.threshold_percent': 'Input should be less than or equal to 1',
      'kana_gate.kanji': 'not a boolean',
      'type_enabled.kana': 'not a boolean either',
    });
    expect(placed.general).toBeNull();
  });

  it('keeps kana, kanji and vocab under different groups apart', () => {
    const placed = placeServerErrors(
      new ApiError(422, 'Request failed', {
        'new_limits.kana': 'limit',
        'type_enabled.kana': 'switch',
        'kana_gate.kanji': 'gate',
      }),
    );
    expect(placed.fields).toEqual({
      'new_limits.kana': 'limit',
      'type_enabled.kana': 'switch',
      'kana_gate.kanji': 'gate',
    });
  });

  it('keeps messages for unknown fields for the general alert', () => {
    const placed = placeServerErrors(
      new ApiError(422, 'Request failed', {
        'new_limits.kana': 'too big',
        surprise: 'unexpected field',
      }),
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
  const enabled = schemas['TypeEnabled-Input']?.properties ?? {};
  const gate = schemas['KanaGate-Input']?.properties ?? {};

  it('matches the defaults the API declares', () => {
    expect(RECOMMENDED_SETTINGS.new_card_policy).toBe(settings.new_card_policy?.default);
    expect(RECOMMENDED_SETTINGS.target_retention).toBe(settings.target_retention?.default);
    expect(RECOMMENDED_SETTINGS.rollover_hour).toBe(settings.rollover_hour?.default);
    expect(RECOMMENDED_SETTINGS.mastery_threshold).toBe(settings.mastery_threshold?.default);
    expect(RECOMMENDED_SETTINGS.new_limits.kana).toBe(limits.kana?.default);
    expect(RECOMMENDED_SETTINGS.new_limits.kanji).toBe(limits.kanji?.default);
    expect(RECOMMENDED_SETTINGS.new_limits.vocab).toBe(limits.vocab?.default);
  });

  it('matches the type switches and kana gate the API declares', () => {
    expect(RECOMMENDED_SETTINGS.type_enabled.kana).toBe(enabled.kana?.default);
    expect(RECOMMENDED_SETTINGS.type_enabled.kanji).toBe(enabled.kanji?.default);
    expect(RECOMMENDED_SETTINGS.type_enabled.vocab).toBe(enabled.vocab?.default);
    expect(RECOMMENDED_SETTINGS.kana_gate.kanji).toBe(gate.kanji?.default);
    expect(RECOMMENDED_SETTINGS.kana_gate.vocab).toBe(gate.vocab?.default);
    expect(RECOMMENDED_SETTINGS.kana_gate.threshold).toBe(gate.threshold?.default);
  });

  it('is a document the API would accept', () => {
    expect(validateSettings(toFormValues(RECOMMENDED_SETTINGS))).toEqual({});
    expect(RECOMMENDED_SETTINGS.active_levels).toEqual(['N5']);
  });
});

describe('settings tabs', () => {
  it('lists the tabs in display order with their labels', () => {
    expect(SETTINGS_TABS.map((tab) => tab.value)).toEqual([
      'learning',
      'pace',
      'reviewing',
      'system',
    ]);
    expect(SETTINGS_TABS.map((tab) => tab.label)).toEqual([
      'Learning path',
      'Pace',
      'Reviewing',
      'System',
    ]);
    expect(DEFAULT_TAB).toBe('learning');
  });

  it.each([
    ['learning', true],
    ['system', true],
    ['admin', false],
    ['', false],
    [null, false],
    [undefined, false],
  ])('isSettingsTab(%j) is %s', (value, expected) => {
    expect(isSettingsTab(value)).toBe(expected);
  });

  it('places every field of the form on a tab', () => {
    for (const field of Object.keys(toFormValues(RECOMMENDED_SETTINGS))) {
      expect(Object.hasOwn(TAB_OF_FIELD, field), field).toBe(true);
    }
  });

  it.each([
    ['new_card_policy', 'learning'],
    ['active_levels', 'learning'],
    ['mastery_threshold_percent', 'learning'],
    ['type_enabled.kana', 'learning'],
    ['kana_gate', 'learning'],
    ['kana_gate.threshold_percent', 'learning'],
    ['new_limits', 'pace'],
    ['new_limits.kana', 'pace'],
    ['rollover_hour', 'pace'],
    ['target_retention_percent', 'pace'],
    ['kana_mode', 'reviewing'],
    ['vocab_mode', 'reviewing'],
    ['not_a_field', 'learning'],
    ['', 'learning'],
  ])('puts %s on the %s tab', (path, tab) => {
    expect(tabOfField(path)).toBe(tab);
  });

  it('finds the tabs that hold an error, whatever the nesting', () => {
    expect([...tabsWithErrors({})]).toEqual([]);
    expect([...tabsWithErrors({ 'new_limits.kana': 'Too big', kana_gate: 'Needs kana' })]).toEqual(
      expect.arrayContaining(['pace', 'learning']),
    );
    expect(tabsWithErrors({ kana_mode: 'Bad' }).has('reviewing')).toBe(true);
  });

  it('ignores an entry that holds no message', () => {
    expect([
      ...tabsWithErrors({ rollover_hour: null, kana_mode: undefined, x: false, y: '' }),
    ]).toEqual([]);
  });

  it('picks the first tab in tab order, not in key order', () => {
    expect(firstTabWithErrors({})).toBeNull();
    expect(firstTabWithErrors({ kana_mode: 'Bad', rollover_hour: 'Bad' })).toBe('pace');
    expect(firstTabWithErrors({ kana_mode: 'Bad', new_card_policy: 'Bad' })).toBe('learning');
  });

  it('picks the first errored field of a tab', () => {
    const errors = { kana_mode: 'Bad', rollover_hour: 'Bad', 'new_limits.kanji': 'Bad' };
    expect(firstErrorPathIn(errors, 'pace')).toBe('rollover_hour');
    expect(firstErrorPathIn(errors, 'reviewing')).toBe('kana_mode');
    expect(firstErrorPathIn(errors, 'learning')).toBeNull();
  });
});
