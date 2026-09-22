import type { CardView, Grade } from '../../api/endpoints';

/**
 * What a way of answering a card (flip and self-grade; typed answer; multiple choice) receives.
 * A mode shows the card, decides when it is answered, and reports a grade; the page owns
 * fetching, timing and errors.
 */
export interface ReviewModeProps {
  card: CardView;
  showFurigana: boolean;
  /** An answer is being saved (or the next card is loading): ignore input. */
  pending: boolean;
  /** The learner has seen the answer (used for the screen-reader announcement). */
  onReveal: () => void;
  onGrade: (grade: Grade) => void;
  /**
   * The learner is ready for the next card, after seeing feedback. Flip mode never calls this
   * (grading already advances immediately there) but still receives it, since all three modes
   * share one contract.
   */
  onContinue: () => void;
}
