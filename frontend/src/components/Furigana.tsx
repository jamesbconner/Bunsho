import type { RubySegment } from '../api/endpoints';
import classes from './Furigana.module.css';

/**
 * Japanese text with its readings above the kanji, from the API's ruby segments. Native
 * `<ruby>` with `<rp>` fallbacks, so browsers without ruby support show "kanji(reading)".
 * A highlighted segment (the word an example sentence is about) is emphasised.
 */
export function Furigana({ segments }: { segments: readonly RubySegment[] }) {
  return (
    <span lang="ja" className={classes.text}>
      {segments.map((segment, index) => {
        const highlighted = segment.highlighted === true;
        const key = `${index}:${segment.base}`;
        if (segment.reading === null || segment.reading === undefined || segment.reading === '') {
          return (
            <span
              key={key}
              className={highlighted ? classes.highlight : undefined}
              data-highlighted={highlighted ? 'true' : undefined}
            >
              {segment.base}
            </span>
          );
        }
        return (
          <ruby
            key={key}
            className={highlighted ? classes.highlight : undefined}
            data-highlighted={highlighted ? 'true' : undefined}
          >
            {segment.base}
            <rp>(</rp>
            <rt>{segment.reading}</rt>
            <rp>)</rp>
          </ruby>
        );
      })}
    </span>
  );
}
