import type { CardView, Grade } from '../../api/endpoints';

/**
 * What a way of answering a card (flip and self-grade today; typed answer or multiple choice
 * later) receives. A mode shows the card, decides when it is answered, and reports a grade; the
 * page owns fetching, timing and errors.
 */
export interface ReviewModeProps {
  card: CardView;
  showFurigana: boolean;
  /** An answer is being saved (or the next card is loading): ignore input. */
  pending: boolean;
  /** The learner has seen the answer (used for the screen-reader announcement). */
  onReveal: () => void;
  onGrade: (grade: Grade) => void;
}
