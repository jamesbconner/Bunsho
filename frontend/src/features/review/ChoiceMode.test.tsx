import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { makeKanaCard, makeKanjiCard } from '../../test/fixtures';
import { renderWithProviders } from '../../test/render';
import { ChoiceMode } from './ChoiceMode';

function renderMode(overrides: Partial<Parameters<typeof ChoiceMode>[0]> = {}) {
  const onGrade = vi.fn();
  const onReveal = vi.fn();
  const onContinue = vi.fn();
  const view = renderWithProviders(
    <ChoiceMode
      card={makeKanaCard({ choices: ['a', 'i', 'u', 'e'] })}
      showFurigana={false}
      pending={false}
      onReveal={onReveal}
      onGrade={onGrade}
      onContinue={onContinue}
      {...overrides}
    />,
  );
  return { onGrade, onReveal, onContinue, ...view };
}

describe('ChoiceMode', () => {
  it('shows the front and all four options as buttons, keyed 1 to 4', () => {
    renderMode();
    expect(screen.getByText('あ')).toBeInTheDocument();
    for (const [index, label] of ['a', 'i', 'u', 'e'].entries()) {
      expect(screen.getByRole('button', { name: new RegExp(label) })).toHaveAttribute(
        'aria-keyshortcuts',
        String(index + 1),
      );
    }
  });

  it('grades Good and reveals when the correct option is picked', async () => {
    const user = userEvent.setup();
    const { onGrade, onReveal } = renderMode();
    await user.click(screen.getByRole('button', { name: /^a$/ }));
    expect(onGrade).toHaveBeenCalledWith(3);
    expect(onReveal).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/Correct/i)).toBeInTheDocument();
  });

  it('grades Again when a wrong option is picked, and highlights the correct one', async () => {
    const user = userEvent.setup();
    const { onGrade } = renderMode();
    await user.click(screen.getByRole('button', { name: /^i$/ }));
    expect(onGrade).toHaveBeenCalledWith(1);
    expect(screen.getByText(/Not quite/i)).toBeInTheDocument();
  });

  it('picks with the 1-4 number keys', async () => {
    const user = userEvent.setup();
    const { onGrade } = renderMode();
    await user.keyboard('1');
    expect(onGrade).toHaveBeenCalledWith(3);
  });

  it('ignores a pick while pending, and a second pick after the first', async () => {
    const user = userEvent.setup();
    const { onGrade } = renderMode({ pending: true });
    await user.click(screen.getByRole('button', { name: /^a$/ }));
    expect(onGrade).not.toHaveBeenCalled();
  });

  it('calls onContinue on click and on Enter once an option is picked', async () => {
    const user = userEvent.setup();
    const { onContinue } = renderMode();
    await user.click(screen.getByRole('button', { name: /^a$/ }));
    await user.keyboard('{Enter}');
    expect(onContinue).toHaveBeenCalledTimes(1);
  });

  it('marks the options as Japanese when the answer is Japanese', () => {
    renderMode({
      card: makeKanjiCard({
        direction: 'meaning_to_kanji',
        mode: 'multiple_choice',
        accepted_answers: ['日'],
        choices: ['日', '月', '火', '水'],
      }),
    });
    for (const glyph of ['日', '月', '火', '水']) {
      expect(screen.getByText(glyph)).toHaveAttribute('lang', 'ja');
    }
  });

  it('leaves the options unmarked when the answer is English or romaji', () => {
    renderMode();
    for (const sound of ['a', 'i', 'u', 'e']) {
      expect(screen.getByText(sound)).not.toHaveAttribute('lang');
    }
  });
});
