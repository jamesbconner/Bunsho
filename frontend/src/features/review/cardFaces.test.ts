import { describe, expect, it } from 'vitest';

import { makeKanaCard, makeKanjiCard, makeVocabCard, segment } from '../../test/fixtures';
import { cardFaces } from './cardFaces';

const OFF = { showFurigana: false, revealed: false };

describe('cardFaces: kana', () => {
  it('glyph to sound shows the character, then the romaji with script and group', () => {
    const { front, back } = cardFaces(makeKanaCard(), OFF);
    expect(front.main).toEqual({ text: 'あ', japanese: true, segments: null });
    expect(front.caption).toBe('Kana · Hiragana · New');
    expect(back.main).toEqual({ text: 'a', japanese: false, segments: null });
    expect(back.lines.map((line) => line.text)).toEqual(['Hiragana', 'a']);
  });

  it('sound to glyph swaps the sides', () => {
    const { front, back } = cardFaces(makeKanaCard({ direction: 'sound_to_glyph' }), OFF);
    expect(front.main.text).toBe('a');
    expect(back.main).toEqual({ text: 'あ', japanese: true, segments: null });
  });
});

describe('cardFaces: kanji', () => {
  it('kanji to meaning shows the meanings, with the readings underneath', () => {
    const { front, back } = cardFaces(makeKanjiCard(), OFF);
    expect(front.main.text).toBe('日');
    expect(front.caption).toBe('Kanji · N5');
    expect(back.main).toEqual({ text: 'day, sun', japanese: false, segments: null });
    expect(back.lines).toEqual([
      { label: 'On', text: 'ニチ、ジツ', japanese: true },
      { label: 'Kun', text: 'ひ、か', japanese: true },
    ]);
  });

  it('kanji to reading shows on and kun readings, with the meanings underneath', () => {
    const { back } = cardFaces(makeKanjiCard({ direction: 'kanji_to_reading' }), OFF);
    expect(back.main).toEqual({ text: 'ニチ、ジツ、ひ、か', japanese: true, segments: null });
    expect(back.lines).toEqual([{ label: 'Meanings', text: 'day, sun', japanese: false }]);
  });

  it('meaning to kanji asks with the meanings and answers with the kanji', () => {
    const { front, back } = cardFaces(makeKanjiCard({ direction: 'meaning_to_kanji' }), OFF);
    expect(front.main).toEqual({ text: 'day, sun', japanese: false, segments: null });
    expect(back.main).toEqual({ text: '日', japanese: true, segments: null });
  });

  it('leaves the level out for a kanji without one and skips empty reading lines', () => {
    const card = makeKanjiCard();
    const { front, back } = cardFaces(
      {
        ...card,
        kanji: card.kanji && { ...card.kanji, level: null, on_readings: [], kun_readings: ['ひ'] },
      },
      OFF,
    );
    expect(front.caption).toBe('Kanji');
    expect(back.lines).toEqual([{ label: 'Kun', text: 'ひ', japanese: true }]);
  });
});

describe('cardFaces: vocabulary', () => {
  it('recognition hides furigana on the front and shows it once flipped', () => {
    const front = cardFaces(makeVocabCard(), OFF).front;
    expect(front.main).toEqual({ text: '食べる', japanese: true, segments: null });
    expect(front.caption).toBe('Vocabulary · N5');
    const flipped = cardFaces(makeVocabCard(), { showFurigana: false, revealed: true }).front;
    expect(flipped.main.segments).toEqual([segment('食', 'た'), segment('べる')]);
  });

  it('recognition shows furigana on the front when the learner asks for it', () => {
    const { front } = cardFaces(makeVocabCard(), { showFurigana: true, revealed: false });
    expect(front.main.segments).not.toBeNull();
  });

  it('recognition answers with the meaning, reading, part of speech and the example sentence', () => {
    const { back } = cardFaces(makeVocabCard(), OFF);
    expect(back.main).toEqual({ text: 'to eat', japanese: false, segments: null });
    expect(back.lines).toEqual([
      { label: 'Reading', text: 'たべる', japanese: true },
      { label: 'Part of speech', text: 'verb, ichidan', japanese: false },
    ]);
    expect(back.sentence?.english).toBe('I eat breakfast every day.');
    expect(back.sentence?.segments).toHaveLength(5);
  });

  it('recall asks with the meaning and answers with the word and its furigana', () => {
    const { front, back } = cardFaces(makeVocabCard({ direction: 'recall' }), OFF);
    expect(front.main).toEqual({ text: 'to eat', japanese: false, segments: null });
    expect(front.lines).toEqual([
      { label: 'Part of speech', text: 'verb, ichidan', japanese: false },
    ]);
    expect(back.main.text).toBe('食べる');
    expect(back.main.segments).not.toBeNull();
    expect(back.lines).toEqual([{ label: 'Reading', text: 'たべる', japanese: true }]);
  });

  it('omits the example sentence and empty lines when the word has none', () => {
    const card = makeVocabCard();
    const { back } = cardFaces(
      { ...card, vocab: card.vocab && { ...card.vocab, sentence: null, part_of_speech: [] } },
      OFF,
    );
    expect(back.sentence).toBeNull();
    expect(back.lines).toEqual([{ label: 'Reading', text: 'たべる', japanese: true }]);
  });

  it('adds the additional definitions when there are some', () => {
    const card = makeVocabCard();
    const { back } = cardFaces(
      { ...card, vocab: card.vocab && { ...card.vocab, additional_definitions: 'to live on' } },
      OFF,
    );
    expect(back.lines).toContainEqual({ label: 'More', text: 'to live on', japanese: false });
  });
});

describe('cardFaces: new cards', () => {
  it('tags the front of an unseen card and leaves a seen card alone', () => {
    expect(cardFaces(makeKanaCard({ is_new: true }), OFF).front.caption).toBe(
      'Kana · Hiragana · New',
    );
    expect(cardFaces(makeKanaCard({ is_new: false }), OFF).front.caption).toBe('Kana · Hiragana');
  });

  it('tags a placeholder front too, without a leading separator', () => {
    const { front } = cardFaces(makeKanaCard({ kana: null, is_new: true }), OFF);
    expect(front.caption).toBe('New');
  });
});

describe('cardFaces: bad data', () => {
  it('shows a placeholder when the content of the card is missing', () => {
    const { front } = cardFaces(makeKanaCard({ kana: null }), OFF);
    expect(front.main.text).toBe('This card cannot be shown');
  });

  it('shows a placeholder for a direction that does not fit the type', () => {
    const { front } = cardFaces(makeVocabCard({ direction: 'glyph_to_sound' }), OFF);
    expect(front.main.text).toBe('This card cannot be shown');
  });
});
