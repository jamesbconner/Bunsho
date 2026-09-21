import { Furigana } from '../../components/Furigana';
import type { Face } from './cardFaces';
import classes from './review.module.css';

/** One side of a card: an optional caption, the main text, labelled lines and the example. */
export function ReviewCard({ face, answer = false }: { face: Face; answer?: boolean }) {
  const { caption, main, lines, sentence } = face;
  return (
    <section className={answer ? `${classes.card} ${classes.answer}` : classes.card}>
      {caption !== null && <div className={classes.caption}>{caption}</div>}
      <div className={main.japanese ? classes.mainJapanese : classes.mainLatin}>
        {main.segments !== null ? (
          <Furigana segments={main.segments} />
        ) : main.japanese ? (
          <span lang="ja">{main.text}</span>
        ) : (
          main.text
        )}
      </div>
      {lines.length > 0 && (
        <dl className={classes.lines}>
          {lines.map((line) => (
            <div key={line.label} style={{ display: 'contents' }}>
              <dt>{line.label}</dt>
              <dd lang={line.japanese ? 'ja' : undefined}>{line.text}</dd>
            </div>
          ))}
        </dl>
      )}
      {sentence !== null && (
        <div className={classes.sentence}>
          <Furigana segments={sentence.segments} />
          <div className={classes.english}>{sentence.english}</div>
        </div>
      )}
    </section>
  );
}
