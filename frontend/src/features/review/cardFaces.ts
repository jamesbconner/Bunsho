import type { CardView, RubySegment } from '../../api/endpoints';

/** One labelled line under the main text of a card face ("Reading", "Meaning"). */
export interface FaceLine {
  label: string;
  text: string;
  japanese: boolean;
}

/** What one side of a card shows. Pure data: `ReviewCard` turns it into markup. */
export interface Face {
  /** A small line above the main text, such as "Vocabulary · N5". */
  caption: string | null;
  /** The large text. With `segments` it is drawn as Japanese with furigana. */
  main: { text: string; japanese: boolean; segments: readonly RubySegment[] | null };
  lines: FaceLine[];
  /** An example sentence with furigana and its English. */
  sentence: { segments: readonly RubySegment[]; english: string } | null;
}

export interface CardFaces {
  front: Face;
  back: Face;
}

export interface CardFaceOptions {
  /** The learner turned furigana on for the front of the card. */
  showFurigana: boolean;
  /** The card has been flipped: readings are shown regardless of the switch. */
  revealed: boolean;
}

const SCRIPTS = { hira: 'Hiragana', kata: 'Katakana' } as const;
const LEVELS = { 1: 'N1', 2: 'N2', 3: 'N3', 4: 'N4', 5: 'N5' } as const;

function face(
  main: Face['main'],
  extras: { caption?: string; lines?: (FaceLine | null)[]; sentence?: Face['sentence'] } = {},
): Face {
  return {
    caption: extras.caption ?? null,
    main,
    lines: (extras.lines ?? []).filter((line): line is FaceLine => line !== null),
    sentence: extras.sentence ?? null,
  };
}

function plain(text: string): Face['main'] {
  return { text, japanese: false, segments: null };
}

function japanese(text: string, segments: readonly RubySegment[] | null = null): Face['main'] {
  return { text, japanese: true, segments };
}

function line(label: string, text: string, isJapanese = false): FaceLine | null {
  return text === '' ? null : { label, text, japanese: isJapanese };
}

function caption(kind: string, detail: string | null): string {
  return detail === null ? kind : `${kind} · ${detail}`;
}

const UNSUPPORTED: CardFaces = {
  front: face(plain('This card cannot be shown')),
  back: face(plain('Reload the page to continue.')),
};

function kanaFaces(card: CardView): CardFaces | null {
  const kana = card.kana;
  if (kana === null || kana === undefined) return null;
  const script = SCRIPTS[kana.script];
  const details = [line('Script', script), line('Group', kana.group)];
  const glyph = japanese(kana.char);
  const sound = plain(kana.romaji);
  if (card.direction === 'glyph_to_sound') {
    return {
      front: face(glyph, { caption: caption('Kana', script) }),
      back: face(sound, { lines: details }),
    };
  }
  return {
    front: face(sound, { caption: caption('Kana', script) }),
    back: face(glyph, { lines: details }),
  };
}

function kanjiFaces(card: CardView): CardFaces | null {
  const kanji = card.kanji;
  if (kanji === null || kanji === undefined) return null;
  const meanings = (kanji.meanings ?? []).join(', ');
  const on = (kanji.on_readings ?? []).join('、');
  const kun = (kanji.kun_readings ?? []).join('、');
  const level = kanji.level === null ? null : LEVELS[kanji.level];
  const captionText = caption('Kanji', level);
  const readings = [line('On', on, true), line('Kun', kun, true)];
  switch (card.direction) {
    case 'kanji_to_meaning':
      return {
        front: face(japanese(kanji.char), { caption: captionText }),
        back: face(plain(meanings), { lines: readings }),
      };
    case 'kanji_to_reading':
      return {
        front: face(japanese(kanji.char), { caption: captionText }),
        back: face(japanese([on, kun].filter((text) => text !== '').join('、')), {
          lines: [line('Meanings', meanings)],
        }),
      };
    case 'meaning_to_kanji':
      return {
        front: face(plain(meanings), { caption: captionText }),
        back: face(japanese(kanji.char), { lines: readings }),
      };
    default:
      return null;
  }
}

function vocabFaces(card: CardView, options: CardFaceOptions): CardFaces | null {
  const vocab = card.vocab;
  if (vocab === null || vocab === undefined) return null;
  const captionText = caption('Vocabulary', LEVELS[vocab.level]);
  const partOfSpeech = line('Part of speech', (vocab.part_of_speech ?? []).join(', '));
  const sentence =
    vocab.sentence === null || vocab.sentence === undefined
      ? null
      : { segments: vocab.sentence.segments, english: vocab.sentence.english };
  if (card.direction === 'recognition') {
    const withReadings = options.showFurigana || options.revealed;
    return {
      front: face(japanese(vocab.expression, withReadings ? vocab.reading_segments : null), {
        caption: captionText,
      }),
      back: face(plain(vocab.meaning), {
        lines: [
          line('Reading', vocab.reading, true),
          partOfSpeech,
          line('More', vocab.additional_definitions ?? ''),
        ],
        sentence,
      }),
    };
  }
  if (card.direction === 'recall') {
    return {
      front: face(plain(vocab.meaning), { caption: captionText, lines: [partOfSpeech] }),
      back: face(japanese(vocab.expression, vocab.reading_segments), {
        lines: [line('Reading', vocab.reading, true)],
        sentence,
      }),
    };
  }
  return null;
}

/** Mark the front of a card the learner has not seen before. */
function withNewTag(faces: CardFaces, isNew: boolean): CardFaces {
  if (!isNew) return faces;
  const caption = [faces.front.caption, 'New'].filter((part) => part !== null).join(' · ');
  return { ...faces, front: { ...faces.front, caption } };
}

function facesFor(card: CardView, options: CardFaceOptions): CardFaces {
  switch (card.item_type) {
    case 'kana':
      return kanaFaces(card) ?? UNSUPPORTED;
    case 'kanji':
      return kanjiFaces(card) ?? UNSUPPORTED;
    case 'vocab':
      return vocabFaces(card, options) ?? UNSUPPORTED;
  }
}

/**
 * The front and back of a card for its type and direction. Furigana is left off the front of
 * cards that test a word's reading or meaning unless the learner switched it on; after the flip
 * the readings are shown. An unseen card carries a "New" tag. A card whose content is missing gets
 * a harmless placeholder so a bad row never breaks the page.
 */
export function cardFaces(card: CardView, options: CardFaceOptions): CardFaces {
  return withNewTag(facesFor(card, options), card.is_new);
}
