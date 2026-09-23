import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { describe, expect, it } from 'vitest';

import { makeKanaCard } from '../../test/fixtures';
import { renderWithProviders } from '../../test/render';
import { TypedMode } from './TypedMode';

function renderMode(overrides: Partial<Parameters<typeof TypedMode>[0]> = {}) {
  const onGrade = vi.fn();
  const onReveal = vi.fn();
  const onContinue = vi.fn();
  const view = renderWithProviders(
    <TypedMode
      card={makeKanaCard({ accepted_answers: ['a'] })}
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

describe('TypedMode', () => {
  it('shows the front and a focused text input', () => {
    renderMode();
    expect(screen.getByText('あ')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Your answer' })).toHaveFocus();
  });

  it('grades Good and shows feedback when the typed answer matches', async () => {
    const user = userEvent.setup();
    const { onGrade, onReveal } = renderMode();
    await user.type(screen.getByRole('textbox', { name: 'Your answer' }), 'a{Enter}');
    expect(onGrade).toHaveBeenCalledWith(3);
    expect(onReveal).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/Correct/i)).toBeInTheDocument();
  });

  it('grades Again and shows the correct answer when it does not match', async () => {
    const user = userEvent.setup();
    const { onGrade } = renderMode();
    await user.type(screen.getByRole('textbox', { name: 'Your answer' }), 'zzz{Enter}');
    expect(onGrade).toHaveBeenCalledWith(1);
    expect(screen.getByText('a')).toBeInTheDocument(); // the correct answer, shown as feedback
  });

  it('matches case-insensitively and trims whitespace', async () => {
    const user = userEvent.setup();
    const { onGrade } = renderMode();
    await user.type(screen.getByRole('textbox', { name: 'Your answer' }), '  A  {Enter}');
    expect(onGrade).toHaveBeenCalledWith(3);
  });

  it('advances focus to Continue after grading, and calls onContinue when pressed', async () => {
    const user = userEvent.setup();
    const { onContinue } = renderMode();
    await user.type(screen.getByRole('textbox', { name: 'Your answer' }), 'a{Enter}');
    const button = screen.getByRole('button', { name: 'Continue' });
    expect(button).toHaveFocus();
    await user.click(button);
    expect(onContinue).toHaveBeenCalledTimes(1);
  });

  it('ignores submission while pending', async () => {
    const user = userEvent.setup();
    const { onGrade } = renderMode({ pending: true });
    await user.type(screen.getByRole('textbox', { name: 'Your answer' }), 'a{Enter}');
    expect(onGrade).not.toHaveBeenCalled();
  });

  it('disables the input once graded, so a second submit cannot re-grade', async () => {
    const user = userEvent.setup();
    const { onGrade } = renderMode();
    await user.type(screen.getByRole('textbox', { name: 'Your answer' }), 'a{Enter}');
    expect(screen.getByRole('textbox', { name: 'Your answer' })).toBeDisabled();
    expect(onGrade).toHaveBeenCalledTimes(1);
  });
});
