import { fireEvent, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { makeKanaCard, makeKanjiCard, makeVocabCard } from '../../test/fixtures';
import { renderWithProviders } from '../../test/render';
import { FlipMode } from './FlipMode';

function renderMode(overrides: Partial<Parameters<typeof FlipMode>[0]> = {}) {
  const onGrade = vi.fn();
  const onReveal = vi.fn();
  const onContinue = vi.fn();
  const view = renderWithProviders(
    <>
      <input aria-label="Notes" />
      <FlipMode
        card={makeKanaCard()}
        showFurigana={false}
        pending={false}
        onReveal={onReveal}
        onGrade={onGrade}
        onContinue={onContinue}
        {...overrides}
      />
    </>,
  );
  return { onGrade, onReveal, onContinue, ...view };
}

describe('FlipMode', () => {
  it('shows the front with a focused "Show answer" button and hides the answer', () => {
    renderMode();
    expect(screen.getByText('あ')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Show answer' })).toHaveFocus();
    expect(screen.queryByRole('group', { name: 'Grade your answer' })).not.toBeInTheDocument();
    expect(screen.queryByText('Hiragana')).not.toBeInTheDocument();
  });

  it('flips on click, shows the answer and moves focus to the grade group', async () => {
    const user = userEvent.setup();
    const { onReveal } = renderMode();
    await user.click(screen.getByRole('button', { name: 'Show answer' }));
    expect(onReveal).toHaveBeenCalledTimes(1);
    expect(screen.getByText('Hiragana')).toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'Grade your answer' })).toHaveFocus();
    expect(screen.queryByRole('button', { name: 'Show answer' })).not.toBeInTheDocument();
  });

  it.each([[' '], ['{Enter}']])('flips with the %j key', async (key) => {
    const user = userEvent.setup();
    const { onReveal } = renderMode();
    await user.keyboard(key);
    expect(onReveal).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('group', { name: 'Grade your answer' })).toBeInTheDocument();
  });

  it('marks Japanese text runs with lang="ja" and leaves English text unmarked', async () => {
    const user = userEvent.setup();
    const { container } = renderMode({ card: makeKanjiCard() });
    const kanji = screen.getByText('日');
    expect(kanji).toHaveAttribute('lang', 'ja');

    await user.keyboard(' ');
    const meanings = screen.getByText('day, sun');
    expect(meanings.closest('[lang]')).toBeNull();
    for (const reading of ['ニチ、ジツ', 'ひ、か']) {
      expect(screen.getByText(reading)).toHaveAttribute('lang', 'ja');
    }
    expect(container.querySelectorAll('dd[lang="ja"]')).toHaveLength(2);
  });

  it('leaves the romaji of a kana card unmarked', () => {
    renderMode({ card: makeKanaCard({ direction: 'sound_to_glyph' }) });
    expect(screen.getByText('a').closest('[lang]')).toBeNull();
  });

  it('labels each grade with its key and projected interval', async () => {
    const user = userEvent.setup();
    renderMode();
    await user.keyboard(' ');
    for (const name of ['Again · 1 m', 'Hard · 10 m', 'Good · 1 d', 'Easy · 4 d']) {
      expect(screen.getByRole('button', { name })).toBeEnabled();
    }
  });

  it.each([
    ['1', 1],
    ['2', 2],
    ['3', 3],
    ['4', 4],
  ])('grades with the %s key once flipped', async (key, grade) => {
    const user = userEvent.setup();
    const { onGrade } = renderMode();
    await user.keyboard(' ');
    await user.keyboard(key);
    expect(onGrade).toHaveBeenCalledExactlyOnceWith(grade);
  });

  it('grades with a click on a button', async () => {
    const user = userEvent.setup();
    const { onGrade } = renderMode();
    await user.keyboard(' ');
    await user.click(screen.getByRole('button', { name: /^Hard/ }));
    expect(onGrade).toHaveBeenCalledExactlyOnceWith(2);
  });

  it('ignores grade keys before the card is flipped', async () => {
    const user = userEvent.setup();
    const { onGrade } = renderMode();
    await user.keyboard('3');
    expect(onGrade).not.toHaveBeenCalled();
    expect(screen.queryByRole('group', { name: 'Grade your answer' })).not.toBeInTheDocument();
  });

  it('ignores keys with a modifier held', async () => {
    const user = userEvent.setup();
    const { onGrade } = renderMode();
    await user.keyboard(' ');
    await user.keyboard('{Control>}3{/Control}');
    await user.keyboard('{Meta>}3{/Meta}');
    await user.keyboard('{Alt>}3{/Alt}');
    expect(onGrade).not.toHaveBeenCalled();
  });

  it('ignores a key that is being held down (auto-repeat)', async () => {
    const user = userEvent.setup();
    const { onGrade } = renderMode();
    await user.keyboard(' ');
    fireEvent.keyDown(document.body, { key: '3', repeat: true });
    expect(onGrade).not.toHaveBeenCalled();
  });

  it('ignores keys while an input method is composing', async () => {
    const user = userEvent.setup();
    const { onGrade } = renderMode();
    await user.keyboard(' ');
    fireEvent.keyDown(document.body, { key: '3', isComposing: true });
    expect(onGrade).not.toHaveBeenCalled();
  });

  it('leaves keys alone when a text field has focus', async () => {
    const user = userEvent.setup();
    const { onGrade, onReveal } = renderMode();
    await user.click(screen.getByRole('textbox', { name: 'Notes' }));
    await user.keyboard(' 3{Enter}');
    expect(onReveal).not.toHaveBeenCalled();
    expect(onGrade).not.toHaveBeenCalled();
  });

  it('ignores keys and disables the buttons while an answer is pending', async () => {
    const user = userEvent.setup();
    const onGrade = vi.fn();
    function Harness() {
      const [pending, setPending] = useState(false);
      return (
        <div data-review-controls>
          <button
            type="button"
            onClick={() => {
              setPending((value) => !value);
            }}
          >
            Toggle pending
          </button>
          <FlipMode
            card={makeKanaCard()}
            showFurigana={false}
            pending={pending}
            onReveal={vi.fn()}
            onGrade={onGrade}
            onContinue={vi.fn()}
          />
        </div>
      );
    }
    renderWithProviders(<Harness />);
    await user.keyboard(' ');
    await user.click(screen.getByRole('button', { name: 'Toggle pending' }));
    expect(screen.getByRole('button', { name: /^Good/ })).toBeDisabled();
    await user.keyboard('3');
    expect(onGrade).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: 'Toggle pending' }));
    await user.keyboard('3');
    expect(onGrade).toHaveBeenCalledExactlyOnceWith(3);
  });

  it('shows the readings on the front of a vocabulary card only when asked, or after the flip', async () => {
    const user = userEvent.setup();
    const card = makeVocabCard();
    const { container, unmount } = renderMode({ card });
    expect(container.querySelector('ruby')).toBeNull();
    await user.keyboard(' ');
    expect(container.querySelector('ruby')).not.toBeNull();
    unmount();

    const shown = renderMode({ card, showFurigana: true });
    expect(shown.container.querySelector('ruby')).not.toBeNull();
    expect(screen.queryByText('to eat')).not.toBeInTheDocument();
  });
});
